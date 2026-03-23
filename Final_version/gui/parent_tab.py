# gui/parent_tab.py — 家长配置（含多孩子管理）

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QLineEdit, QSpinBox,
    QDoubleSpinBox, QGroupBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialog, QFormLayout, QDialogButtonBox,
    QMessageBox, QCheckBox, QComboBox, QScrollArea,
    QSizePolicy, QTabWidget
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from database.db_manager import DatabaseManager
import config

AVATARS = ["🧒", "👦", "👧", "🧑", "🎓", "⭐", "🌟", "🦁", "🐼", "🐧"]


# ── 添加/编辑孩子档案对话框 ─────────────────────────────
class ChildDialog(QDialog):
    def __init__(self, parent=None, child=None):
        super().__init__(parent)
        self.setWindowTitle("添加孩子" if child is None else "编辑孩子档案")
        self.setMinimumWidth(340)
        self._build(child)

    def _build(self, child):
        lay = QFormLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(20, 20, 20, 20)

        # 头像选择
        self.avatar_combo = QComboBox()
        for a in AVATARS:
            self.avatar_combo.addItem(a)
        if child:
            idx = AVATARS.index(child.get("avatar", "🧒")) \
                  if child.get("avatar", "🧒") in AVATARS else 0
            self.avatar_combo.setCurrentIndex(idx)
        lay.addRow("头像：", self.avatar_combo)

        self.name_edit = QLineEdit(child["name"] if child else "")
        self.name_edit.setPlaceholderText("孩子姓名")
        lay.addRow("姓名：", self.name_edit)

        self.age_spin = QSpinBox()
        self.age_spin.setRange(4, 18)
        self.age_spin.setSuffix(" 岁")
        self.age_spin.setValue(child["age"] if child else 8)
        lay.addRow("年龄：", self.age_spin)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addRow(btns)

    def values(self):
        return (
            self.name_edit.text().strip(),
            self.age_spin.value(),
            self.avatar_combo.currentText(),
        )


# ── 添加/编辑奖励对话框 ─────────────────────────────────
class RewardDialog(QDialog):
    def __init__(self, parent=None, reward=None):
        super().__init__(parent)
        self.setWindowTitle("添加奖励" if reward is None else "编辑奖励")
        self.setMinimumWidth(360)
        self._build(reward)

    def _build(self, reward):
        lay = QFormLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(20, 20, 20, 20)

        self.name_edit = QLineEdit(reward["name"] if reward else "")
        self.name_edit.setPlaceholderText("如：🎮 游戏时间")
        lay.addRow("奖励名称：", self.name_edit)

        self.desc_edit = QLineEdit(reward.get("description", "") if reward else "")
        self.desc_edit.setPlaceholderText("简短描述（可选）")
        lay.addRow("描述：", self.desc_edit)

        self.pts_spin = QSpinBox()
        self.pts_spin.setRange(10, 9999)
        self.pts_spin.setSingleStep(10)
        self.pts_spin.setValue(reward["points_needed"] if reward else 100)
        lay.addRow("所需积分：", self.pts_spin)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addRow(btns)

    def values(self):
        return (
            self.name_edit.text().strip(),
            self.desc_edit.text().strip(),
            self.pts_spin.value()
        )


