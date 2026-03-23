# gui/statistics_tab.py — 用眼习惯统计标签页（支持 uid 参数）

from datetime import date, timedelta
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QComboBox, QTextEdit,
    QSplitter, QSizePolicy
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from database.db_manager import DatabaseManager
from modules.statistics_module import (
    build_daily_figure, build_weekly_figure,
    build_longterm_figure, generate_advice
)


class StatsLoader(QThread):
    done = pyqtSignal(dict)

    def __init__(self, db: DatabaseManager, mode: str, uid: int,
                 user_age: int, api_key: str = ""):
        super().__init__()
        self.db       = db
        self.mode     = mode
        self.uid      = uid
        self.user_age = user_age
        self.api_key  = api_key

    def run(self):
        if self.mode == "daily":
            hourly = self.db.get_hourly_usage_today(self.uid)
            daily  = self.db.get_daily_stats(self.uid)
            daily["hourly"] = hourly
            self.done.emit({"mode": "daily", "daily": daily})
        elif self.mode == "weekly":
            weekly = self.db.get_weekly_stats(self.uid)
            self.done.emit({"mode": "weekly", "weekly": weekly})
        else:
            stats  = self.db.get_longterm_stats(self.uid, 30)
            advice = generate_advice(stats, self.user_age, self.api_key)
            self.done.emit({"mode": "longterm", "longterm": stats, "advice": advice})


class StatisticsTab(QWidget):
    def __init__(self, db: DatabaseManager, uid: int = 1,
                 api_key: str = "", parent=None):
        super().__init__(parent)
        self.db       = db
        self.uid      = uid
        self.api_key  = api_key
        self._loaders = []
        self._canvas  = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        ctrl = QHBoxLayout()
        title = QLabel("📊  用眼习惯统计")
        title.setObjectName("sectionTitle")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        ctrl.addWidget(title)
        ctrl.addStretch()

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["📅 今日日报", "📆 近7日周报", "📈 30日长期趋势"])
        self.mode_combo.setFixedWidth(180)
        ctrl.addWidget(self.mode_combo)

        self.refresh_btn = QPushButton("🔄  刷新")
        self.refresh_btn.setObjectName("accentBtn")
        self.refresh_btn.clicked.connect(self.load_stats)
        ctrl.addWidget(self.refresh_btn)
        root.addLayout(ctrl)

        splitter = QSplitter(Qt.Vertical)

        chart_container = QFrame()
        chart_container.setObjectName("card")
        self.chart_layout = QVBoxLayout(chart_container)
        self.chart_layout.setContentsMargins(8, 8, 8, 8)
        self.loading_lbl = QLabel("请点击「刷新」加载统计图表")
        self.loading_lbl.setAlignment(Qt.AlignCenter)
        self.loading_lbl.setObjectName("infoLabel")
        self.chart_layout.addWidget(self.loading_lbl)
        splitter.addWidget(chart_container)

        advice_container = QFrame()
        advice_container.setObjectName("card")
        adv_lay = QVBoxLayout(advice_container)
        adv_lay.setContentsMargins(10, 10, 10, 10)
        adv_title = QLabel("💡  个性化用眼建议")
        adv_title.setObjectName("sectionTitle")
        adv_lay.addWidget(adv_title)
        self.advice_text = QTextEdit()
        self.advice_text.setReadOnly(True)
        self.advice_text.setPlaceholderText("选择「30日长期趋势」后将自动生成个性化建议…")
        self.advice_text.setMaximumHeight(160)
        self.advice_text.setStyleSheet(
            "QTextEdit { background:#0D1117; border:none; font-size:12px;"
            " color:#E6EDF3; line-height:1.6; }")
        adv_lay.addWidget(self.advice_text)
        splitter.addWidget(advice_container)
        splitter.setSizes([500, 180])
        root.addWidget(splitter)

        self.summary_row = self._build_summary_row()
        root.addLayout(self.summary_row)

    def _build_summary_row(self):
        layout = QHBoxLayout()
        layout.setSpacing(10)
        self.sum_cards = {}
        cards = [
            ("today_time",   "⏱", "今日用眼", "—"),
            ("today_good",   "🪑", "坐姿良好率", "—"),
            ("today_dist",   "👁", "平均视距", "—"),
            ("today_points", "⭐", "今日积分", "—"),
        ]
        for key, icon, label, default in cards:
            card = QFrame()
            card.setObjectName("card")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 10, 12, 10)
            cl.setSpacing(2)
            row = QHBoxLayout()
            ic  = QLabel(icon); ic.setFont(QFont("Segoe UI Emoji", 14))
            lbl = QLabel(label); lbl.setObjectName("metricLabel")
            row.addWidget(ic); row.addWidget(lbl); row.addStretch()
            cl.addLayout(row)
            val = QLabel(default)
            val.setObjectName("metricValue")
            val.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
            cl.addWidget(val)
            self.sum_cards[key] = val
            layout.addWidget(card)
        return layout

    def load_stats(self):
        idx  = self.mode_combo.currentIndex()
        mode = ["daily", "weekly", "longterm"][idx]
        user = self.db.get_user(self.uid)
        age  = user.get("age", 10)

        self.refresh_btn.setEnabled(False)
        self.loading_lbl.setText("⏳  AI 建议生成中，请稍候…" if mode == "longterm"
                                  else "⏳  加载中…")
        self.loading_lbl.show()

        loader = StatsLoader(self.db, mode, self.uid, age, self.api_key)
        loader.done.connect(self._on_stats_loaded)
        loader.finished.connect(lambda: self.refresh_btn.setEnabled(True))
        self._loaders.append(loader)
        loader.start()
        self._refresh_summary()

    def _refresh_summary(self):
        daily  = self.db.get_daily_stats(self.uid)
        hourly = self.db.get_hourly_usage_today(self.uid)
        total_min = sum(hourly.values())
        h, m  = divmod(total_min, 60)
        self.sum_cards["today_time"].setText(f"{h:02d}:{m:02d}")
        self.sum_cards["today_good"].setText(f"{daily['good_ratio']:.1f}%")
        d = daily["avg_distance"]
        self.sum_cards["today_dist"].setText(f"{d:.1f} cm" if d else "—")
        pts = self.db.get_total_points(self.uid)
        self.sum_cards["today_points"].setText(str(pts))

    def _on_stats_loaded(self, data: dict):
        self.loading_lbl.hide()
        mode = data["mode"]
        if mode == "daily":
            fig = build_daily_figure(data["daily"])
        elif mode == "weekly":
            fig = build_weekly_figure(data["weekly"])
        else:
            fig = build_longterm_figure(data["longterm"])
            self.advice_text.setPlainText(data.get("advice", ""))

        if self._canvas:
            self.chart_layout.removeWidget(self._canvas)
            self._canvas.deleteLater()

        self._canvas = FigureCanvas(fig)
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.chart_layout.addWidget(self._canvas)
        self._canvas.draw()