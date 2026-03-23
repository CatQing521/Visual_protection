# core/voice_alert.py — 语音提醒（pyttsx3，后台线程）

import threading
import queue
import time
import pyttsx3


class VoiceAlert:
    """
    后台线程语音提醒器。
    • 使用队列避免阻塞主线程
    • 同类提醒设置冷却时间
    """

    MESSAGES = {
        "距离过近"  : "请注意，您距离屏幕太近，建议保持50厘米以上的距离。",
        "歪坐"      : "请注意坐姿，检测到您正在歪坐，请保持肩部水平。",
        "低头"      : "请注意坐姿，检测到您正在低头，请抬起头部，保持正确坐姿。",
        "抬头"      : "请放松头部，保持自然端正的坐姿。",
        "趴伏/前倾" : "请注意坐姿，检测到您身体前倾，请坐直。",
        "歪头"      : "请注意坐姿，检测到您歪头，请保持头部端正。",
        "休息提醒"  : "您已连续用眼较长时间，请休息一下，做一做眼保健操。",
        "奖励积分"  : "太棒了！您的良好坐姿获得了积分奖励，继续保持！",
        "综合姿态异常": "检测到综合坐姿偏差，请调整坐姿，保持端正舒适的姿态。",
    }

    def __init__(self, rate=180, volume=0.9):
        self._q       = queue.Queue()
        self._running = False
        self._thread  = None
        self._rate    = rate
        self._volume  = volume
        self._last_spoken: dict[str, float] = {}
        self._cooldown = 15.0   # 同类提醒最短间隔（秒）

    # ── 公共接口 ─────────────────────────────────────────
    def start(self):
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        self._q.put(None)    # 哨兵

    def speak(self, alert_type: str, force: bool = False):
        """将提醒类型加入队列（自动查找对应文本）"""
        now = time.time()
        last = self._last_spoken.get(alert_type, 0)
        if not force and (now - last) < self._cooldown:
            return
        self._last_spoken[alert_type] = now
        msg = self.MESSAGES.get(alert_type, alert_type)
        # 清空旧内容，避免积压
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except queue.Empty:
                break
        self._q.put(msg)

    def speak_text(self, text: str):
        """直接播报自定义文本"""
        self._q.put(text)

    # ── 工作线程 ─────────────────────────────────────────
    def _worker(self):
        engine = pyttsx3.init()
        engine.setProperty("rate",   self._rate)
        engine.setProperty("volume", self._volume)
        # 优先中文语音
        voices = engine.getProperty("voices")
        for v in voices:
            if "chinese" in v.name.lower() or "zh" in v.id.lower():
                engine.setProperty("voice", v.id)
                break

        while self._running:
            try:
                msg = self._q.get(timeout=1)
            except queue.Empty:
                continue
            if msg is None:
                break
            try:
                engine.say(msg)
                engine.runAndWait()
            except Exception:
                pass

    def set_cooldown(self, seconds: float):
        self._cooldown = seconds