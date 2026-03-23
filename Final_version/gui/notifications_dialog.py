# gui/notifications_dialog.py — 儿童关联申请通知对话框

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QWidget,
    QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from database.db_manager import DatabaseManager


class NotificationsDialog(QDialog):
    """
    儿童登录后弹出，展示所有待确认的家长关联申请。
    accepted 信号在孩子接受申请后发出，通知主窗口刷新。
    """
    accepted_link = pyqtSignal()

    def __init__(self, db: DatabaseManager, child_account_id: int, parent=None):
        super().__init__(parent)
        self.db               = db
        self.child_account_id = child_account_id
        self.setWindowTitle("📬  家长关联申请")
        self.setMinimumWidth(460)
        self.setStyleSheet("""
            QDialog { background: #0D1117; }
            QLabel  { color: #E6EDF3; }
        """)
        self._build()
        self._load()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        # 标题
        title = QLabel("📬  收到家长关联申请")
        title.setFont(QFont("Microsoft YaHei", 15, QFont.Bold))
        title.setStyleSheet("color:#58A6FF;")
        root.addWidget(title)

        desc = QLabel(
            "以下家长希望将您的账号关联到他们的管理列表。\n"
            "接受后，家长可以查看您的坐姿数据和积分，并为您设置奖励。")
        desc.setStyleSheet("color:#8B949E; font-size:12px;")
        desc.setWordWrap(True)
        root.addWidget(desc)

        # 申请列表（可滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch()

        scroll.setWidget(self.list_widget)
        root.addWidget(scroll, 1)

        # 底部关闭按钮
        close_btn = QPushButton("稍后再说")
        close_btn.setStyleSheet("""
            QPushButton {
                background: #21262D; border: 1px solid #30363D;
                border-radius: 8px; color: #8B949E;
                padding: 8px 24px; font-size: 13px;
            }
            QPushButton:hover { background: #30363D; color: #E6EDF3; }
        """)
        close_btn.clicked.connect(self.accept)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

    def _load(self):
        # 清空旧卡片
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        requests = self.db.get_pending_requests(self.child_account_id)
        if not requests:
            empty = QLabel("暂无待处理申请")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color:#484F58; font-size:13px; padding:20px;")
            self.list_layout.insertWidget(0, empty)
            return

        for req in requests:
            self.list_layout.insertWidget(
                self.list_layout.count() - 1,
                self._make_card(req))

    def _make_card(self, req: dict) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet("""
            QFrame#card {
                background: #161B22;
                border: 1px solid #30363D;
                border-radius: 10px;
                padding: 4px;
            }
        """)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        # 头像占位
        avatar = QLabel("👨‍👩‍👧")
        avatar.setFont(QFont("Segoe UI Emoji", 22))
        avatar.setFixedWidth(40)
        lay.addWidget(avatar)

        # 信息
        info = QVBoxLayout()
        name_lbl = QLabel(req.get("nickname") or req["username"])
        name_lbl.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        name_lbl.setStyleSheet("color:#E6EDF3;")

        user_lbl = QLabel(f"用户名：{req['username']}")
        user_lbl.setStyleSheet("color:#8B949E; font-size:11px;")

        time_lbl = QLabel(f"申请时间：{req['created_at'][:16]}")
        time_lbl.setStyleSheet("color:#484F58; font-size:10px;")

        info.addWidget(name_lbl)
        info.addWidget(user_lbl)
        info.addWidget(time_lbl)
        lay.addLayout(info, 1)

        # 操作按钮
        btn_col = QVBoxLayout()
        btn_col.setSpacing(6)

        accept_btn = QPushButton("✅  接 受")
        accept_btn.setFixedWidth(90)
        accept_btn.setStyleSheet("""
            QPushButton {
                background: #238636; border-radius: 7px;
                color: #fff; font-size: 12px; padding: 6px;
                font-weight: bold;
            }
            QPushButton:hover { background: #2EA043; }
        """)
        accept_btn.clicked.connect(
            lambda: self._on_accept(req["id"], card, accept_btn, reject_btn))

        reject_btn = QPushButton("❌  拒 绝")
        reject_btn.setFixedWidth(90)
        reject_btn.setStyleSheet("""
            QPushButton {
                background: #21262D; border: 1px solid #F85149;
                border-radius: 7px; color: #F85149;
                font-size: 12px; padding: 6px;
            }
            QPushButton:hover { background: #F8514922; }
        """)
        reject_btn.clicked.connect(
            lambda: self._on_reject(req["id"], card, accept_btn, reject_btn))

        btn_col.addWidget(accept_btn)
        btn_col.addWidget(reject_btn)
        lay.addLayout(btn_col)

        return card

    def _on_accept(self, request_id: int, card: QFrame,
                   accept_btn: QPushButton, reject_btn: QPushButton):
        ok = self.db.accept_link_request(request_id, self.child_account_id)
        if ok:
            accept_btn.setText("✅  已接受")
            accept_btn.setEnabled(False)
            reject_btn.setEnabled(False)
            accept_btn.setStyleSheet(
                "background:#196127; border-radius:7px; color:#8B949E;"
                " font-size:12px; padding:6px;")
            card.setStyleSheet("""
                QFrame#card {
                    background: #0D2B0D;
                    border: 1px solid #238636;
                    border-radius: 10px;
                }
            """)
            self.accepted_link.emit()

    def _on_reject(self, request_id: int, card: QFrame,
                   accept_btn: QPushButton, reject_btn: QPushButton):
        ok = self.db.reject_link_request(request_id, self.child_account_id)
        if ok:
            reject_btn.setText("❌  已拒绝")
            reject_btn.setEnabled(False)
            accept_btn.setEnabled(False)
            card.setStyleSheet("""
                QFrame#card {
                    background: #1A1010;
                    border: 1px solid #30363D;
                    border-radius: 10px;
                    opacity: 0.5;
                }
            """)