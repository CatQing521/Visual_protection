# gui/monitor_tab.py — 实时监测标签页

import time
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QFrame, QProgressBar, QSizePolicy,
    QGridLayout, QSpacerItem
)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QPixmap, QFont

import config


# ── 单指标卡片 ───────────────────────────────────────────
class MetricCard(QFrame):
    def __init__(self, icon: str, label: str, unit: str = "",
                 bar: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self._unit = unit

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(4)

        # 图标 + 标签
        row = QHBoxLayout()
        icon_lbl = QLabel(icon)
        icon_lbl.setFont(QFont("Segoe UI Emoji", 16))
        icon_lbl.setFixedWidth(30)
        name_lbl = QLabel(label)
        name_lbl.setObjectName("metricLabel")
        row.addWidget(icon_lbl)
        row.addWidget(name_lbl)
        row.addStretch()
        lay.addLayout(row)

        # 数值
        self.value_lbl = QLabel("—")
        self.value_lbl.setObjectName("metricValue")
        lay.addWidget(self.value_lbl)

        # 可选进度条
        if bar:
            self.bar = QProgressBar()
            self.bar.setRange(0, 100)
            self.bar.setValue(0)
            self.bar.setFixedHeight(8)
            lay.addWidget(self.bar)
        else:
            self.bar = None

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def set_value(self, val, color: str = None):
        if val is None:
            self.value_lbl.setText(f"—")
        else:
            self.value_lbl.setText(f"{val}{self._unit}")
        if color:
            self.value_lbl.setStyleSheet(f"color:{color};")
        if self.bar is not None:
            try:
                self.bar.setValue(int(float(str(val).replace(self._unit,""))))
            except Exception:
                pass


# ── 角度指示组件 ─────────────────────────────────────────
class AngleIndicator(QWidget):
    GOOD_COLOR = "#3FB950"
    WARN_COLOR = "#F0883E"
    BAD_COLOR  = "#F85149"

    def __init__(self, label, threshold, parent=None):
        super().__init__(parent)
        self._threshold = threshold
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(8)

        self.dot = QLabel("●")
        self.dot.setFont(QFont("Segoe UI Emoji", 10))
        self.dot.setStyleSheet(f"color:{self.GOOD_COLOR};")
        self.dot.setFixedWidth(16)

        lbl = QLabel(label)
        lbl.setStyleSheet("color:#8B949E;")
        lbl.setFixedWidth(100)

        self.val_lbl = QLabel("—")
        self.val_lbl.setStyleSheet("color:#E6EDF3;")

        lay.addWidget(self.dot)
        lay.addWidget(lbl)
        lay.addWidget(self.val_lbl)
        lay.addStretch()

    def update(self, angle):
        if angle is None:
            self.val_lbl.setText("—")
            self.dot.setStyleSheet(f"color:#484F58;")
            return
        a = abs(angle)
        self.val_lbl.setText(f"{angle:.1f}°")
        if a <= self._threshold * 0.7:
            color = self.GOOD_COLOR
        elif a <= self._threshold:
            color = self.WARN_COLOR
        else:
            color = self.BAD_COLOR
        self.dot.setStyleSheet(f"color:{color};")


# ── 主监测页 ─────────────────────────────────────────────
class MonitorTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._session_running = False
        self._elapsed = 0
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick_ui)
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)

        # ── 左：摄像头 ───────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(10)

        cam_lbl = QLabel("📷  实时画面")
        cam_lbl.setObjectName("sectionTitle")
        left.addWidget(cam_lbl)

        self.camera_lbl = QLabel()
        self.camera_lbl.setObjectName("cameraView")
        self.camera_lbl.setAlignment(Qt.AlignCenter)
        self.camera_lbl.setText("等待摄像头启动…\n\n请点击「开始监测」")
        self.camera_lbl.setMinimumSize(480, 360)
        self.camera_lbl.setScaledContents(False)
        left.addWidget(self.camera_lbl, 1)

        # 提醒横幅
        self.alert_banner = QLabel("  ✅  系统就绪，请开始监测")
        self.alert_banner.setObjectName("successLabel")
        self.alert_banner.setAlignment(Qt.AlignCenter)
        self.alert_banner.setWordWrap(True)
        left.addWidget(self.alert_banner)

        # 按钮行
        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("▶  开始监测")
        self.start_btn.setObjectName("primaryBtn")
        self.pause_btn = QPushButton("⏸  暂停")
        self.pause_btn.setEnabled(False)
        self.stop_btn  = QPushButton("⏹  停止")
        self.stop_btn.setObjectName("dangerBtn")
        self.stop_btn.setEnabled(False)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.pause_btn)
        btn_row.addWidget(self.stop_btn)
        left.addLayout(btn_row)

        root.addLayout(left, 3)

        # ── 右：状态面板 ─────────────────────────────
        right = QVBoxLayout()
        right.setSpacing(10)

        panel_lbl = QLabel("📊  实时状态")
        panel_lbl.setObjectName("sectionTitle")
        right.addWidget(panel_lbl)

        # 状态指示灯
        self.status_card = QFrame()
        self.status_card.setObjectName("card")
        sc_lay = QVBoxLayout(self.status_card)
        sc_lay.setSpacing(6)

        self.overall_lbl = QLabel("● 等待检测")
        self.overall_lbl.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        self.overall_lbl.setStyleSheet("color:#484F58;")
        self.overall_lbl.setAlignment(Qt.AlignCenter)
        sc_lay.addWidget(self.overall_lbl)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sc_lay.addWidget(sep)

        self.th1 = AngleIndicator("θ₁ 肩部水平", config.THETA1_MAX)
        self.th2 = AngleIndicator("θ₂ 头部俯仰", config.THETA2_MAX)
        self.th3 = AngleIndicator("θ₃ 躯干前倾", config.THETA3_MAX)
        self.th4 = AngleIndicator("θ₄ 头部偏航", config.THETA4_MAX)
        for w in [self.th1, self.th2, self.th3, self.th4]:
            sc_lay.addWidget(w)

        right.addWidget(self.status_card)

        # 指标卡片网格
        grid = QGridLayout()
        grid.setSpacing(8)
        self.dist_card    = MetricCard("👁", "视距",    " cm")
        self.time_card    = MetricCard("⏱", "用眼时长", "")
        self.points_card  = MetricCard("⭐", "今日积分", " 分")
        self.streak_card  = MetricCard("🔥", "连续良好", " s")
        self.rest_card    = MetricCard("💤", "休息倒计时", "")
        self.good_card    = MetricCard("🏆", "坐姿良好率", "%", bar=True)

        grid.addWidget(self.dist_card,   0, 0)
        grid.addWidget(self.time_card,   0, 1)
        grid.addWidget(self.points_card, 1, 0)
        grid.addWidget(self.streak_card, 1, 1)
        grid.addWidget(self.rest_card,   2, 0)
        grid.addWidget(self.good_card,   2, 1)
        right.addLayout(grid)

        right.addStretch()
        root.addLayout(right, 2)

    # ── Slots (由 MainWindow 连接) ──────────────────────
    @pyqtSlot(QPixmap)
    def on_frame(self, pix: QPixmap):
        scaled = pix.scaled(
            self.camera_lbl.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.camera_lbl.setPixmap(scaled)

    @pyqtSlot(dict)
    def on_status(self, result: dict):
        # 坐姿角度
        self.th1.update(result.get("theta1"))
        self.th2.update(result.get("theta2"))
        self.th3.update(result.get("theta3"))
        self.th4.update(result.get("theta4"))

        # 视距
        d = result.get("distance_cm")
        if d is not None:
            color = "#3FB950" if d >= config.MIN_SAFE_DISTANCE_CM else "#F85149"
            self.dist_card.set_value(f"{d:.1f}", color)

        # 整体状态灯
        if not result.get("pose_ok") and not result.get("face_ok"):
            self.overall_lbl.setText("● 未检测到人体")
            self.overall_lbl.setStyleSheet("color:#484F58;")
        elif result.get("is_good"):
            self.overall_lbl.setText("● 姿态良好")
            self.overall_lbl.setStyleSheet("color:#3FB950;")
        else:
            alerts = result.get("alerts", [])
            self.overall_lbl.setText("● " + " | ".join(alerts))
            self.overall_lbl.setStyleSheet("color:#F85149;")

    @pyqtSlot(str)
    def on_alert(self, alert_type: str):
        EMOJI = {
            "距离过近": "👁 距离过近！请距离屏幕50cm以上",
            "歪坐":     "↔ 检测到歪坐，请保持肩部水平",
            "低头":     "⬇ 检测到低头，请抬起头部",
            "趴伏/前倾":"⬆ 检测到身体前倾，请坐直",
            "歪头":     "↗ 检测到歪头，请保持头部端正",
            "休息提醒": "💤 已连续用眼较长时间，请休息一下！",
        }
        msg = EMOJI.get(alert_type, f"⚠ {alert_type}")
        self.alert_banner.setText(f"  ⚠  {msg}")
        self.alert_banner.setObjectName("alertLabel")
        self.alert_banner.setStyleSheet("")   # 触发 QSS 重算
        self.alert_banner.setProperty("class", "alertLabel")
        # 3秒后恢复
        QTimer.singleShot(3000, self._clear_alert)

    def _clear_alert(self):
        self.alert_banner.setText("  ✅  监测中…")
        self.alert_banner.setObjectName("successLabel")
        self.alert_banner.setStyleSheet("")

    @pyqtSlot(dict)
    def on_session(self, info: dict):
        self._elapsed = info.get("elapsed", 0)
        h, rem = divmod(self._elapsed, 3600)
        m, s   = divmod(rem, 60)
        self.time_card.set_value(f"{h:02d}:{m:02d}:{s:02d}")
        self.points_card.set_value(info.get("total_points", 0), "#F0883E")
        self.streak_card.set_value(info.get("good_streak", 0))
        rest = info.get("rest_in", 0)
        rm, rs = divmod(rest, 60)
        self.rest_card.set_value(f"{rm:02d}:{rs:02d}")

    def update_good_ratio(self, ratio_pct: float):
        self.good_card.set_value(f"{ratio_pct:.1f}")
        if self.good_card.bar:
            self.good_card.bar.setValue(int(ratio_pct))

    # ── 按钮状态 ─────────────────────────────────────────
    def set_session_running(self, running: bool, paused: bool = False):
        self._session_running = running
        self.start_btn.setEnabled(not running)
        self.pause_btn.setEnabled(running)
        self.stop_btn.setEnabled(running)
        if running:
            self.pause_btn.setText("⏸  暂停" if not paused else "▶  继续")
        if running and not self._timer.isActive():
            self._timer.start(1000)
        elif not running:
            self._timer.stop()

    def _tick_ui(self):
        pass   # 时间显示由 session_signal 驱动，此处可做其他周期任务