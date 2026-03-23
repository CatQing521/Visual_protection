# gui/login_window.py — 登录 / 注册窗口

import hashlib
import os
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFrame, QTabWidget,
    QComboBox, QMessageBox, QSizePolicy, QSpacerItem
)
from PyQt5.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QPixmap, QColor, QPainter, QIcon

from database.db_manager import DatabaseManager


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def _make_salt() -> str:
    return os.urandom(16).hex()


# ── 圆角输入框封装 ───────────────────────────────────────
class StyledLineEdit(QLineEdit):
    def __init__(self, placeholder="", password=False, parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        if password:
            self.setEchoMode(QLineEdit.Password)
        self.setFixedHeight(40)
        self.setStyleSheet("""
            QLineEdit {
                background: #161B22;
                border: 1.5px solid #30363D;
                border-radius: 8px;
                padding: 0 14px;
                color: #E6EDF3;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #58A6FF;
                background: #0D1117;
            }
            QLineEdit::placeholder {
                color: #484F58;
            }
        """)


# ── 登录页 ───────────────────────────────────────────────
class LoginPage(QWidget):
    login_success = pyqtSignal(dict)   # 发出 account dict

    def __init__(self, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 24, 32, 24)
        lay.setSpacing(14)

        tip = QLabel("使用家长账号登录可管理多个孩子档案")
        tip.setStyleSheet("color:#8B949E; font-size:12px;")
        tip.setAlignment(Qt.AlignCenter)
        lay.addWidget(tip)

        self.username_edit = StyledLineEdit("用户名")
        self.password_edit = StyledLineEdit("密码", password=True)
        lay.addWidget(self.username_edit)
        lay.addWidget(self.password_edit)

        self.err_lbl = QLabel("")
        self.err_lbl.setStyleSheet("color:#F85149; font-size:12px;")
        self.err_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.err_lbl)

        lay.addItem(QSpacerItem(0, 8, QSizePolicy.Minimum, QSizePolicy.Fixed))

        login_btn = QPushButton("登 录")
        login_btn.setFixedHeight(42)
        login_btn.setStyleSheet("""
            QPushButton {
                background: #1F6FEB;
                border-radius: 8px;
                color: #fff;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background: #388BFD; }
            QPushButton:pressed { background: #1158C7; }
        """)
        login_btn.clicked.connect(self._do_login)
        lay.addWidget(login_btn)

        # Enter 键触发登录
        self.password_edit.returnPressed.connect(self._do_login)
        self.username_edit.returnPressed.connect(self.password_edit.setFocus)

    def _do_login(self):
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        if not username or not password:
            self.err_lbl.setText("请填写用户名和密码")
            return
        try:
            account = self.db.login(username, password)
        except Exception as e:
            self.err_lbl.setText(f"数据库错误：{e}")
            return

        if account is None:
            self.err_lbl.setText("用户名或密码错误")
            self.password_edit.clear()
            return

        self.err_lbl.setText("")
        self.login_success.emit(account)


