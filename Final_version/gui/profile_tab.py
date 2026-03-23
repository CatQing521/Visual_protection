# gui/profile_tab.py — 个人中心标签页（家长 / 儿童通用）

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QLineEdit, QComboBox,
    QMessageBox, QSizePolicy, QSpacerItem, QGridLayout
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from database.db_manager import DatabaseManager


# ── 带标题的卡片容器 ─────────────────────────────────────
class _SectionCard(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 20)
        root.setSpacing(14)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("sectionTitle")
        title_lbl.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        root.addWidget(title_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#21262D;")
        root.addWidget(sep)

        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        root.addLayout(self.body)

    def add_row(self, label: str, widget: QWidget):
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setFixedWidth(90)
        lbl.setStyleSheet("color:#8B949E; font-size:12px;")
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(lbl)
        row.addWidget(widget, 1)
        self.body.addLayout(row)

    def add_widget(self, widget: QWidget):
        self.body.addWidget(widget)


# ── 只读信息标签 ─────────────────────────────────────────
def _info_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "color:#E6EDF3; font-size:13px;"
        " background:#0D1117; border:1px solid #21262D;"
        " border-radius:6px; padding:6px 10px;")
    return lbl


# ── 输入框统一样式 ───────────────────────────────────────
def _input(placeholder="", password=False) -> QLineEdit:
    w = QLineEdit()
    w.setPlaceholderText(placeholder)
    if password:
        w.setEchoMode(QLineEdit.Password)
    w.setFixedHeight(36)
    w.setStyleSheet("""
        QLineEdit {
            background:#161B22; border:1.5px solid #30363D;
            border-radius:7px; padding:0 10px;
            color:#E6EDF3; font-size:13px;
        }
        QLineEdit:focus { border-color:#58A6FF; background:#0D1117; }
        QLineEdit::placeholder { color:#484F58; }
    """)
    return w


