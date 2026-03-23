# gui/ai_chat_tab.py — AI 助手答疑模块（家长 / 儿童双模式）

import time
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QLineEdit, QFrame,
    QScrollArea, QSizePolicy, QSpacerItem
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QColor

import config


# ══════════════════════════════════════════════════════════
# 系统提示词
# ══════════════════════════════════════════════════════════
_SYSTEM_PARENT = """你是 VisionGuard 系统的专业儿童视力健康顾问助手。
你的服务对象是关心孩子用眼健康的家长。

你可以帮助家长：
1. 解答关于儿童近视预防、坐姿矫正、用眼卫生的专业问题
2. 解读系统检测数据（视距、坐姿角度、用眼时长）的含义
3. 提供科学的护眼建议和家庭干预方案
4. 推荐适合孩子年龄的用眼时长和休息频率
5. 解答关于 VisionGuard 系统功能和使用方法的问题

回答要求：
- 使用专业但易懂的中文
- 建议具体可操作，避免泛泛而谈
- 涉及医学问题时建议及时就医，不替代医生诊断
- 回答长度适中，重点突出
"""

_SYSTEM_CHILD = """你是 VisionGuard 系统里的护眼小伙伴「视视」🤖！
你专门陪伴小朋友一起保护眼睛、养成好习惯。

你可以：
1. 用简单有趣的语言解释为什么要保护眼睛
2. 教小朋友正确的坐姿和用眼方法
3. 分享护眼小知识和眼保健操
4. 鼓励小朋友坚持好习惯，获得更多积分
5. 回答关于系统积分和奖励的问题

说话要求：
- 语气活泼友好，像朋友一样
- 使用简单的词语，多用比喻
- 多用 emoji 让对话更生动
- 适当给予鼓励和表扬
- 回答简短清晰，不超过150字
"""


# ══════════════════════════════════════════════════════════
# 后台 API 调用线程
# ══════════════════════════════════════════════════════════
class ChatWorker(QThread):
    reply_ready  = pyqtSignal(str)   # 正常回复
    error_signal = pyqtSignal(str)   # 错误信息

    def __init__(self, messages: list, system: str, api_key: str):
        super().__init__()
        self.messages = messages
        self.system   = system
        self.api_key  = api_key

    def run(self):
        if not self.api_key or self.api_key.startswith("在这里填入"):
            self.error_signal.emit("未配置 API Key，请在 config.py 中填入 DEEPSEEK_API_KEY。")
            return
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=self.api_key,
                base_url="https://api.deepseek.com",
            )
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "system", "content": self.system}] + self.messages,
                max_tokens=500,
                temperature=0.8,
            )
            self.reply_ready.emit(resp.choices[0].message.content.strip())
        except ImportError:
            self.error_signal.emit("请先安装 openai 库：pip install openai")
        except Exception as e:
            self.error_signal.emit(f"网络错误：{e}")


# ══════════════════════════════════════════════════════════
# 单条消息气泡
# ══════════════════════════════════════════════════════════
class MessageBubble(QFrame):
    """
    is_user=True  → 右侧蓝色气泡（用户）
    is_user=False → 左侧深色气泡（AI）
    """
    def __init__(self, text: str, is_user: bool, is_parent: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("card")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 2, 0, 2)
        outer.setSpacing(8)

        # 头像
        avatar = QLabel("👤" if is_user else ("🧑‍💼" if is_parent else "🤖"))
        avatar.setFont(QFont("Segoe UI Emoji", 18))
        avatar.setFixedWidth(36)
        avatar.setAlignment(Qt.AlignTop)

        # 气泡
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bubble.setFont(QFont("Microsoft YaHei", 11))
        bubble.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        if is_user:
            bubble.setStyleSheet("""
                QLabel {
                    background: #1F6FEB;
                    color: #ffffff;
                    border-radius: 12px 12px 2px 12px;
                    padding: 10px 14px;
                }
            """)
            outer.addStretch()
            outer.addWidget(bubble)
            outer.addWidget(avatar)
        else:
            bubble.setStyleSheet("""
                QLabel {
                    background: #21262D;
                    color: #E6EDF3;
                    border-radius: 12px 12px 12px 2px;
                    padding: 10px 14px;
                    border: 1px solid #30363D;
                }
            """)
            outer.addWidget(avatar)
            outer.addWidget(bubble)
            outer.addStretch()