# ── 孩子管理面板 ─────────────────────────────────────────
class ChildrenPanel(QWidget):
    child_selected  = pyqtSignal(int)
    children_changed = pyqtSignal()

    def __init__(self, db: DatabaseManager, parent_account_id: int,
                 current_uid: int, parent=None):
        super().__init__(parent)
        self.db                = db
        self.parent_account_id = parent_account_id
        self.current_uid       = current_uid
        self._build()
        self._load()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # ── 顶部：已关联孩子 ─────────────────────────
        hdr = QHBoxLayout()
        title = QLabel("👨‍👩‍👧  孩子档案管理")
        title.setObjectName("sectionTitle")
        title.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        hdr.addWidget(title)
        hdr.addStretch()
        add_btn = QPushButton("➕  手动创建档案")
        add_btn.setObjectName("primaryBtn")
        add_btn.clicked.connect(self._add_child)
        hdr.addWidget(add_btn)
        lay.addLayout(hdr)

        # 孩子卡片区（可滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setFixedHeight(200)
        self.cards_widget = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_widget)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(6)
        self.cards_layout.addStretch()
        scroll.setWidget(self.cards_widget)
        lay.addWidget(scroll)

        # ── 搜索关联儿童账号 ─────────────────────────
        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#30363D;")
        lay.addWidget(sep)

        link_title = QLabel("🔗  关联儿童账号")
        link_title.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        link_title.setStyleSheet("color:#58A6FF;")
        lay.addWidget(link_title)

        desc = QLabel("输入孩子注册时的用户名，发送关联申请，孩子登录后确认即可。")
        desc.setStyleSheet("color:#8B949E; font-size:11px;")
        desc.setWordWrap(True)
        lay.addWidget(desc)

        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("输入孩子的用户名…")
        self.search_edit.setFixedHeight(36)
        self.search_edit.returnPressed.connect(self._send_link_request)
        search_row.addWidget(self.search_edit, 1)

        send_btn = QPushButton("发送申请")
        send_btn.setObjectName("primaryBtn")
        send_btn.setFixedHeight(36)
        send_btn.clicked.connect(self._send_link_request)
        search_row.addWidget(send_btn)
        lay.addLayout(search_row)

        self.link_result_lbl = QLabel("")
        self.link_result_lbl.setWordWrap(True)
        self.link_result_lbl.setStyleSheet("font-size:11px;")
        lay.addWidget(self.link_result_lbl)

        # ── 已发出的申请状态 ─────────────────────────
        self.requests_title = QLabel("📤  已发出的申请")
        self.requests_title.setFont(QFont("Microsoft YaHei", 11))
        self.requests_title.setStyleSheet("color:#8B949E;")
        lay.addWidget(self.requests_title)

        self.requests_widget = QWidget()
        self.requests_layout = QVBoxLayout(self.requests_widget)
        self.requests_layout.setContentsMargins(0, 0, 0, 0)
        self.requests_layout.setSpacing(4)
        lay.addWidget(self.requests_widget)

    def _load(self):
        # 清空孩子卡片
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        children = self.db.get_children(self.parent_account_id)
        if not children:
            empty = QLabel("暂无孩子档案，请手动创建或通过关联申请添加")
            empty.setStyleSheet("color:#484F58; font-size:11px; padding:8px;")
            empty.setWordWrap(True)
            self.cards_layout.insertWidget(0, empty)
        else:
            for c in children:
                self.cards_layout.insertWidget(
                    self.cards_layout.count() - 1,
                    self._make_card(c))

        # 刷新申请状态
        self._load_requests()

    def _load_requests(self):
        while self.requests_layout.count():
            item = self.requests_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        requests = self.db.get_sent_requests(self.parent_account_id)
        if not requests:
            self.requests_title.hide()
            return

        self.requests_title.show()
        STATUS_STYLE = {
            "pending":  ("⏳ 等待确认", "#F0883E"),
            "accepted": ("✅ 已接受",   "#3FB950"),
            "rejected": ("❌ 已拒绝",   "#F85149"),
        }
        for req in requests:
            row = QFrame()
            row.setStyleSheet(
                "background:#161B22; border-radius:6px; padding:2px;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(10, 6, 10, 6)

            name = req.get("nickname") or req["username"]
            name_lbl = QLabel(f"🧒 {name}（{req['username']}）")
            name_lbl.setStyleSheet("color:#E6EDF3; font-size:11px;")

            status_txt, color = STATUS_STYLE.get(
                req["status"], (req["status"], "#8B949E"))
            status_lbl = QLabel(status_txt)
            status_lbl.setStyleSheet(f"color:{color}; font-size:11px;")

            rl.addWidget(name_lbl, 1)
            rl.addWidget(status_lbl)
            self.requests_layout.addWidget(row)

    def _make_card(self, child: dict) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        is_current = (child["id"] == self.current_uid)
        if is_current:
            card.setStyleSheet(
                "QFrame#card { border:1.5px solid #1F6FEB; border-radius:10px; }")

        lay = QHBoxLayout(card)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        avatar_lbl = QLabel(child.get("avatar", "🧒"))
        avatar_lbl.setFont(QFont("Segoe UI Emoji", 22))
        avatar_lbl.setFixedWidth(38)
        lay.addWidget(avatar_lbl)

        info = QVBoxLayout()
        name_lbl = QLabel(child["name"])
        name_lbl.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        name_lbl.setStyleSheet("color:#E6EDF3;")

        sub = f"{child['age']} 岁"
        if child.get("child_account_id"):
            sub += "  ·  🔗 账号关联"
        age_lbl = QLabel(sub)
        age_lbl.setStyleSheet("color:#8B949E; font-size:10px;")

        pts = self.db.get_total_points(child["id"])
        pts_lbl = QLabel(f"⭐ {pts} 积分")
        pts_lbl.setStyleSheet("color:#F0883E; font-size:10px;")

        info.addWidget(name_lbl)
        info.addWidget(age_lbl)
        info.addWidget(pts_lbl)
        lay.addLayout(info, 1)

        if is_current:
            cur_tag = QLabel("✔ 当前")
            cur_tag.setStyleSheet(
                "background:#1F6FEB; border-radius:6px;"
                " padding:2px 8px; color:#fff; font-size:10px;")
            lay.addWidget(cur_tag)
        else:
            # ── 切换按钮 ──────────────────────────────
            switch_btn = QPushButton("切 换")
            switch_btn.setFixedSize(56, 28)
            switch_btn.setStyleSheet("""
                QPushButton {
                    background: #1F6FEB22;
                    border: 1px solid #1F6FEB;
                    border-radius: 6px;
                    color: #58A6FF;
                    font-size: 11px;
                    font-weight: bold;
                }
                QPushButton:hover { background: #1F6FEB55; }
            """)
            switch_btn.clicked.connect(
                lambda: self.child_selected.emit(child["id"]))
            lay.addWidget(switch_btn)

        edit_btn = QPushButton("✏️")
        edit_btn.setFixedSize(30, 30)
        edit_btn.clicked.connect(lambda: self._edit_child(child["id"]))
        lay.addWidget(edit_btn)

        if not is_current:
            del_btn = QPushButton("🗑️")
            del_btn.setFixedSize(30, 30)
            del_btn.setObjectName("dangerBtn")
            del_btn.clicked.connect(
                lambda: self._del_child(child["id"], child["name"]))
            lay.addWidget(del_btn)

        return card

    def _send_link_request(self):
        username = self.search_edit.text().strip()
        if not username:
            return

        child_acct = self.db.search_child_account(username)
        if not child_acct:
            self._set_link_result(
                f"❌  未找到儿童账号「{username}」，请确认用户名正确且账号类型为「儿童账号」",
                "#F85149")
            return

        result = self.db.send_link_request(
            self.parent_account_id, child_acct["id"])

        messages = {
            "ok":              ("✅  申请已发送，等待孩子登录后确认",        "#3FB950"),
            "already_linked":  ("ℹ️  该孩子已被关联到某个家长账号",          "#F0883E"),
            "already_pending": ("ℹ️  您已向该孩子发送过申请，请等待确认",    "#F0883E"),
            "already_accepted":("✅  该孩子已接受您的关联申请",              "#3FB950"),
            "already_rejected":("❌  该孩子已拒绝您的申请，无法重复发送",    "#F85149"),
        }
        msg, color = messages.get(result, (f"未知状态：{result}", "#8B949E"))
        self._set_link_result(msg, color)

        if result == "ok":
            self.search_edit.clear()
            self._load_requests()

    def _set_link_result(self, msg: str, color: str):
        self.link_result_lbl.setText(msg)
        self.link_result_lbl.setStyleSheet(f"color:{color}; font-size:11px;")

    def _add_child(self):
        children = self.db.get_children(self.parent_account_id)
        if len(children) >= 8:
            QMessageBox.information(self, "提示", "最多支持8个孩子档案。")
            return
        dlg = ChildDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            name, age, avatar = dlg.values()
            if name:
                self.db.add_child(self.parent_account_id, name, age, avatar)
                self._load()
                self.children_changed.emit()

    def _edit_child(self, child_id: int):
        child = self.db.get_user(child_id)
        dlg = ChildDialog(self, child)
        if dlg.exec_() == QDialog.Accepted:
            name, age, avatar = dlg.values()
            if name:
                self.db.update_user(name, age, avatar, child_id)
                self._load()
                self.children_changed.emit()

    def _del_child(self, child_id: int, child_name: str):
        ans = QMessageBox.question(
            self, "确认删除",
            f"确定删除「{child_name}」的所有档案和数据吗？\n此操作不可撤销！",
            QMessageBox.Yes | QMessageBox.No)
        if ans == QMessageBox.Yes:
            self.db.delete_child(child_id, self.parent_account_id)
            self._load()
            self.children_changed.emit()

    def refresh(self, current_uid: int = None):
        if current_uid is not None:
            self.current_uid = current_uid
        self._load()


# ── 家长配置主页 ─────────────────────────────────────────
class ParentTab(QWidget):
    settings_changed = pyqtSignal()
    children_changed = pyqtSignal()

    def __init__(self, db: DatabaseManager, account_id: int,
                 current_uid: int, account: dict, parent=None):
        super().__init__(parent)
        self.db          = db
        self.account_id  = account_id
        self.current_uid = current_uid
        self.account     = account
        self._build_ui()
        self._load_all()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)

        # ── 左列 ─────────────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(12)

        # 孩子管理面板
        self.children_panel = ChildrenPanel(
            self.db, self.account_id, self.current_uid)
        self.children_panel.children_changed.connect(self.children_changed)
        self.children_panel.setMinimumHeight(240)
        left.addWidget(self.children_panel, 2)

        # 坐姿阈值
        thresh_grp = QGroupBox("📐  坐姿检测阈值")
        tg = QFormLayout(thresh_grp)
        tg.setSpacing(10)
        tg.setContentsMargins(14, 18, 14, 14)

        self.th_widgets = {}
        thresh_defs = [
            ("theta1_max", "θ₁ 肩部水平（°）", config.THETA1_MAX, 3.0,  30.0),
            ("theta2_max", "θ₂ 头部俯仰（°）", config.THETA2_MAX, 10.0, 60.0),
            ("theta3_max", "θ₃ 躯干前倾（°）", config.THETA3_MAX, 5.0,  40.0),
            ("theta4_max", "θ₄ 头部偏航（°）", config.THETA4_MAX, 5.0,  30.0),
        ]
        for key, label, default, lo, hi in thresh_defs:
            spin = QDoubleSpinBox()
            spin.setRange(lo, hi)
            spin.setSingleStep(1.0)
            spin.setSuffix("°")
            spin.setValue(default)
            self.th_widgets[key] = spin
            tg.addRow(label, spin)

        save_thresh_btn = QPushButton("💾  保存阈值")
        save_thresh_btn.setObjectName("accentBtn")
        save_thresh_btn.clicked.connect(self._save_thresholds)
        tg.addRow("", save_thresh_btn)
        left.addWidget(thresh_grp)

        # 视距设置
        dist_grp = QGroupBox("📏  视距设置")
        dg = QFormLayout(dist_grp)
        dg.setSpacing(10)
        dg.setContentsMargins(14, 18, 14, 14)

        self.min_dist_spin = QSpinBox()
        self.min_dist_spin.setRange(20, 100)
        self.min_dist_spin.setSuffix(" cm")
        self.min_dist_spin.setValue(config.MIN_SAFE_DISTANCE_CM)
        dg.addRow("最小安全视距：", self.min_dist_spin)

        self.warn_dist_spin = QSpinBox()
        self.warn_dist_spin.setRange(15, 80)
        self.warn_dist_spin.setSuffix(" cm")
        self.warn_dist_spin.setValue(config.WARN_DISTANCE_CM)
        dg.addRow("警告触发视距：", self.warn_dist_spin)

        save_dist_btn = QPushButton("💾  保存视距设置")
        save_dist_btn.setObjectName("accentBtn")
        save_dist_btn.clicked.connect(self._save_dist)
        dg.addRow("", save_dist_btn)
        left.addWidget(dist_grp)

        left.addStretch()
        root.addLayout(left, 1)

        # ── 右列 ─────────────────────────────────────
        right = QVBoxLayout()
        right.setSpacing(10)

        # 孩子档案快速编辑（当前孩子）
        profile_grp = QGroupBox(f"👤  当前孩子档案")
        pg = QFormLayout(profile_grp)
        pg.setSpacing(10)
        pg.setContentsMargins(14, 18, 14, 14)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("请输入姓名")
        pg.addRow("姓名：", self.name_edit)

        self.age_spin = QSpinBox()
        self.age_spin.setRange(4, 18)
        self.age_spin.setSuffix(" 岁")
        pg.addRow("年龄：", self.age_spin)

        age_note = QLabel("（年龄影响休息提醒间隔和个性化建议）")
        age_note.setObjectName("metricLabel")
        age_note.setWordWrap(True)
        pg.addRow("", age_note)

        save_profile_btn = QPushButton("💾  保存档案")
        save_profile_btn.setObjectName("primaryBtn")
        save_profile_btn.clicked.connect(self._save_profile)
        pg.addRow("", save_profile_btn)
        right.addWidget(profile_grp)

        # 奖励管理
        reward_header = QHBoxLayout()
        rh_title = QLabel("🎁  当前孩子奖励管理")
        rh_title.setObjectName("sectionTitle")
        rh_title.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        reward_header.addWidget(rh_title)
        reward_header.addStretch()

        add_reward_btn = QPushButton("➕  添加奖励")
        add_reward_btn.setObjectName("primaryBtn")
        add_reward_btn.clicked.connect(self._add_reward)
        reward_header.addWidget(add_reward_btn)
        right.addLayout(reward_header)

        self.reward_table = QTableWidget(0, 4)
        self.reward_table.setHorizontalHeaderLabels(["名称", "描述", "积分", "操作"])
        self.reward_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.reward_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.reward_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.reward_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.reward_table.setAlternatingRowColors(True)
        self.reward_table.verticalHeader().setVisible(False)
        self.reward_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.reward_table.setShowGrid(False)
        right.addWidget(self.reward_table, 1)

        # 手动积分调整
        pts_grp = QGroupBox("🔧  手动积分调整（当前孩子）")
        pgl = QFormLayout(pts_grp)
        pgl.setSpacing(10)
        pgl.setContentsMargins(14, 18, 14, 14)

        self.adj_spin = QSpinBox()
        self.adj_spin.setRange(-9999, 9999)
        self.adj_spin.setSuffix(" 分")
        self.adj_spin.setValue(10)
        pgl.addRow("调整数量：", self.adj_spin)

        self.adj_reason = QLineEdit()
        self.adj_reason.setPlaceholderText("原因（如：完成家务）")
        pgl.addRow("原因：", self.adj_reason)

        adj_btn = QPushButton("✅  确认调整")
        adj_btn.setObjectName("primaryBtn")
        adj_btn.clicked.connect(self._adjust_points)
        pgl.addRow("", adj_btn)
        right.addWidget(pts_grp)

        root.addLayout(right, 1)

    # ── 数据加载 ─────────────────────────────────────────
    def showEvent(self, event):
        """每次切换到此页时刷新孩子卡片积分"""
        super().showEvent(event)
        self.children_panel.refresh(self.current_uid)

    def _load_all(self):
        user = self.db.get_user(self.current_uid)
        self.name_edit.setText(user.get("name", "小朋友"))
        self.age_spin.setValue(user.get("age", 10))

        s = self.db.get_all_settings(self.account_id)
        for key, spin in self.th_widgets.items():
            if key in s:
                spin.setValue(float(s[key]))

        if "min_distance" in s:
            self.min_dist_spin.setValue(int(s["min_distance"]))
        if "warn_distance" in s:
            self.warn_dist_spin.setValue(int(s["warn_distance"]))

        self._load_rewards()

    def _load_rewards(self):
        rewards = self.db.get_rewards(self.current_uid)
        self.reward_table.setRowCount(0)
        for r in rewards:
            row = self.reward_table.rowCount()
            self.reward_table.insertRow(row)
            self.reward_table.setRowHeight(row, 42)
            self.reward_table.setItem(row, 0, QTableWidgetItem(r["name"]))
            self.reward_table.setItem(row, 1, QTableWidgetItem(r.get("description", "")))
            self.reward_table.setItem(row, 2, QTableWidgetItem(str(r["points_needed"])))

            btn_widget = QWidget()
            btn_lay = QHBoxLayout(btn_widget)
            btn_lay.setContentsMargins(4, 2, 4, 2)
            btn_lay.setSpacing(4)

            edit_btn = QPushButton("编辑")
            edit_btn.setFixedSize(52, 28)
            edit_btn.clicked.connect(lambda c, rid=r["id"]: self._edit_reward(rid))

            del_btn = QPushButton("删除")
            del_btn.setObjectName("dangerBtn")
            del_btn.setFixedSize(52, 28)
            del_btn.clicked.connect(lambda c, rid=r["id"]: self._del_reward(rid))

            btn_lay.addWidget(edit_btn)
            btn_lay.addWidget(del_btn)
            self.reward_table.setCellWidget(row, 3, btn_widget)

    # ── 保存操作 ─────────────────────────────────────────
    def _save_profile(self):
        name = self.name_edit.text().strip() or "小朋友"
        age  = self.age_spin.value()
        self.db.update_user(name, age, uid=self.current_uid)
        self.children_panel.refresh(self.current_uid)
        self.children_changed.emit()
        QMessageBox.information(self, "保存成功", "孩子档案已更新。")
        self.settings_changed.emit()

    def _save_thresholds(self):
        for key, spin in self.th_widgets.items():
            self.db.set_setting(key, spin.value(), self.account_id)
        QMessageBox.information(self, "保存成功", "坐姿阈值已更新，下次启动监测时生效。")
        self.settings_changed.emit()

    def _save_dist(self):
        self.db.set_setting("min_distance", self.min_dist_spin.value(), self.account_id)
        self.db.set_setting("warn_distance", self.warn_dist_spin.value(), self.account_id)
        QMessageBox.information(self, "保存成功", "视距设置已更新。")
        self.settings_changed.emit()

    def _add_reward(self):
        dlg = RewardDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            name, desc, pts = dlg.values()
            if name:
                self.db.add_reward(name, desc, pts, self.current_uid)
                self._load_rewards()

    def _edit_reward(self, rid: int):
        reward = self.db.get_reward(rid)
        if not reward:
            return
        dlg = RewardDialog(self, reward)
        if dlg.exec_() == QDialog.Accepted:
            name, desc, pts = dlg.values()
            if name:
                self.db.update_reward(rid, name, desc, pts)
                self._load_rewards()

    def _del_reward(self, rid: int):
        reward = self.db.get_reward(rid)
        if not reward:
            return
        ans = QMessageBox.question(
            self, "确认删除",
            f"确定删除奖励「{reward['name']}」吗？",
            QMessageBox.Yes | QMessageBox.No)
        if ans == QMessageBox.Yes:
            self.db.delete_reward(rid)
            self._load_rewards()

    def _adjust_points(self):
        delta  = self.adj_spin.value()
        reason = self.adj_reason.text().strip() or "家长手动调整"
        if delta == 0:
            QMessageBox.warning(self, "提示", "调整数量不能为0。")
            return
        self.db.add_points(delta, f"[家长]{reason}", self.current_uid)
        total = self.db.get_total_points(self.current_uid)
        QMessageBox.information(
            self, "调整成功",
            f"积分已调整 {'+' if delta > 0 else ''}{delta} 分\n当前总积分：{total} 分")
        self.adj_spin.setValue(10)
        self.adj_reason.clear()
        self.children_panel.refresh(self.current_uid)