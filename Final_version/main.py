# main.py — 程序入口（含登录流程）

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication, QSplashScreen
from PyQt5.QtCore    import Qt, QTimer
from PyQt5.QtGui     import QFont, QPixmap, QColor, QPainter

from database.db_manager import DatabaseManager
from gui.login_window    import LoginDialog
from gui.main_window     import MainWindow

_app: QApplication = None
_main_win: MainWindow = None


def make_splash() -> QSplashScreen:
    w, h = 500, 280
    pix  = QPixmap(w, h)
    pix.fill(QColor("#0D1117"))

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)

    painter.setBrush(QColor(31, 111, 235, 40))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(w - 140, -60, 220, 220)
    painter.drawEllipse(-60, h - 140, 200, 200)

    painter.setPen(QColor("#58A6FF"))
    painter.setFont(QFont("Microsoft YaHei", 26, QFont.Bold))
    painter.drawText(0, 60, w, 50, Qt.AlignCenter, "👁  VisionGuard")

    painter.setPen(QColor("#8B949E"))
    painter.setFont(QFont("Microsoft YaHei", 12))
    painter.drawText(0, 115, w, 30, Qt.AlignCenter, "儿童近视风险预防系统")

    painter.setPen(QColor("#388BFD"))
    painter.setFont(QFont("Microsoft YaHei", 9))
    painter.drawText(0, 160, w, 24, Qt.AlignCenter,
                     "MediaPipe  ·  OpenCV  ·  PyQt5  ·  SQLite")

    painter.setPen(QColor("#484F58"))
    painter.setFont(QFont("Microsoft YaHei", 9))
    painter.drawText(0, 245, w, 20, Qt.AlignCenter, "正在初始化，请稍候…")
    painter.end()

    splash = QSplashScreen(pix, Qt.WindowStaysOnTopHint)
    return splash


def show_login(db: DatabaseManager):
    """显示登录对话框，登录成功后打开主窗口"""
    global _main_win

    while True:   # 允许登录失败后重试，而不是直接退出
        dlg = LoginDialog(db)
        center = _app.desktop().screenGeometry()
        dlg.move(
            center.width()  // 2 - dlg.width()  // 2,
            center.height() // 2 - dlg.height() // 2,
        )

        result = dlg.exec_()

        # 用户点了关闭按钮（非登录成功）→ 询问是否退出
        if result != LoginDialog.Accepted or dlg.account is None:
            from PyQt5.QtWidgets import QMessageBox
            ans = QMessageBox.question(
                None, "退出", "确定要退出 VisionGuard 吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if ans == QMessageBox.Yes:
                sys.exit(0)
            continue   # 重新显示登录窗口

        account = dlg.account
        try:
            _main_win = MainWindow(db, account)
            _main_win.show()
            return
        except Exception as e:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(
                None, "启动失败",
                f"加载主界面时发生错误：\n{e}\n\n请检查数据库文件后重试。"
            )
            # 继续循环，重新显示登录窗口


def restart_to_login():
    """退出登录时重新显示登录界面"""
    global _main_win
    db = DatabaseManager()
    show_login(db)


def main():
    global _app

    _app = QApplication(sys.argv)
    _app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    _app.setAttribute(Qt.AA_UseHighDpiPixmaps,    True)
    _app.setQuitOnLastWindowClosed(False)   # 防止最后一个窗口关闭时自动退出
    _app.setApplicationName("VisionGuard")

    # 加载样式表
    qss_path = os.path.join(os.path.dirname(__file__), "assets", "style.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            _app.setStyleSheet(f.read())

    # 启动画面
    splash = make_splash()
    splash.show()
    _app.processEvents()

    # 初始化数据库
    db = DatabaseManager()

    def _after_splash():
        splash.close()
        try:
            show_login(db)
        except SystemExit:
            raise   # sys.exit() 正常传播
        except Exception as e:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(None, "严重错误", f"程序启动失败：\n{e}")
            sys.exit(1)

    QTimer.singleShot(1600, _after_splash)
    sys.exit(_app.exec_())


if __name__ == "__main__":
    main()