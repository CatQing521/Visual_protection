# gui/main_window.py — 主窗口（支持多账号 / 多孩子切换）

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QStackedWidget, QFrame,
    QStatusBar, QSizePolicy, QMessageBox, QComboBox,
    QAction, QMenu, QToolButton
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QIcon

from database.db_manager   import DatabaseManager
from core.behavior_monitor import BehaviorMonitor
from core.voice_alert      import VoiceAlert
from gui.monitor_tab       import MonitorTab
from gui.statistics_tab    import StatisticsTab
from gui.rewards_tab       import RewardsTab
from gui.parent_tab        import ParentTab
from gui.ai_chat_tab       import AIChatTab
from gui.notifications_dialog import NotificationsDialog
from gui.profile_tab          import ProfileTab
import config


class MainWindow(QMainWindow):
    def __init__(self, db: DatabaseManager, account: dict):
        super().__init__()
        self.db        = db
        self.account   = account
        self.is_parent = (account.get("role") == "parent")

        # 当前选中的孩子档案
        if self.is_parent:
            children = self.db.get_children(account["id"])
            self.current_user = children[0] if children else {
                "id": 0, "name": "小朋友", "age": 10, "avatar": "🧒"}
        else:
            # 儿童账号：通过 child_account_id 找到自己的档案
            user = self.db.get_user_by_child_account(account["id"])
            self.current_user = user if user else {
                "id": 0, "name": account.get("nickname", "小朋友"),
                "age": 10, "avatar": "🧒"}

        self.voice = VoiceAlert()
        self.voice.start()
        self.monitor_thread: BehaviorMonitor = None
        self._paused = False

        self.setWindowTitle("VisionGuard — 儿童近视风险预防系统")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)

        self._build_ui()
        self._connect_signals()
        self._refresh_status_bar()
        self._update_child_combo()

        # 定时刷新状态栏
        self._sb_timer = QTimer()
        self._sb_timer.timeout.connect(self._refresh_status_bar)
        self._sb_timer.start(10000)

        # 儿童账号：延迟500ms弹出关联申请通知
        if not self.is_parent:
            QTimer.singleShot(500, self._check_link_notifications)

    # ── UI 构建 ───────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        main_lay = QVBoxLayout(central)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        main_lay.addWidget(self._build_topbar())

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        content.addWidget(self._build_sidebar())
        content.addWidget(self._build_stack())
        main_lay.addLayout(content, 1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

    def _build_topbar(self):
        bar = QWidget()
        bar.setObjectName("topBar")
        bar.setFixedHeight(52)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 20, 0)
        lay.setSpacing(10)

        # Logo
        logo_lbl = QLabel("👁")
        logo_lbl.setFont(QFont("Segoe UI Emoji", 22))
        title_lbl = QLabel("VisionGuard")
        title_lbl.setObjectName("title")
        subtitle_lbl = QLabel("儿童近视风险预防系统")
        subtitle_lbl.setObjectName("subtitle")
        lay.addWidget(logo_lbl)
        lay.addWidget(title_lbl)
        lay.addWidget(subtitle_lbl)
        lay.addStretch()

        # ── 孩子切换下拉（仅家长可见）────────────────
        if self.is_parent:
            child_icon = QLabel("🧒")
            child_icon.setFont(QFont("Segoe UI Emoji", 14))
            lay.addWidget(child_icon)

            self.child_combo = QComboBox()
            self.child_combo.setFixedHeight(32)
            self.child_combo.setMinimumWidth(130)
            self.child_combo.setStyleSheet("""
                QComboBox {
                    background:#1F6FEB22; border:1px solid #1F6FEB;
                    border-radius:6px; padding:0 10px;
                    color:#E6EDF3; font-weight:bold; font-size:12px;
                }
                QComboBox::drop-down { border:none; }
                QComboBox QAbstractItemView {
                    background:#161B22; color:#E6EDF3;
                    selection-background-color:#1F6FEB;
                }
            """)
            self.child_combo.currentIndexChanged.connect(self._on_child_selected)
            lay.addWidget(self.child_combo)
        else:
            self.child_combo = None

        # 积分显示
        self.topbar_pts_lbl = QLabel()
        self.topbar_pts_lbl.setStyleSheet(
            "background:#1F6FEB; border-radius:10px;"
            " padding:3px 10px; color:#fff; font-weight:bold;")
        lay.addWidget(self.topbar_pts_lbl)

        # 账号菜单按钮
        self.account_btn = QToolButton()
        self.account_btn.setStyleSheet("""
            QToolButton {
                background:#161B22; border:1px solid #30363D;
                border-radius:8px; padding:4px 10px;
                color:#E6EDF3; font-size:12px;
            }
            QToolButton:hover { background:#21262D; }
            QToolButton::menu-indicator { image: none; }
        """)
        self.account_btn.setPopupMode(QToolButton.InstantPopup)

        acct_menu = QMenu(self)
        acct_menu.setStyleSheet("""
            QMenu { background:#161B22; border:1px solid #30363D;
                    color:#E6EDF3; border-radius:8px; }
            QMenu::item { padding:8px 20px; }
            QMenu::item:selected { background:#1F6FEB; border-radius:4px; }
        """)
        logout_act = QAction("🚪  退出登录", self)
        logout_act.triggered.connect(self._logout)
        acct_menu.addAction(logout_act)
        self.account_btn.setMenu(acct_menu)
        lay.addWidget(self.account_btn)

        self._refresh_topbar()
        return bar

    def _build_sidebar(self):
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(180)
        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(0, 10, 0, 10)
        lay.setSpacing(2)

        nav_items = [
            ("📷", "实时监测", 0),
            ("📊", "用眼统计", 1),
            ("🎁", "积分奖励", 2),
            ("🤖", "AI 助手",  4),
            ("👤", "个人中心", 5),
        ]
        # 只有家长看到配置页
        if self.is_parent:
            nav_items.append(("⚙", "家长配置", 3))

        self._nav_btns = []
        for icon, label, idx in nav_items:
            btn = QPushButton(f"  {icon}  {label}")
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.setFont(QFont("Microsoft YaHei", 12))
            btn.clicked.connect(lambda c, i=idx: self._switch_tab(i))
            lay.addWidget(btn)
            self._nav_btns.append(btn)

        lay.addStretch()

        ver_lbl = QLabel("v2.0.0  |  MediaPipe")
        ver_lbl.setObjectName("subtitle")
        ver_lbl.setAlignment(Qt.AlignCenter)
        ver_lbl.setWordWrap(True)
        lay.addWidget(ver_lbl)

        self._nav_btns[0].setChecked(True)
        return sidebar

    def _build_stack(self):
        self.stack = QStackedWidget()
        uid = self.current_user["id"]
        account_id = self.account["id"]

        self.monitor_tab    = MonitorTab()
        self.statistics_tab = StatisticsTab(
            self.db, uid,
            getattr(config, "DEEPSEEK_API_KEY", ""))
        self.rewards_tab    = RewardsTab(self.db, uid)
        self.parent_tab     = ParentTab(self.db, account_id,
                                        uid, self.account) if self.is_parent else QWidget()
        child_name = self.current_user.get("name", "小朋友")
        self.ai_chat_tab    = AIChatTab(
            is_parent=self.is_parent,
            api_key=getattr(config, "DEEPSEEK_API_KEY", ""),
            child_name=child_name,
        )
        self.profile_tab = ProfileTab(
            self.db, self.account,
            current_user=self.current_user if not self.is_parent else None,
        )

        self.stack.addWidget(self.monitor_tab)    # 0
        self.stack.addWidget(self.statistics_tab) # 1
        self.stack.addWidget(self.rewards_tab)    # 2
        self.stack.addWidget(self.parent_tab)     # 3
        self.stack.addWidget(self.ai_chat_tab)    # 4
        self.stack.addWidget(self.profile_tab)    # 5

        if self.is_parent:
            self.parent_tab.settings_changed.connect(self._apply_settings)
            self.parent_tab.children_changed.connect(self._on_children_changed)
            self.parent_tab.children_panel.child_selected.connect(
                self._on_child_selected_by_id)
        self.profile_tab.account_updated.connect(self._on_account_updated)

        return self.stack

    # ── 孩子切换 ─────────────────────────────────────────
    def _update_child_combo(self):
        if not self.child_combo:
            return
        self.child_combo.blockSignals(True)
        self.child_combo.clear()
        children = self.db.get_children(self.account["id"])
        for c in children:
            self.child_combo.addItem(
                f"{c.get('avatar','🧒')} {c['name']}（{c['age']}岁）", c["id"])
        # 选中当前孩子
        for i in range(self.child_combo.count()):
            if self.child_combo.itemData(i) == self.current_user["id"]:
                self.child_combo.setCurrentIndex(i)
                break
        self.child_combo.blockSignals(False)

    def _on_child_selected(self, index: int):
        if not self.child_combo or index < 0:
            return
        child_id = self.child_combo.itemData(index)
        if child_id == self.current_user["id"]:
            return
        if self.monitor_thread and self.monitor_thread.isRunning():
            QMessageBox.warning(self, "请先停止监测",
                                "切换孩子档案前请先停止当前监测会话。")
            self._update_child_combo()
            return
        self.current_user = self.db.get_user(child_id)
        self._rebuild_tabs()
        self._refresh_topbar()
        self.status_bar.showMessage(f"已切换到：{self.current_user['name']}")

    def _on_child_selected_by_id(self, child_id: int):
        """孩子卡片「切换」按钮触发，直接用 child_id 切换"""
        if child_id == self.current_user["id"]:
            return
        if self.monitor_thread and self.monitor_thread.isRunning():
            QMessageBox.warning(self, "请先停止监测",
                                "切换孩子档案前请先停止当前监测会话。")
            return
        self.current_user = self.db.get_user(child_id)
        self._rebuild_tabs()
        self._update_child_combo()
        self._refresh_topbar()
        self.status_bar.showMessage(f"已切换到：{self.current_user['name']}")

    def _rebuild_tabs(self):
        """切换孩子后重建统计/奖励/家长页（个人中心不重建，属于账号级别）"""
        uid        = self.current_user["id"]
        account_id = self.account["id"]
        cur_idx    = self.stack.currentIndex()

        for tab in [self.statistics_tab, self.rewards_tab,
                    self.parent_tab, self.ai_chat_tab]:
            self.stack.removeWidget(tab)
            tab.deleteLater()

        child_name = self.current_user.get("name", "小朋友")
        self.statistics_tab = StatisticsTab(
            self.db, uid,
            getattr(config, "DEEPSEEK_API_KEY", ""))
        self.rewards_tab    = RewardsTab(self.db, uid)
        self.parent_tab     = ParentTab(self.db, account_id,
                                        uid, self.account) if self.is_parent else QWidget()
        self.ai_chat_tab    = AIChatTab(
            is_parent=self.is_parent,
            api_key=getattr(config, "DEEPSEEK_API_KEY", ""),
            child_name=child_name,
        )
        self.stack.insertWidget(1, self.statistics_tab)
        self.stack.insertWidget(2, self.rewards_tab)
        self.stack.insertWidget(3, self.parent_tab)
        self.stack.insertWidget(4, self.ai_chat_tab)
        # profile_tab 保留在索引 5，无需重建

        if self.is_parent:
            self.parent_tab.settings_changed.connect(self._apply_settings)
            self.parent_tab.children_changed.connect(self._on_children_changed)
            self.parent_tab.children_panel.child_selected.connect(
                self._on_child_selected_by_id)

        self.stack.setCurrentIndex(cur_idx)

    def _on_children_changed(self):
        """孩子列表变化（新增/删除）"""
        self._update_child_combo()
        children = self.db.get_children(self.account["id"])
        # 若当前孩子已被删除，切换到第一个
        ids = [c["id"] for c in children]
        if self.current_user["id"] not in ids and children:
            self.current_user = children[0]
            self._update_child_combo()
            self._rebuild_tabs()

    # ── 导航 ─────────────────────────────────────────────
    def _switch_tab(self, idx: int):
        for i, btn in enumerate(self._nav_btns):
            btn.setChecked(False)
        # 找到对应按钮并高亮
        nav_items = [("📷", 0), ("📊", 1), ("🎁", 2), ("🤖", 4), ("👤", 5), ("⚙", 3)]
        for i, btn in enumerate(self._nav_btns):
            if i < len(nav_items) and nav_items[i][1] == idx:
                btn.setChecked(True)
                break
        self.stack.setCurrentIndex(idx)
        if idx == 2:
            self.rewards_tab.refresh()
        if idx == 5:
            self.profile_tab.refresh()
        self._refresh_topbar()

    # ── 监测控制 ─────────────────────────────────────────
    def _connect_signals(self):
        self.monitor_tab.start_btn.clicked.connect(self._start_monitor)
        self.monitor_tab.pause_btn.clicked.connect(self._pause_monitor)
        self.monitor_tab.stop_btn.clicked.connect(self._stop_monitor)

    def _start_monitor(self):
        if self.monitor_thread and self.monitor_thread.isRunning():
            return
        uid = self.current_user["id"]
        age = self.current_user.get("age", 10)

        self.monitor_thread = BehaviorMonitor(self.db, self.voice)
        self.monitor_thread.start_session(user_id=uid, age=age)
        self.monitor_thread.frame_signal.connect(self.monitor_tab.on_frame)
        self.monitor_thread.status_signal.connect(self.monitor_tab.on_status)
        self.monitor_thread.alert_signal.connect(self.monitor_tab.on_alert)
        self.monitor_thread.session_signal.connect(self.monitor_tab.on_session)
        self.monitor_thread.error_signal.connect(self._on_camera_error)

        self._paused = False
        self.monitor_thread.start()
        self.monitor_tab.set_session_running(True)
        self.status_bar.showMessage(
            f"监测中…  当前孩子：{self.current_user['name']}")

    def _pause_monitor(self):
        if not self.monitor_thread:
            return
        self._paused = not self._paused
        self.monitor_thread.pause(self._paused)
        self.monitor_tab.set_session_running(True, self._paused)
        self.status_bar.showMessage("已暂停" if self._paused else "监测中…")

    def _stop_monitor(self):
        if not self.monitor_thread:
            return
        self.monitor_thread.stop_session()
        self.monitor_thread.stop()
        self.monitor_thread.wait(3000)
        self.monitor_thread = None
        self._paused = False
        self.monitor_tab.set_session_running(False)
        self.monitor_tab.camera_lbl.clear()
        self.monitor_tab.camera_lbl.setText("监测已停止\n点击「开始监测」重新启动")
        self.status_bar.showMessage("监测已停止")
        self._refresh_topbar()

    def _on_account_updated(self, account: dict):
        """个人中心修改昵称后同步刷新顶栏"""
        self.account = account
        self._refresh_topbar()

    def _on_camera_error(self, msg: str):
        QMessageBox.critical(self, "摄像头错误", msg)
        self.monitor_tab.set_session_running(False)

    # ── 设置应用 ─────────────────────────────────────────
    def _apply_settings(self):
        s = self.db.get_all_settings(self.account["id"])
        if "theta1_max" in s: config.THETA1_MAX = float(s["theta1_max"])
        if "theta2_max" in s: config.THETA2_MAX = float(s["theta2_max"])
        if "theta3_max" in s: config.THETA3_MAX = float(s["theta3_max"])
        if "theta4_max" in s: config.THETA4_MAX = float(s["theta4_max"])
        if "min_distance" in s: config.MIN_SAFE_DISTANCE_CM = int(s["min_distance"])
        if "warn_distance" in s: config.WARN_DISTANCE_CM = int(s["warn_distance"])
        self._refresh_topbar()

    # ── 顶栏刷新 ─────────────────────────────────────────
    def _refresh_topbar(self):
        nick = self.account.get("nickname") or self.account.get("username", "用户")
        role_icon = "👨\u200d👩\u200d👧" if self.is_parent else "🧒"
        self.account_btn.setText(f"{role_icon}  {nick}  ▾")

        uid = self.current_user["id"]
        pts = self.db.get_total_points(uid)
        self.topbar_pts_lbl.setText(f"⭐ {pts} 积分")

    def _refresh_status_bar(self):
        self._refresh_topbar()
        uid = self.current_user["id"]
        pts = self.db.get_total_points(uid)
        name = self.current_user.get("name", "")
        if self.monitor_thread and self.monitor_thread.isRunning():
            self.status_bar.showMessage(f"监测中…  {name}  积分：{pts}")
        else:
            self.status_bar.showMessage(f"就绪  |  {name}  总积分：{pts}")

    # ── 退出登录 ─────────────────────────────────────────
    def _logout(self):
        if self.monitor_thread and self.monitor_thread.isRunning():
            ans = QMessageBox.question(
                self, "确认退出",
                "监测正在进行中，退出登录将停止监测。\n确定要退出吗？",
                QMessageBox.Yes | QMessageBox.No)
            if ans != QMessageBox.Yes:
                return
            self._stop_monitor()
        self._sb_timer.stop()
        self.voice.stop()
        self.hide()
        # 用 QTimer 延迟到当前事件处理完毕后再创建登录窗口
        # 避免在槽函数调用栈中同时销毁/创建原生窗口导致 0xC0000409 崩溃
        from main import restart_to_login
        QTimer.singleShot(0, restart_to_login)
        QTimer.singleShot(100, self.close)

    # ── 儿童关联通知 ─────────────────────────────────────
    def _check_link_notifications(self):
        pending = self.db.get_pending_requests(self.account["id"])
        if not pending:
            return
        dlg = NotificationsDialog(self.db, self.account["id"], self)
        dlg.accepted_link.connect(self._on_link_accepted)
        dlg.exec_()

    def _on_link_accepted(self):
        """孩子接受关联后，刷新当前用户档案"""
        user = self.db.get_user_by_child_account(self.account["id"])
        if user:
            self.current_user = user
            self._refresh_topbar()
            self.status_bar.showMessage("✅ 已成功关联到家长账号")

    def closeEvent(self, event):
        if self.monitor_thread and self.monitor_thread.isRunning():
            self._stop_monitor()
        self.voice.stop()
        event.accept()