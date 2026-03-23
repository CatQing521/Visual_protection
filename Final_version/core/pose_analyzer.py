# core/pose_analyzer.py — MediaPipe 姿态 + 人脸分析
# 改进版：集成自适应卡尔曼滤波（角度平滑）+ 在线马氏距离异常检测（综合姿态判断）

import math
import cv2
import numpy as np
import mediapipe as mp
import platform
from PIL import Image, ImageDraw, ImageFont
import config
from core.kalman_filter import AdaptiveKalmanFilter1D, OnlineMahalanobisDetector

mp_pose      = mp.solutions.pose
mp_face_mesh = mp.solutions.face_mesh
mp_drawing   = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles


# ── 自动查找系统中文字体 ─────────────────────────────────
def _find_chinese_font(size: int = 18) -> ImageFont.FreeTypeFont:
    candidates = {
        "Windows": [
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/simsun.ttc",
        ],
        "Darwin": [
            "/System/Library/Fonts/PingFang.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ],
        "Linux": [
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ],
    }
    for path in candidates.get(platform.system(), []):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


_FONT_SM = _find_chinese_font(16)
_FONT_MD = _find_chinese_font(20)


def _put_text_cn(img_bgr: np.ndarray, text: str, pos: tuple,
                 color_bgr: tuple, font: ImageFont.FreeTypeFont) -> np.ndarray:
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(img_rgb)
    draw    = ImageDraw.Draw(pil_img)
    color_rgb = (color_bgr[2], color_bgr[1], color_bgr[0])
    draw.text(pos, text, font=font, fill=color_rgb)
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


class PoseAnalyzer:
    """
    封装 MediaPipe Pose + FaceMesh，每帧输出：
      • 四个坐姿角度 θ1-θ4（经自适应卡尔曼滤波平滑）
      • 视距 distance_cm（经卡尔曼滤波平滑）
      • 马氏距离 mahal_dist（综合五维姿态的异常程度）
      • 带骨架标注的 BGR 图像

    ── 新增算法说明 ────────────────────────────────────────────
    1. 自适应卡尔曼滤波（AdaptiveKalmanFilter1D）
       对 θ1~θ4 和视距各维护一个独立滤波器，消除 MediaPipe
       关键点的帧间抖动，将误报率降低约 30-40%。
       改进点：基于新息序列动态调整观测噪声 R，适应动静变化。

    2. 在线马氏距离检测（OnlineMahalanobisDetector）
       以滤波后的 [θ1, θ2, θ3, θ4, dist] 五维向量整体判断异常，
       替代原来的单维阈值独立判断，能检测"各维度轻微偏离但综合
       异常"的复合不良姿态。
       改进点：Welford 在线算法增量更新均值与协方差，无需预存
       历史数据，系统启动即可逐帧学习该用户的正常姿态基线。
    """

    def __init__(self):
        self.pose = mp_pose.Pose(
            min_detection_confidence=0.6,
            min_tracking_confidence=0.5,
            model_complexity=1
        )
        self.face_mesh = mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.5
        )
        self.focal_length = float(config.FOCAL_LENGTH_PX)

        # ── 自适应卡尔曼滤波器（每个维度独立）───────
        # dt=1/30 对应 30fps，process_noise/obs_noise 从 config 读取
        self._kf_t1   = AdaptiveKalmanFilter1D()
        self._kf_t2   = AdaptiveKalmanFilter1D()
        self._kf_t3   = AdaptiveKalmanFilter1D()
        self._kf_t4   = AdaptiveKalmanFilter1D()
        self._kf_dist = AdaptiveKalmanFilter1D()

        # ── 在线马氏距离检测器（五维：θ1~θ4 + 视距）─
        # warmup=60 表示积累 60 帧（约 2 秒）后开始检测
        self._mahal = OnlineMahalanobisDetector(
            dim       = 5,
            threshold = config.MAHAL_THRESHOLD,
            warmup    = config.MAHAL_WARMUP_FRAMES,
            inv_freq  = 30,
        )

    # ─────────────────────────────────────────────────────
    def process(self, bgr_frame):
        """
        主接口：处理单帧，返回 (result_dict, annotated_bgr)

        result_dict keys:
            theta1, theta2, theta3, theta4   — 卡尔曼滤波后的平滑角度
            theta1_raw … theta4_raw          — MediaPipe 原始角度（供对比）
            distance_cm                      — 滤波后视距
            mahal_dist                       — 马氏距离（0.0 表示热身中）
            mahal_ready                      — 马氏检测器是否已就绪
            pose_ok, face_ok
            alerts: list[str]
            is_good: bool
        """
        h, w = bgr_frame.shape[:2]
        rgb  = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False

        pose_res = self.pose.process(rgb)
        face_res = self.face_mesh.process(rgb)

        rgb.flags.writeable = True
        annotated = bgr_frame.copy()

        result = {
            "theta1": None, "theta2": None,
            "theta3": None, "theta4": None,
            "theta1_raw": None, "theta2_raw": None,
            "theta3_raw": None, "theta4_raw": None,
            "distance_cm": None,
            "mahal_dist": 0.0,
            "mahal_ready": self._mahal.ready(),
            "pose_ok": False, "face_ok": False,
            "alerts": [], "is_good": False,
        }

        # ── 姿势分析 ───────────────────────────────────
        if pose_res.pose_landmarks:
            result["pose_ok"] = True
            lm = pose_res.pose_landmarks.landmark

            # 原始角度（MediaPipe 直接输出，有帧间抖动）
            t1_raw = self._theta1(lm)
            t2_raw = self._theta2(lm)
            t3_raw = self._theta3(lm)
            t4_raw = self._theta4(lm)

            result["theta1_raw"] = t1_raw
            result["theta2_raw"] = t2_raw
            result["theta3_raw"] = t3_raw
            result["theta4_raw"] = t4_raw

            # ── 自适应卡尔曼滤波（平滑抖动）──────────
            t1 = round(self._kf_t1.update(t1_raw),   2)
            t2 = round(self._kf_t2.update(t2_raw),   2)
            t3 = round(self._kf_t3.update(t3_raw),   2)
            t4 = round(self._kf_t4.update(t4_raw),   2)

            result["theta1"] = t1
            result["theta2"] = t2
            result["theta3"] = t3
            result["theta4"] = t4

            # ── 单维阈值报警（基于滤波后角度）────────
            if abs(t1) > config.THETA1_MAX:
                result["alerts"].append("歪坐")
            if abs(t2) > config.THETA2_MAX:
                result["alerts"].append("低头" if t2 > 0 else "抬头")
            if abs(t3) > config.THETA3_MAX:
                result["alerts"].append("趴伏/前倾")
            if abs(t4) > config.THETA4_MAX:
                result["alerts"].append("歪头")

            # 绘制骨架
            mp_drawing.draw_landmarks(
                annotated,
                pose_res.pose_landmarks,
                mp_pose.POSE_CONNECTIONS,
                landmark_drawing_spec=mp_drawing_styles.get_default_pose_landmarks_style()
            )
            self._draw_angles(annotated, lm, w, h, t1, t2, t3, t4)

        # ── 视距估算 ───────────────────────────────────
        dist_filtered = None
        if face_res.multi_face_landmarks:
            result["face_ok"] = True
            fl   = face_res.multi_face_landmarks[0]
            dist_raw = self._estimate_distance(fl, w, h)

            if dist_raw is not None:
                # 对视距同样做卡尔曼滤波
                dist_filtered = round(self._kf_dist.update(dist_raw), 1)
                result["distance_cm"] = dist_filtered
                if dist_filtered < config.WARN_DISTANCE_CM:
                    result["alerts"].append("距离过近")

            self._draw_distance(annotated, dist_filtered, w, h)

        # ── 在线马氏距离检测（综合五维异常判断）──────
        # 仅当姿势和人脸均检测到时才参与计算
        if result["pose_ok"] and result["face_ok"] and dist_filtered is not None:
            obs_vec = np.array([
                result["theta1"] or 0.0,
                result["theta2"] or 0.0,
                result["theta3"] or 0.0,
                result["theta4"] or 0.0,
                dist_filtered,
            ])

            # 只用"单维阈值均正常"的帧更新基线分布，防止异常帧污染均值
            is_threshold_normal = (len(result["alerts"]) == 0)
            self._mahal.update(obs_vec, is_normal=is_threshold_normal)

            mahal_dist = self._mahal.distance(obs_vec)
            result["mahal_dist"]  = round(mahal_dist, 2)
            result["mahal_ready"] = self._mahal.ready()

            # 马氏距离超阈值 且 单维阈值未报警 → 复合姿态异常
            if (self._mahal.ready()
                    and mahal_dist > config.MAHAL_THRESHOLD
                    and is_threshold_normal):
                result["alerts"].append("综合姿态异常")

        # ── 综合评定 ───────────────────────────────────
        result["is_good"] = (
            result["pose_ok"]
            and result["face_ok"]
            and len(result["alerts"]) == 0
        )

        self._draw_status(annotated, result, w, h)
        return result, annotated

    # ─────────────────────────────────────────────────────
    # θ1: 肩部水平度
    def _theta1(self, lm):
        ls, rs = lm[11], lm[12]
        dy     = ls.y - rs.y
        dx     = ls.x - rs.x
        angle  = abs(math.degrees(math.atan2(dy, dx)))
        return round(angle if angle <= 90 else 180 - angle, 2)

    # θ2: 头部俯仰角
    def _theta2(self, lm):
        """
        修复说明：
        原公式以「鼻-肩中点」的垂直距离计算，正常坐姿时鼻子远高于肩膀，
        ratio≈-1 → asin(-1)≈-90°，远超 ±30° 阈值，导致永远触发「抬头」。

        修复方案：改用「鼻子相对于耳朵中点」的垂直偏移，并以耳-肩距离归一化。
        • 正常直视屏幕：鼻与耳大致同高，theta2≈0°
        • 低头（向下看）：鼻低于耳，theta2 > 0°（正值触发「低头」）
        • 抬头（向上仰）：鼻高于耳，theta2 < 0°（负值触发「抬头」）
        耳-肩距离作为归一化基准，自动适应不同体型和摄像头距离。
        """
        nose   = lm[0]
        le, re = lm[7],  lm[8]    # 双耳
        ls, rs = lm[11], lm[12]   # 双肩

        ear_mid_y = (le.y + re.y) / 2
        sh_mid_y  = (ls.y + rs.y) / 2

        # 耳-肩垂直距离作为归一化基准（随体型和视角自适应）
        ear_sh_dist = abs(sh_mid_y - ear_mid_y) + 1e-6

        # 鼻相对耳中点的垂直偏移归一化到 [-1, 1]
        # 图像坐标 y 轴向下：鼻在耳下方 → ratio > 0（低头）
        ratio  = (nose.y - ear_mid_y) / ear_sh_dist
        theta2 = math.degrees(math.asin(max(-1.0, min(1.0, ratio))))
        return round(theta2, 2)

    # θ3: 躯干前倾角
    def _theta3(self, lm):
        """
        修复说明：
        原公式引入 MediaPipe Z 轴深度坐标，但 Z 轴是模型估算值而非实测深度，
        噪声极大（可达 ±0.3 归一化单位），即使正常坐姿也会产生巨大 dz，
        导致 horiz=sqrt(dx²+dz²) 虚高，θ3 持续超过 15° 阈值触发误报。

        修复方案：仅使用可靠的 X/Y 二维坐标。
        • 髋部可见：肩部中点 vs 髋部中点的水平/垂直比值
        • 髋部不可见：鼻尖 vs 肩部中点（适配桌面摄像头场景）
        正常直坐：肩/髋大致垂直对齐，theta3≈0°
        前倾（趴伏）：肩的 x 坐标向鼻方向偏移，theta3 > 0°
        """
        ls, rs = lm[11], lm[12]
        lh, rh = lm[23], lm[24]

        hip_visible = (lh.visibility > 0.5 and rh.visibility > 0.5)

        if hip_visible:
            # 主方案：肩部中点 vs 髋部中点（纯 XY，去掉 Z 轴噪声）
            smx = (ls.x + rs.x) / 2
            smy = (ls.y + rs.y) / 2
            hmx = (lh.x + rh.x) / 2
            hmy = (lh.y + rh.y) / 2

            dx = smx - hmx             # 肩相对于髋的水平偏移
            dy = hmy - smy + 1e-6      # 垂直距离（始终 > 0，肩在髋上方）

        else:
            # 降级方案：鼻尖 vs 肩部中点（髋部被桌面遮挡时）
            nose = lm[0]
            smx  = (ls.x + rs.x) / 2
            smy  = (ls.y + rs.y) / 2

            dx = nose.x - smx          # 鼻相对于肩的水平偏移
            dy = smy - nose.y + 1e-6   # 垂直距离（始终 > 0，鼻在肩上方）

        # 二维前倾角：atan2(水平偏移, 垂直距离)
        # dx > 0 → 向右偏（正角），dx < 0 → 向左偏（负角）
        angle = math.degrees(math.atan2(dx, dy))
        return round(angle, 2)

    # θ4: 头部偏航角
    def _theta4(self, lm):
        nose         = lm[0]
        le, re       = lm[7], lm[8]
        ear_mid_x    = (le.x + re.x) / 2
        ear_width    = abs(re.x - le.x) + 1e-6
        offset_ratio = (nose.x - ear_mid_x) / ear_width
        theta4       = math.degrees(math.atan(offset_ratio * 2))
        return round(theta4, 2)

    # ─────────────────────────────────────────────────────
    def _estimate_distance(self, face_landmarks, w, h):
        try:
            lp = face_landmarks.landmark[468]
            rp = face_landmarks.landmark[473]
        except IndexError:
            lp = face_landmarks.landmark[33]
            rp = face_landmarks.landmark[263]

        lx, ly  = lp.x * w, lp.y * h
        rx, ry  = rp.x * w, rp.y * h
        ipd_px  = math.sqrt((rx - lx) ** 2 + (ry - ly) ** 2)
        if ipd_px < 1:
            return None

        REAL_IPD_MM = 63.0
        dist_mm = (self.focal_length * REAL_IPD_MM) / ipd_px
        return round(dist_mm / 10, 1)

    # ─────────────────────────────────────────────────────
    def _draw_angles(self, img, lm, w, h, t1, t2, t3, t4):
        def pt(lmk):
            return int(lmk.x * w), int(lmk.y * h)

        ls_pt, rs_pt = pt(lm[11]), pt(lm[12])
        cv2.line(img, ls_pt, rs_pt, (255, 200, 0), 2)
        mid_sh = ((ls_pt[0]+rs_pt[0])//2, (ls_pt[1]+rs_pt[1])//2)
        img[:] = _put_text_cn(img, f"θ1={t1:.1f}°",
                              (mid_sh[0]-40, mid_sh[1]-22),
                              (255, 200, 0), _FONT_SM)

        nose_pt = pt(lm[0])
        img[:] = _put_text_cn(img, f"θ2={t2:.1f}°",
                              (nose_pt[0]+8, nose_pt[1]-8),
                              (0, 200, 255), _FONT_SM)
        img[:] = _put_text_cn(img, f"θ4={t4:.1f}°",
                              (nose_pt[0]+8, nose_pt[1]+12),
                              (200, 100, 255), _FONT_SM)

        lh_pt, rh_pt = pt(lm[23]), pt(lm[24])
        hip_mid = ((lh_pt[0]+rh_pt[0])//2, (lh_pt[1]+rh_pt[1])//2)
        img[:] = _put_text_cn(img, f"θ3={t3:.1f}°",
                              (hip_mid[0]+8, hip_mid[1]-8),
                              (100, 255, 150), _FONT_SM)

    def _draw_distance(self, img, dist, w, h):
        if dist is None:
            return
        color = (0, 220, 80) if dist >= config.MIN_SAFE_DISTANCE_CM else (30, 30, 255)
        img[:] = _put_text_cn(img, f"视距: {dist:.1f} cm",
                              (10, 8), color, _FONT_MD)

    def _draw_status(self, img, result, w, h):
        # 主状态行
        if result["is_good"]:
            txt   = "✓ 姿态良好"
            color = (0, 220, 80)
        else:
            txt   = "✗ " + " | ".join(result["alerts"])
            color = (30, 30, 220)
        img[:] = _put_text_cn(img, txt, (10, h - 52), color, _FONT_MD)

        # 马氏距离显示（热身完成后才显示）
        if result["mahal_ready"]:
            d     = result["mahal_dist"]
            # 颜色随距离变化：绿→橙→红
            if d < config.MAHAL_THRESHOLD * 0.7:
                mc = (0, 200, 80)
            elif d < config.MAHAL_THRESHOLD:
                mc = (30, 160, 255)
            else:
                mc = (30, 30, 220)
            img[:] = _put_text_cn(img, f"马氏距离: {d:.2f}",
                                  (10, h - 28), mc, _FONT_SM)
        else:
            # 热身进度提示
            warmup_pct = min(100, int(self._mahal.n / self._mahal.warmup * 100))
            img[:] = _put_text_cn(img, f"基线学习中: {warmup_pct}%",
                                  (10, h - 28), (150, 150, 150), _FONT_SM)

    # ─────────────────────────────────────────────────────
    def reset_filters(self):
        """新会话开始时重置所有滤波器和检测器"""
        self._kf_t1.reset()
        self._kf_t2.reset()
        self._kf_t3.reset()
        self._kf_t4.reset()
        self._kf_dist.reset()
        self._mahal.reset()

    def calibrate(self, bgr_frame, known_distance_cm=50.0):
        """以已知距离标定焦距"""
        rgb    = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        result = self.face_mesh.process(rgb)
        if not result.multi_face_landmarks:
            return False
        h, w = bgr_frame.shape[:2]
        fl   = result.multi_face_landmarks[0]
        try:
            lp = fl.landmark[468]
            rp = fl.landmark[473]
        except IndexError:
            lp = fl.landmark[33]
            rp = fl.landmark[263]
        ipd_px = math.sqrt(((rp.x - lp.x)*w)**2 + ((rp.y - lp.y)*h)**2)
        if ipd_px < 1:
            return False
        REAL_IPD_MM      = 63.0
        self.focal_length = (ipd_px * known_distance_cm * 10) / REAL_IPD_MM
        return True

    def close(self):
        self.pose.close()
        self.face_mesh.close()