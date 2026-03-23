# gui/rewards_tab.py — 积分奖励标签页（支持 uid 参数）

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QSizePolicy, QMessageBox, QProgressBar
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor

from database.db_manager import DatabaseManager


class RewardsTab(QWidget):
    def __init__(self, db: DatabaseManager, uid: int = 1, parent=None):
        super().__init__(parent)
        self.db  = db
        self.uid = uid
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        # ── 顶部积分展示 ─────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(16)

        points_card = QFrame()
        points_card.setObjectName("card")
        points_card.setMinimumHeight(130)
        pc_lay = QVBoxLayout(points_card)
        pc_lay.setContentsMargins(20, 16, 20, 16)
        pc_lay.setSpacing(6)

        pts_header = QHBoxLayout()
        star_lbl = QLabel("⭐")
        star_lbl.setFont(QFont("Segoe UI Emoji", 24))
        pts_header.addWidget(star_lbl)
        pts_title = QLabel("当前积分总额")
        pts_title.setObjectName("sectionTitle")
        pts_title.setFont(QFont("Microsoft YaHei", 14))
        pts_header.addWidget(pts_title)
        pts_header.addStretch()
        pc_lay.addLayout(pts_header)

        self.points_lbl = QLabel("0")
        self.points_lbl.setFont(QFont("Microsoft YaHei", 42, QFont.Bold))
        self.points_lbl.setStyleSheet("color: #F0883E;")
        pc_lay.addWidget(self.points_lbl)

        self.points_tip = QLabel("继续保持良好用眼习惯来赚取更多积分！")
        self.points_tip.setObjectName("metricLabel")
        pc_lay.addWidget(self.points_tip)
        top.addWidget(points_card, 2)

        stat_col = QVBoxLayout()
        stat_col.setSpacing(8)
        for key, icon, label in [
            ("today_pts",  "📅", "今日获得"),
            ("redeemed",   "🎁", "已兑换奖励"),
            ("available",  "✨", "可兑换奖励"),
        ]:
            card = QFrame()
            card.setObjectName("card")
            cl = QHBoxLayout(card)
            cl.setContentsMargins(14, 10, 14, 10)
            ic_l = QLabel(icon); ic_l.setFont(QFont("Segoe UI Emoji", 14))
            lbl  = QLabel(label); lbl.setObjectName("metricLabel"); lbl.setFixedWidth(90)
            val  = QLabel("—")
            val.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
            val.setStyleSheet("color:#58A6FF;")
            cl.addWidget(ic_l); cl.addWidget(lbl); cl.addStretch(); cl.addWidget(val)
            setattr(self, f"stat_{key}", val)
            stat_col.addWidget(card)
        top.addLayout(stat_col, 1)
        root.addLayout(top)

        # ── 奖励列表 ─────────────────────────────────
        list_header = QHBoxLayout()
        lh_title = QLabel("🎁  奖励商城")
        lh_title.setObjectName("sectionTitle")
        lh_title.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        list_header.addWidget(lh_title)
        list_header.addStretch()
        self.refresh_btn = QPushButton("🔄  刷新")
        self.refresh_btn.clicked.connect(self.refresh)
        list_header.addWidget(self.refresh_btn)
        root.addLayout(list_header)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["图标/名称", "描述", "所需积分", "状态", "操作"])
        for i, mode in enumerate([QHeaderView.ResizeToContents,
                                   QHeaderView.Stretch,
                                   QHeaderView.ResizeToContents,
                                   QHeaderView.ResizeToContents,
                                   QHeaderView.ResizeToContents]):
            self.table.horizontalHeader().setSectionResizeMode(i, mode)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setShowGrid(False)
        root.addWidget(self.table, 1)

        # 进度提示
        prog_frame = QFrame()
        prog_frame.setObjectName("card")
        pg_lay = QVBoxLayout(prog_frame)
        pg_lay.setContentsMargins(14, 10, 14, 10)
        pg_lay.setSpacing(4)
        next_lbl = QLabel("距离下一个奖励还差…")
        next_lbl.setObjectName("metricLabel")
        pg_lay.addWidget(next_lbl)
        self.next_bar = QProgressBar()
        self.next_bar.setRange(0, 100)
        self.next_bar.setFixedHeight(10)
        pg_lay.addWidget(self.next_bar)
        self.next_text = QLabel("")
        self.next_text.setObjectName("metricLabel")
        pg_lay.addWidget(self.next_text)
        root.addWidget(prog_frame)

    def showEvent(self, event):
        """每次切换到此页时自动刷新"""
        super().showEvent(event)
        self.refresh()

    def refresh(self):
        total   = self.db.get_total_points(self.uid)
        rewards = self.db.get_rewards(self.uid)

        self.points_lbl.setText(str(total))
        redeemed  = sum(1 for r in rewards if r["is_redeemed"])
        available = sum(1 for r in rewards
                        if not r["is_redeemed"] and r["points_needed"] <= total)
        self.stat_redeemed.setText(str(redeemed))
        self.stat_available.setText(str(available))
        self.stat_today_pts.setText(str(total))

        self.table.setRowCount(0)
        for r in rewards:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setRowHeight(row, 46)

            name_item = QTableWidgetItem(r["name"])
            name_item.setFont(QFont("Microsoft YaHei", 12))
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(r.get("description", "")))

            pts_item = QTableWidgetItem(f"⭐ {r['points_needed']}")
            pts_item.setTextAlignment(Qt.AlignCenter)
            pts_item.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
            self.table.setItem(row, 2, pts_item)

            if r["is_redeemed"]:
                status = QTableWidgetItem("✅ 已兑换")
                status.setForeground(QColor("#3FB950"))
            elif r["points_needed"] <= total:
                status = QTableWidgetItem("🟢 可兑换")
                status.setForeground(QColor("#58A6FF"))
            else:
                status = QTableWidgetItem(f"🔒 差 {r['points_needed']-total} 分")
                status.setForeground(QColor("#8B949E"))
            status.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 3, status)

            btn = QPushButton("兑 换")
            btn.setObjectName("primaryBtn")
            btn.setFixedSize(72, 30)
            btn.setEnabled(not r["is_redeemed"] and r["points_needed"] <= total)
            btn.clicked.connect(
                lambda checked, rid=r["id"], rn=r["name"]: self._redeem(rid, rn))
            self.table.setCellWidget(row, 4, btn)

        not_redeemed = [r for r in rewards if not r["is_redeemed"]]
        if not_redeemed:
            next_r = min(not_redeemed, key=lambda x: x["points_needed"])
            needed = next_r["points_needed"]
            pct    = min(100, int(total / needed * 100))
            self.next_bar.setValue(pct)
            self.next_text.setText(
                f"「{next_r['name']}」需要 {needed} 积分，"
                f"当前 {total} 分，还差 {max(0, needed - total)} 分")
        else:
            self.next_bar.setValue(100)
            self.next_text.setText("所有奖励已兑换！请让家长添加新奖励。")

    def _redeem(self, reward_id, reward_name):
        msg = QMessageBox(self)
        msg.setWindowTitle("确认兑换")
        msg.setText(f"确定要兑换「{reward_name}」吗？")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.No)
        if msg.exec_() == QMessageBox.Yes:
            ok = self.db.redeem_reward(reward_id, self.uid)
            if ok:
                QMessageBox.information(
                    self, "兑换成功",
                    f"🎉 「{reward_name}」兑换成功！\n请告知家长确认奖励。")
            else:
                QMessageBox.warning(self, "积分不足", "积分不足，无法兑换此奖励。")
            self.refresh()