# ── 注册页 ───────────────────────────────────────────────
class RegisterPage(QWidget):
    register_success = pyqtSignal(dict)

    def __init__(self, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 16, 32, 24)
        lay.setSpacing(10)

        # 角色选择
        role_row = QHBoxLayout()
        role_lbl = QLabel("账号类型：")
        role_lbl.setStyleSheet("color:#8B949E;")
        self.role_combo = QComboBox()
        self.role_combo.addItems(["👨‍👩‍👧 家长账号", "🧒 儿童账号"])
        self.role_combo.setFixedHeight(36)
        self.role_combo.setStyleSheet("""
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
        role_row.addWidget(role_lbl)
        role_row.addWidget(self.role_combo, 1)
        lay.addLayout(role_row)

        self.username_edit   = StyledLineEdit("用户名（4-20位字母/数字）")
        self.nickname_edit   = StyledLineEdit("昵称（显示用，可留空）")
        self.password_edit   = StyledLineEdit("密码（至少6位）", password=True)
        self.confirm_edit    = StyledLineEdit("确认密码", password=True)

        for w in [self.username_edit, self.nickname_edit,
                  self.password_edit, self.confirm_edit]:
            lay.addWidget(w)

        self.err_lbl = QLabel("")
        self.err_lbl.setStyleSheet("color:#F85149; font-size:12px;")
        self.err_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.err_lbl)

        reg_btn = QPushButton("创 建 账 号")
        reg_btn.setFixedHeight(42)
        reg_btn.setStyleSheet("""
            QPushButton {
                background: #238636;
                border-radius: 8px;
                color: #fff;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background: #2EA043; }
            QPushButton:pressed { background: #196127; }
        """)
        reg_btn.clicked.connect(self._do_register)
        lay.addWidget(reg_btn)

    def _do_register(self):
        username = self.username_edit.text().strip()
        nickname = self.nickname_edit.text().strip() or username
        password = self.password_edit.text()
        confirm  = self.confirm_edit.text()
        role     = "parent" if self.role_combo.currentIndex() == 0 else "child"

        # 校验
        if len(username) < 4:
            self.err_lbl.setText("用户名至少4位")
            return
        if not username.replace("_", "").isalnum():
            self.err_lbl.setText("用户名只能包含字母、数字和下划线")
            return
        if len(password) < 6:
            self.err_lbl.setText("密码至少6位")
            return
        if password != confirm:
            self.err_lbl.setText("两次密码不一致")
            return

        try:
            if self.db.account_exists(username):
                self.err_lbl.setText("该用户名已被注册")
                return
            account = self.db.register(username, password, nickname, role)
        except Exception as e:
            self.err_lbl.setText(f"注册失败：{e}")
            return

        self.err_lbl.setText("")
        self.register_success.emit(account)


# ── 主登录对话框 ─────────────────────────────────────────
class LoginDialog(QDialog):
    """返回已登录的 account dict，cancel 则 reject"""

    def __init__(self, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db      = db
        self.account = None
        self.setWindowTitle("VisionGuard — 登录")
        self.setFixedSize(440, 480)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._build()
        self._drag_pos = None

    def _build(self):
        # 外层带圆角的容器
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("loginCard")
        card.setStyleSheet("""
            QFrame#loginCard {
                background: #0D1117;
                border-radius: 16px;
                border: 1px solid #30363D;
            }
        """)
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(0, 0, 0, 20)
        card_lay.setSpacing(0)

        # ── 顶部 LOGO 区 ─────────────────────────────
        header = QWidget()
        header.setFixedHeight(110)
        header.setStyleSheet("background: #161B22; border-radius: 16px 16px 0 0;")
        h_lay = QVBoxLayout(header)
        h_lay.setAlignment(Qt.AlignCenter)

        logo_row = QHBoxLayout()
        logo_row.setAlignment(Qt.AlignCenter)
        logo_lbl = QLabel("👁")
        logo_lbl.setFont(QFont("Segoe UI Emoji", 28))
        title_lbl = QLabel("VisionGuard")
        title_lbl.setFont(QFont("Microsoft YaHei", 22, QFont.Bold))
        title_lbl.setStyleSheet("color:#58A6FF;")
        logo_row.addWidget(logo_lbl)
        logo_row.addWidget(title_lbl)
        h_lay.addLayout(logo_row)

        sub_lbl = QLabel("儿童近视风险预防系统")
        sub_lbl.setStyleSheet("color:#8B949E; font-size:12px;")
        sub_lbl.setAlignment(Qt.AlignCenter)
        h_lay.addWidget(sub_lbl)
        card_lay.addWidget(header)

        # 关闭按钮（右上角） — 对话框固定宽440，直接用固定坐标
        close_btn = QPushButton("✕")
        close_btn.setParent(header)
        close_btn.setFixedSize(28, 28)
        close_btn.move(440 - 36, 8)   # 固定宽度440，避免build期 width()==0
        close_btn.setStyleSheet("""
            QPushButton { background:transparent; color:#8B949E;
                          border:none; font-size:14px; }
            QPushButton:hover { color:#F85149; }
        """)
        close_btn.clicked.connect(self.reject)

        # ── 标签页 ───────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: none; }
            QTabBar::tab {
                background: transparent;
                color: #8B949E;
                padding: 10px 32px;
                font-size: 13px;
                font-weight: bold;
                border-bottom: 2px solid transparent;
            }
            QTabBar::tab:selected {
                color: #58A6FF;
                border-bottom: 2px solid #58A6FF;
            }
            QTabBar::tab:hover { color: #E6EDF3; }
        """)

        self.login_page    = LoginPage(self.db)
        self.register_page = RegisterPage(self.db)
        self.tabs.addTab(self.login_page,    "登  录")
        self.tabs.addTab(self.register_page, "注  册")

        self.login_page.login_success.connect(self._on_success)
        self.register_page.register_success.connect(self._on_register_success)

        card_lay.addWidget(self.tabs)

        # 版权
        copy_lbl = QLabel("© 2025 VisionGuard  ·  儿童用眼健康守护")
        copy_lbl.setStyleSheet("color:#484F58; font-size:10px;")
        copy_lbl.setAlignment(Qt.AlignCenter)
        card_lay.addWidget(copy_lbl)

        outer.addWidget(card)

    def _on_success(self, account: dict):
        self.account = account
        self.accept()

    def _on_register_success(self, account: dict):
        QMessageBox.information(
            self, "注册成功",
            f"账号「{account['username']}」创建成功！\n"
            f"{'家长账号可在「家长配置」页管理多个孩子档案。' if account['role']=='parent' else ''}",
        )
        # 切换到登录页并填充用户名
        self.tabs.setCurrentIndex(0)
        self.login_page.username_edit.setText(account["username"])
        self.login_page.password_edit.setFocus()

    # ── 拖动无边框窗口 ──────────────────────────────────
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag_pos = ev.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, ev):
        if self._drag_pos and ev.buttons() == Qt.LeftButton:
            self.move(ev.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, ev):
        self._drag_pos = None