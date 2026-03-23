# core/behavior_monitor.py — 行为监测 QThread

import time
import cv2
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker
from PyQt5.QtGui import QImage, QPixmap

from core.pose_analyzer import PoseAnalyzer
from core.voice_alert   import VoiceAlert
from database.db_manager import DatabaseManager
import config


class BehaviorMonitor(QThread):
    """
    后台摄像头采集 + 姿势分析线程。

    信号:
      frame_signal    (QPixmap)          每帧标注图
      status_signal   (dict)             分析结果（角度、距离、is_good）
      alert_signal    (str)              提醒类型
      session_signal  (dict)             会话统计（时长、积分）
      error_signal    (str)              错误信息
    """

    frame_signal   = pyqtSignal(QPixmap)
    status_signal  = pyqtSignal(dict)
    alert_signal   = pyqtSignal(str)
    session_signal = pyqtSignal(dict)
    error_signal   = pyqtSignal(str)

    def __init__(self, db: DatabaseManager, voice: VoiceAlert, parent=None):
        super().__init__(parent)
        self.db    = db
        self.voice = voice
        self._running   = False
        self._mutex     = QMutex()
        self._paused    = False

        # 会话数据
        self._session_id     = None
        self._session_start  = None
        self._user_id        = 1      # ← Bug 1 修复：记录当前用户 uid
        self._good_streak    = 0.0    # 连续良好秒数
        self._total_points   = 0

        # 采样计数
        self._last_record_ts = 0.0
        self._last_point_ts  = 0.0

        # 积分周期内良好帧统计
        self._good_frames  = 0
        self._total_frames = 0

        # 休息提醒
        self._rest_interval  = config.DEFAULT_REST_INTERVAL
        self._last_rest_ts   = 0.0

    # ── 控制接口 ─────────────────────────────────────────
    def start_session(self, user_id=1, age=10):
        self._user_id       = user_id          # ← Bug 1 修复：保存 uid
        rest_map = config.REST_INTERVAL_BY_AGE
        self._rest_interval = config.DEFAULT_REST_INTERVAL
        for (lo, hi), secs in rest_map.items():
            if lo <= age <= hi:
                self._rest_interval = secs
                break
        self._session_id    = self.db.start_session(user_id)
        self._session_start = time.time()
        self._good_streak   = 0.0
        self._last_rest_ts  = time.time()
        self._total_points  = self.db.get_total_points(user_id)
        self._good_frames   = 0
        self._total_frames  = 0

    def stop_session(self):
        if self._session_id and self._session_start:
            duration = int(time.time() - self._session_start)
            self.db.end_session(self._session_id, duration)
        self._session_id = None

    def pause(self, paused: bool):
        with QMutexLocker(self._mutex):
            self._paused = paused

    def stop(self):
        self._running = False

    # ── 主循环 ───────────────────────────────────────────
    def run(self):
        self._running = True
        analyzer = PoseAnalyzer()

        cap = cv2.VideoCapture(config.CAMERA_INDEX)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  config.FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, config.FPS)

        if not cap.isOpened():
            self.error_signal.emit("无法打开摄像头，请检查设备连接。")
            analyzer.close()
            return

        frame_interval = 1.0 / config.FPS

        while self._running:
            loop_start = time.time()

            with QMutexLocker(self._mutex):
                paused = self._paused

            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue

            frame = cv2.flip(frame, 1)   # 镜像

            if paused:
                # 暂停时只推送原始画面
                pix = self._bgr_to_pixmap(frame)
                self.frame_signal.emit(pix)
                time.sleep(frame_interval)
                continue

            # 分析
            result, annotated = analyzer.process(frame)

            # 发送帧
            pix = self._bgr_to_pixmap(annotated)
            self.frame_signal.emit(pix)

            # 发送状态
            self.status_signal.emit(result)

            # 报警
            for alert_type in result["alerts"]:
                self.alert_signal.emit(alert_type)
                self.voice.speak(alert_type)

            now = time.time()

            # 休息提醒
            if self._session_start and (now - self._last_rest_ts) >= self._rest_interval:
                self.alert_signal.emit("休息提醒")
                self.voice.speak("休息提醒")
                self._last_rest_ts = now

            # 数据库记录
            if self._session_id and (now - self._last_record_ts) >= config.RECORD_INTERVAL_SEC:
                if result["pose_ok"]:
                    self.db.insert_posture(
                        self._session_id,
                        result["theta1"] or 0,
                        result["theta2"] or 0,
                        result["theta3"] or 0,
                        result["theta4"] or 0,
                        result["distance_cm"] or 0,
                        result["is_good"]
                    )
                self._last_record_ts = now

            # 每帧累计良好帧数（用于积分周期统计）
            if result["pose_ok"] or result["face_ok"]:
                self._total_frames += 1
                if result["is_good"]:
                    self._good_frames += 1

            # 积分奖励（基于60秒窗口内良好帧占比）
            if self._session_id and (now - self._last_point_ts) >= 60:
                good_ratio = (self._good_frames / max(self._total_frames, 1))
                if good_ratio >= 0.8:   # 80%以上良好帧才给分
                    self._good_streak += 60
                    delta = config.POINTS_PER_GOOD_MINUTE
                    if self._good_streak >= config.POINTS_STREAK_THRESHOLD:
                        delta += config.POINTS_STREAK_BONUS
                        self._good_streak = 0
                        self.voice.speak("奖励积分")
                    self.db.add_points(delta, "良好用眼行为", self._user_id)  # ← Bug 1 修复
                    self._total_points += delta
                else:
                    self._good_streak = 0   # 良好率不足则连续清零
                # 重置本周期计数
                self._good_frames  = 0
                self._total_frames = 0
                self._last_point_ts = now

            # 会话统计信号
            if self._session_start:
                elapsed = int(now - self._session_start)
                self.session_signal.emit({
                    "elapsed"      : elapsed,
                    "total_points" : self._total_points,
                    "good_streak"  : int(self._good_streak),
                    "rest_in"      : max(0, int(self._rest_interval - (now - self._last_rest_ts))),
                })

            # 控制帧率
            elapsed_loop = time.time() - loop_start
            sleep_time   = frame_interval - elapsed_loop
            if sleep_time > 0:
                time.sleep(sleep_time)

        cap.release()
        analyzer.close()

    # ── 工具 ─────────────────────────────────────────────
    @staticmethod
    def _bgr_to_pixmap(bgr_frame) -> QPixmap:
        h, w, ch = bgr_frame.shape
        rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        return QPixmap.fromImage(qimg)