# ── 主页面 ───────────────────────────────────────────────
class ProfileTab(QWidget):
    """
    个人中心：展示账号信息、修改昵称、修改密码。
    儿童账号额外显示档案信息（年龄、头像）。
    """
    account_updated = pyqtSignal(dict)   # 昵称修改后通知主窗口刷新顶栏

    AVATARS = ["🧒", "👦", "👧", "🧑", "🎓", "🌟", "🦁", "🐼", "🐸", "🚀"]

    def __init__(self, db: DatabaseManager, account: dict,
                 current_user: dict = None, parent=None):
        super().__init__(parent)
        self.db           = db
        self.account      = account          # 登录账号（家长或儿童）
        self.current_user = current_user or {}  # 孩子档案（儿童账号时为自己）
        self.is_parent    = (account.get("role") == "parent")
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # ── 页头 ─────────────────────────────────────
        header = QHBoxLayout()
        avatar_lbl = QLabel("👨\u200d👩\u200d👧" if self.is_parent else
                            self.current_user.get("avatar", "🧒"))
        avatar_lbl.setFont(QFont("Segoe UI Emoji", 32))
        avatar_lbl.setFixedWidth(56)

        title_col = QVBoxLayout()
        role_text  = "家长账号" if self.is_parent else "儿童账号"
        name_lbl   = QLabel(self.account.get("nickname") or
                            self.account.get("username", "用户"))
        name_lbl.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
        name_lbl.setStyleSheet("color:#E6EDF3;")
        role_lbl = QLabel(f"@{self.account['username']}  ·  {role_text}")
        role_lbl.setStyleSheet("color:#8B949E; font-size:12px;")
        title_col.addWidget(name_lbl)
        title_col.addWidget(role_lbl)
        title_col.setSpacing(2)

        header.addWidget(avatar_lbl)
        header.addLayout(title_col, 1)
        root.addLayout(header)

        # ── 双列布局 ─────────────────────────────────
        cols = QHBoxLayout()
        cols.setSpacing(16)
        left  = QVBoxLayout()
        right = QVBoxLayout()
        left.setSpacing(16)
        right.setSpacing(16)

        # ── 左列：账号信息 ────────────────────────────
        info_card = _SectionCard("📋  账号信息")
        info_card.add_row("用户名",   _info_label(self.account.get("username", "—")))
        info_card.add_row("角色",     _info_label(role_text))
        created = self.account.get("created_at", "—")[:10]
        info_card.add_row("注册时间", _info_label(created))
        left.addWidget(info_card)

        # ── 左列：修改昵称 ────────────────────────────
        nick_card = _SectionCard("✏️  修改昵称")
        self._nick_edit = _input(
            placeholder=self.account.get("nickname") or self.account.get("username", ""))
        nick_card.add_row("新昵称", self._nick_edit)

        nick_btn = QPushButton("保存昵称")
        nick_btn.setObjectName("accentBtn")
        nick_btn.setFixedHeight(36)
        nick_btn.clicked.connect(self._save_nickname)
        nick_card.add_widget(nick_btn)
        left.addWidget(nick_card)

        left.addStretch()

        # ── 右列：修改密码 ────────────────────────────
        pw_card = _SectionCard("🔒  修改密码")
        self._old_pw   = _input("当前密码", password=True)
        self._new_pw   = _input("新密码（至少6位）", password=True)
        self._confirm_pw = _input("确认新密码", password=True)
        pw_card.add_row("当前密码", self._old_pw)
        pw_card.add_row("新密码",   self._new_pw)
        pw_card.add_row("确认密码", self._confirm_pw)

        pw_btn = QPushButton("修改密码")
        pw_btn.setObjectName("accentBtn")
        pw_btn.setFixedHeight(36)
        pw_btn.clicked.connect(self._save_password)
        pw_card.add_widget(pw_btn)
        right.addWidget(pw_card)

        # ── 右列：儿童档案（仅儿童账号显示）──────────
        if not self.is_parent and self.current_user:
            profile_card = _SectionCard("🧒  我的档案")

            self._age_combo = QComboBox()
            self._age_combo.setFixedHeight(36)
            self._age_combo.setStyleSheet("""
                QComboBox {
                    background:#161B22; border:1.5px solid #30363D;
                    border-radius:7px; padding:0 10px;
                    color:#E6EDF3; font-size:13px;
                }
                QComboBox::drop-down { border:none; }
                QComboBox QAbstractItemView {
                    background:#161B22; color:#E6EDF3;
                    selection-background-color:#1F6FEB;
                }
            """)
            for age in range(5, 19):
                self._age_combo.addItem(f"{age} 岁", age)
            cur_age = self.current_user.get("age", 10)
            idx = self._age_combo.findData(cur_age)
            if idx >= 0:
                self._age_combo.setCurrentIndex(idx)

            self._avatar_combo = QComboBox()
            self._avatar_combo.setFixedHeight(36)
            self._avatar_combo.setStyleSheet(self._age_combo.styleSheet())
            for av in self.AVATARS:
                self._avatar_combo.addItem(av, av)
            cur_av = self.current_user.get("avatar", "🧒")
            av_idx = self._avatar_combo.findData(cur_av)
            if av_idx >= 0:
                self._avatar_combo.setCurrentIndex(av_idx)

            profile_card.add_row("我的年龄", self._age_combo)
            profile_card.add_row("我的头像", self._avatar_combo)

            save_profile_btn = QPushButton("保存档案")
            save_profile_btn.setObjectName("accentBtn")
            save_profile_btn.setFixedHeight(36)
            save_profile_btn.clicked.connect(self._save_profile)
            profile_card.add_widget(save_profile_btn)
            right.addWidget(profile_card)

        right.addStretch()

        cols.addLayout(left,  1)
        cols.addLayout(right, 1)
        root.addLayout(cols, 1)

    # ── 保存昵称 ─────────────────────────────────────────
    def _save_nickname(self):
        new_nick = self._nick_edit.text().strip()
        if not new_nick:
            self._show_warn("请输入新昵称")
            return
        if len(new_nick) > 20:
            self._show_warn("昵称不能超过20个字符")
            return

        # 1. 更新 accounts.nickname（登录账号表）
        self.db.update_account_nickname(self.account["id"], new_nick)
        self.account["nickname"] = new_nick

        # 2. 儿童账号：同步更新 users.name（孩子档案表）
        #    家长端的下拉框 / 孩子卡片读的是 users.name，不同步则家长看不到变化
        if not self.is_parent and self.current_user:
            uid = self.current_user.get("id")
            age = self.current_user.get("age", 10)
            av  = self.current_user.get("avatar", "🧒")
            self.db.update_user(new_nick, age, av, uid)
            self.current_user["name"] = new_nick

        self._nick_edit.clear()
        self._nick_edit.setPlaceholderText(new_nick)
        self._show_ok("昵称已更新为「{}」".format(new_nick))
        self.account_updated.emit(self.account)

    # ── 保存密码 ─────────────────────────────────────────
    def _save_password(self):
        old_pw  = self._old_pw.text()
        new_pw  = self._new_pw.text()
        confirm = self._confirm_pw.text()

        if not old_pw:
            self._show_warn("请输入当前密码")
            return
        if len(new_pw) < 6:
            self._show_warn("新密码至少6位")
            return
        if new_pw != confirm:
            self._show_warn("两次输入的新密码不一致")
            return
        if old_pw == new_pw:
            self._show_warn("新密码不能与当前密码相同")
            return

        ok = self.db.change_password(self.account["id"], old_pw, new_pw)
        if ok:
            self._old_pw.clear()
            self._new_pw.clear()
            self._confirm_pw.clear()
            self._show_ok("密码修改成功！请在下次登录时使用新密码。")
        else:
            self._show_warn("当前密码错误，请重新输入")
            self._old_pw.clear()
            self._old_pw.setFocus()

    # ── 保存儿童档案 ─────────────────────────────────────
    def _save_profile(self):
        age    = self._age_combo.currentData()
        avatar = self._avatar_combo.currentData()
        uid    = self.current_user.get("id", 1)
        name   = self.current_user.get("name", "小朋友")
        self.db.update_user(name, age, avatar, uid)
        self.current_user["age"]    = age
        self.current_user["avatar"] = avatar
        self._show_ok("档案已保存！")

    # ── 工具 ─────────────────────────────────────────────
    def _show_ok(self, msg: str):
        QMessageBox.information(self, "成功", msg)

    def _show_warn(self, msg: str):
        QMessageBox.warning(self, "提示", msg)

    def refresh(self):
        """主窗口切换到此页时调用，保持账号信息最新"""
        self.account = self.db.get_account_by_id(self.account["id"])