# ══════════════════════════════════════════════════════════
# 主聊天页面
# ══════════════════════════════════════════════════════════
class AIChatTab(QWidget):
    def __init__(self, is_parent: bool, api_key: str = "",
                 child_name: str = "小朋友", parent=None):
        super().__init__(parent)
        self.is_parent  = is_parent
        self.api_key    = api_key
        self.child_name = child_name
        self._history   = []      # [{"role": "user"/"assistant", "content": "..."}]
        self._workers   = []
        self._build_ui()
        # 延迟200ms发送欢迎语，等界面渲染完
        QTimer.singleShot(200, self._send_welcome)

    # ── UI 构建 ───────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # 顶部标题栏
        header = QHBoxLayout()
        icon_lbl = QLabel("🤖" if not self.is_parent else "🧑‍💼")
        icon_lbl.setFont(QFont("Segoe UI Emoji", 22))
        title_lbl = QLabel(
            "AI 护眼顾问" if self.is_parent else "护眼小伙伴「视视」")
        title_lbl.setObjectName("sectionTitle")
        title_lbl.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        sub_lbl = QLabel(
            "专业视力健康咨询" if self.is_parent
            else "你的护眼好朋友，随时帮你解答！")
        sub_lbl.setStyleSheet("color:#8B949E; font-size:11px;")

        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        info_col.addWidget(title_lbl)
        info_col.addWidget(sub_lbl)

        header.addWidget(icon_lbl)
        header.addLayout(info_col)
        header.addStretch()

        clear_btn = QPushButton("🗑  清空对话")
        clear_btn.setStyleSheet("""
            QPushButton {
                background: #21262D; border: 1px solid #30363D;
                border-radius: 7px; color: #8B949E;
                padding: 6px 14px; font-size: 12px;
            }
            QPushButton:hover { background: #30363D; color: #E6EDF3; }
        """)
        clear_btn.clicked.connect(self._clear_chat)
        header.addWidget(clear_btn)
        root.addLayout(header)

        # 分隔线
        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #21262D;")
        root.addWidget(sep)

        # 快捷问题按钮区
        quick_frame = QFrame()
        quick_frame.setObjectName("card")
        qf_lay = QVBoxLayout(quick_frame)
        qf_lay.setContentsMargins(12, 8, 12, 8)
        qf_lay.setSpacing(6)
        ql = QLabel("💬  快捷提问")
        ql.setStyleSheet("color:#8B949E; font-size:11px;")
        qf_lay.addWidget(ql)
        qbtn_row = QHBoxLayout()
        qbtn_row.setSpacing(8)

        if self.is_parent:
            quick_qs = [
                "孩子视距总是偏近怎么办？",
                "如何帮孩子改善坐姿？",
                "每天用眼多久合适？",
                "近视怎么预防？",
            ]
        else:
            quick_qs = [
                "为什么要保持眼距？",
                "怎么做眼保健操？",
                "怎么获得更多积分？",
                "坐姿不好有什么影响？",
            ]

        for q in quick_qs:
            btn = QPushButton(q)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background: #161B22; border: 1px solid #30363D;
                    border-radius: 6px; color: #58A6FF;
                    padding: 5px 10px; font-size: 11px;
                }
                QPushButton:hover { background: #1F6FEB22; border-color: #58A6FF; }
            """)
            btn.clicked.connect(lambda _, text=q: self._send_message(text))
            qbtn_row.addWidget(btn)
        qbtn_row.addStretch()
        qf_lay.addLayout(qbtn_row)
        root.addWidget(quick_frame)

        # 聊天气泡区（可滚动）
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setStyleSheet("""
            QScrollArea { background: #0D1117; border: 1px solid #21262D;
                          border-radius: 10px; }
            QScrollBar:vertical { background: #161B22; width: 6px; border-radius: 3px; }
            QScrollBar::handle:vertical { background: #30363D; border-radius: 3px; }
        """)

        self.chat_widget = QWidget()
        self.chat_widget.setStyleSheet("background: #0D1117;")
        self.chat_layout = QVBoxLayout(self.chat_widget)
        self.chat_layout.setContentsMargins(16, 16, 16, 16)
        self.chat_layout.setSpacing(10)
        self.chat_layout.addStretch()   # 推消息到底部

        self.scroll_area.setWidget(self.chat_widget)
        root.addWidget(self.scroll_area, 1)

        # 正在输入提示
        self.typing_lbl = QLabel("  🤖  正在思考中…")
        self.typing_lbl.setStyleSheet("color:#8B949E; font-size:12px;")
        self.typing_lbl.hide()
        root.addWidget(self.typing_lbl)

        # 输入框区域
        input_frame = QFrame()
        input_frame.setObjectName("card")
        input_lay = QHBoxLayout(input_frame)
        input_lay.setContentsMargins(12, 8, 12, 8)
        input_lay.setSpacing(8)

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText(
            "向 AI 顾问提问…" if self.is_parent else "问问视视吧～")
        self.input_box.setFixedHeight(42)
        self.input_box.setFont(QFont("Microsoft YaHei", 12))
        self.input_box.setStyleSheet("""
            QLineEdit {
                background: #161B22; border: 1px solid #30363D;
                border-radius: 8px; padding: 0 14px;
                color: #E6EDF3; font-size: 12px;
            }
            QLineEdit:focus { border-color: #58A6FF; }
        """)
        self.input_box.returnPressed.connect(self._on_send)

        self.send_btn = QPushButton("发 送")
        self.send_btn.setFixedSize(80, 42)
        self.send_btn.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        self.send_btn.setStyleSheet("""
            QPushButton {
                background: #1F6FEB; border-radius: 8px;
                color: #fff; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background: #388BFD; }
            QPushButton:pressed { background: #1158C7; }
            QPushButton:disabled { background: #21262D; color: #484F58; }
        """)
        self.send_btn.clicked.connect(self._on_send)

        input_lay.addWidget(self.input_box, 1)
        input_lay.addWidget(self.send_btn)
        root.addWidget(input_frame)

    # ── 欢迎语 ────────────────────────────────────────────
    def _send_welcome(self):
        if self.is_parent:
            welcome = (
                f"您好！我是 VisionGuard AI 护眼顾问 🧑‍💼\n\n"
                f"我可以帮您解答关于孩子用眼健康的各类问题，"
                f"包括近视预防、坐姿指导、系统数据解读等。\n\n"
                f"请问有什么可以帮到您？"
            )
        else:
            welcome = (
                f"嗨！我是护眼小伙伴「视视」🤖✨\n\n"
                f"我来帮你保护眼睛、养成好习惯！\n"
                f"有什么想问的，直接说吧～😊"
            )
        self._append_bubble(welcome, is_user=False)

    # ── 发送逻辑 ─────────────────────────────────────────
    def _on_send(self):
        text = self.input_box.text().strip()
        if not text:
            return
        self.input_box.clear()
        self._send_message(text)

    def _send_message(self, text: str):
        # 显示用户消息
        self._append_bubble(text, is_user=True)
        self._history.append({"role": "user", "content": text})

        # 禁用输入，显示等待
        self.send_btn.setEnabled(False)
        self.input_box.setEnabled(False)
        self.typing_lbl.show()
        self._scroll_to_bottom()

        # 启动后台请求（最多保留最近20轮上下文）
        system = _SYSTEM_PARENT if self.is_parent else _SYSTEM_CHILD
        worker = ChatWorker(self._history[-20:], system, self.api_key)
        worker.reply_ready.connect(self._on_reply)
        worker.error_signal.connect(self._on_error)
        worker.finished.connect(self._on_worker_done)
        self._workers.append(worker)
        worker.start()

    def _on_reply(self, text: str):
        self._history.append({"role": "assistant", "content": text})
        self.typing_lbl.hide()
        self._append_bubble(text, is_user=False)

    def _on_error(self, msg: str):
        self.typing_lbl.hide()
        error_text = f"⚠ {msg}"
        self._append_bubble(error_text, is_user=False)

    def _on_worker_done(self):
        self.send_btn.setEnabled(True)
        self.input_box.setEnabled(True)
        self.input_box.setFocus()
        self._scroll_to_bottom()

    # ── 气泡 & 滚动 ──────────────────────────────────────
    def _append_bubble(self, text: str, is_user: bool):
        bubble = MessageBubble(text, is_user, self.is_parent)
        # 插入到 stretch 之前（stretch 始终在最后）
        count = self.chat_layout.count()
        self.chat_layout.insertWidget(count - 1, bubble)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        sb = self.scroll_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _clear_chat(self):
        self._history.clear()
        # 移除所有气泡（保留最后的 stretch）
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        QTimer.singleShot(100, self._send_welcome)

    # ── 外部接口：更新 api_key ────────────────────────────
    def set_api_key(self, key: str):
        self.api_key = key