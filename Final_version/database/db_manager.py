# database/db_manager.py — SQLite 数据库管理（支持多账号、多孩子）

import sqlite3
import hashlib
import os
from datetime import datetime, date, timedelta
import config


def _hash_pw(salt: str, password: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


class DatabaseManager:
    def __init__(self, db_path: str = config.DB_PATH):
        self.db_path = db_path
        self._init_db()

    # ── 连接 ─────────────────────────────────────────────
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    # ── 建表 & 迁移 ───────────────────────────────────────
    def _init_db(self):
        ddl = """
        -- 账号表（家长 / 儿童独立账号）
        CREATE TABLE IF NOT EXISTS accounts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            username   TEXT    NOT NULL UNIQUE,
            nickname   TEXT    NOT NULL DEFAULT '',
            password   TEXT    NOT NULL,
            salt       TEXT    NOT NULL,
            role       TEXT    NOT NULL DEFAULT 'parent',
            created_at TEXT    DEFAULT (datetime('now','localtime'))
        );

        -- 儿童档案表（家长创建 or 儿童账号注册后自动生成）
        CREATE TABLE IF NOT EXISTS users (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
            child_account_id  INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
            name              TEXT    NOT NULL DEFAULT '小朋友',
            age               INTEGER NOT NULL DEFAULT 10,
            avatar            TEXT    DEFAULT '🧒',
            created_at        TEXT    DEFAULT (datetime('now','localtime'))
        );

        -- 家长-孩子关联申请表
        CREATE TABLE IF NOT EXISTS link_requests (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            child_account_id  INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            status            TEXT    NOT NULL DEFAULT 'pending',
            created_at        TEXT    DEFAULT (datetime('now','localtime')),
            UNIQUE(parent_account_id, child_account_id)
        );

        -- 会话表
        CREATE TABLE IF NOT EXISTS sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            start_time TEXT    NOT NULL,
            end_time   TEXT,
            duration   INTEGER DEFAULT 0
        );

        -- 姿势记录表
        CREATE TABLE IF NOT EXISTS posture_records (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            ts          TEXT    NOT NULL,
            theta1      REAL,
            theta2      REAL,
            theta3      REAL,
            theta4      REAL,
            distance_cm REAL,
            is_good     INTEGER DEFAULT 0
        );

        -- 积分日志表
        CREATE TABLE IF NOT EXISTS points_log (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            ts      TEXT    NOT NULL,
            delta   INTEGER NOT NULL,
            reason  TEXT
        );

        -- 奖励表（每个孩子独立奖励）
        CREATE TABLE IF NOT EXISTS rewards (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name           TEXT    NOT NULL,
            description    TEXT,
            points_needed  INTEGER NOT NULL DEFAULT 100,
            is_redeemed    INTEGER DEFAULT 0
        );

        -- 设置表（每个家长账号一套设置，用 account_id:key 作唯一键）
        CREATE TABLE IF NOT EXISTS settings (
            account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            key        TEXT    NOT NULL,
            value      TEXT,
            PRIMARY KEY (account_id, key)
        );
        """
        with self._conn() as conn:
            for stmt in ddl.split(';'):
                s = stmt.strip()
                if s:
                    conn.execute(s)
        self._migrate_legacy()

    def _migrate_legacy(self):
        """迁移旧版数据库结构"""
        with self._conn() as conn:
            # settings 表老格式迁移
            cols = [r[1] for r in conn.execute("PRAGMA table_info(settings)").fetchall()]
            if "account_id" not in cols:
                conn.execute("ALTER TABLE settings RENAME TO settings_old")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS settings (
                        account_id INTEGER NOT NULL,
                        key TEXT NOT NULL,
                        value TEXT,
                        PRIMARY KEY (account_id, key)
                    )
                """)
                conn.execute("""
                    INSERT OR IGNORE INTO settings (account_id, key, value)
                    SELECT 1, key, value FROM settings_old
                """)
                conn.execute("DROP TABLE settings_old")

            # users 表新增列
            ucols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
            if "parent_account_id" not in ucols:
                conn.execute("ALTER TABLE users ADD COLUMN parent_account_id INTEGER")
            if "avatar" not in ucols:
                conn.execute("ALTER TABLE users ADD COLUMN avatar TEXT DEFAULT '🧒'")
            if "child_account_id" not in ucols:
                conn.execute("ALTER TABLE users ADD COLUMN child_account_id INTEGER")

            # rewards 表新增 user_id
            rcols = [r[1] for r in conn.execute("PRAGMA table_info(rewards)").fetchall()]
            if "user_id" not in rcols:
                conn.execute("ALTER TABLE rewards ADD COLUMN user_id INTEGER DEFAULT 1")

    # ════════════════════════════════════════════════════
    # 账号管理
    # ════════════════════════════════════════════════════

    def account_exists(self, username: str) -> bool:
        with self._conn() as conn:
            r = conn.execute(
                "SELECT id FROM accounts WHERE username=?", (username,)).fetchone()
            return r is not None

    def register(self, username: str, password: str,
                 nickname: str = "", role: str = "parent") -> dict:
        """注册新账号，返回 account dict"""
        salt = os.urandom(16).hex()
        pw_hash = _hash_pw(salt, password)
        nickname = nickname or username
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO accounts (username, nickname, password, salt, role)"
                " VALUES (?,?,?,?,?)",
                (username, nickname, pw_hash, salt, role))
            account_id = cur.lastrowid

            if role == "parent":
                # 家长自动创建第一个孩子档案（未绑定儿童账号）
                conn.execute(
                    "INSERT INTO users (parent_account_id, name, age, avatar)"
                    " VALUES (?,?,?,?)",
                    (account_id, "小朋友", 10, "🧒"))
                child_id = conn.execute(
                    "SELECT last_insert_rowid() AS id").fetchone()["id"]
                self._seed_rewards(conn, child_id)
            else:
                # 儿童账号自动创建档案，绑定 child_account_id，等待家长关联
                conn.execute(
                    "INSERT INTO users (child_account_id, name, age, avatar)"
                    " VALUES (?,?,?,?)",
                    (account_id, nickname, 10, "🧒"))
                child_id = conn.execute(
                    "SELECT last_insert_rowid() AS id").fetchone()["id"]
                self._seed_rewards(conn, child_id)

        return self.get_account_by_id(account_id)

    def login(self, username: str, password: str):
        """验证账号密码，成功返回 account dict，失败返回 None"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM accounts WHERE username=?", (username,)).fetchone()
        if not row:
            return None
        if _hash_pw(row["salt"], password) != row["password"]:
            return None
        return dict(row)

    def get_account_by_id(self, account_id: int) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
            return dict(row) if row else {}

    def update_account_nickname(self, account_id: int, nickname: str):
        with self._conn() as conn:
            conn.execute(
                "UPDATE accounts SET nickname=? WHERE id=?", (nickname, account_id))

    def change_password(self, account_id: int, old_pw: str, new_pw: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT salt, password FROM accounts WHERE id=?", (account_id,)).fetchone()
        if not row or _hash_pw(row["salt"], old_pw) != row["password"]:
            return False
        salt = os.urandom(16).hex()
        with self._conn() as conn:
            conn.execute(
                "UPDATE accounts SET password=?, salt=? WHERE id=?",
                (_hash_pw(salt, new_pw), salt, account_id))
        return True

    # ════════════════════════════════════════════════════
    # 孩子档案管理（family）
    # ════════════════════════════════════════════════════

    def get_children(self, parent_account_id: int) -> list:
        """返回该家长下所有孩子档案（手动创建 + 已关联的儿童账号）"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM users WHERE parent_account_id=? ORDER BY id",
                (parent_account_id,)).fetchall()
            return [dict(r) for r in rows]

    def get_user_by_child_account(self, child_account_id: int) -> dict:
        """通过儿童账号 ID 获取其档案"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE child_account_id=?",
                (child_account_id,)).fetchone()
            return dict(row) if row else {}

    # ════════════════════════════════════════════════════
    # 家长-孩子关联申请
    # ════════════════════════════════════════════════════

    def search_child_account(self, username: str) -> dict:
        """搜索儿童账号（仅 role=child）"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, username, nickname FROM accounts"
                " WHERE username=? AND role='child'",
                (username,)).fetchone()
            return dict(row) if row else {}

    def send_link_request(self, parent_account_id: int,
                          child_account_id: int) -> str:
        """
        发送关联申请。
        返回: 'ok' | 'already_linked' | 'already_pending' | 'already_rejected'
        """
        # 是否已关联
        child_user = self.get_user_by_child_account(child_account_id)
        if child_user.get("parent_account_id"):
            return "already_linked"
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT status FROM link_requests"
                " WHERE parent_account_id=? AND child_account_id=?",
                (parent_account_id, child_account_id)).fetchone()
            if existing:
                return f"already_{existing['status']}"
            conn.execute(
                "INSERT INTO link_requests (parent_account_id, child_account_id)"
                " VALUES (?,?)",
                (parent_account_id, child_account_id))
        return "ok"

    def get_pending_requests(self, child_account_id: int) -> list:
        """获取儿童账号收到的所有 pending 申请（附带家长昵称）"""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT lr.id, lr.parent_account_id, lr.created_at,
                       a.username, a.nickname
                FROM link_requests lr
                JOIN accounts a ON a.id = lr.parent_account_id
                WHERE lr.child_account_id=? AND lr.status='pending'
                ORDER BY lr.created_at DESC
            """, (child_account_id,)).fetchall()
            return [dict(r) for r in rows]

    def accept_link_request(self, request_id: int,
                            child_account_id: int) -> bool:
        """孩子接受关联申请，将 parent_account_id 写入其档案"""
        with self._conn() as conn:
            req = conn.execute(
                "SELECT * FROM link_requests WHERE id=? AND child_account_id=?"
                " AND status='pending'",
                (request_id, child_account_id)).fetchone()
            if not req:
                return False
            # 更新档案
            conn.execute(
                "UPDATE users SET parent_account_id=? WHERE child_account_id=?",
                (req["parent_account_id"], child_account_id))
            # 标记申请为已接受，同时拒绝其他 pending 申请（只能有一个家长）
            conn.execute(
                "UPDATE link_requests SET status='accepted' WHERE id=?",
                (request_id,))
            conn.execute(
                "UPDATE link_requests SET status='rejected'"
                " WHERE child_account_id=? AND id!=? AND status='pending'",
                (child_account_id, request_id))
        return True

    def reject_link_request(self, request_id: int,
                            child_account_id: int) -> bool:
        """孩子拒绝关联申请"""
        with self._conn() as conn:
            conn.execute(
                "UPDATE link_requests SET status='rejected'"
                " WHERE id=? AND child_account_id=? AND status='pending'",
                (request_id, child_account_id))
        return True

    def get_sent_requests(self, parent_account_id: int) -> list:
        """家长查看已发出的申请状态"""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT lr.id, lr.status, lr.created_at,
                       a.username, a.nickname
                FROM link_requests lr
                JOIN accounts a ON a.id = lr.child_account_id
                WHERE lr.parent_account_id=?
                ORDER BY lr.created_at DESC
            """, (parent_account_id,)).fetchall()
            return [dict(r) for r in rows]

    def add_child(self, parent_account_id: int,
                  name: str, age: int, avatar: str = "🧒") -> dict:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO users (parent_account_id, name, age, avatar)"
                " VALUES (?,?,?,?)",
                (parent_account_id, name, age, avatar))
            child_id = cur.lastrowid
            self._seed_rewards(conn, child_id)
        return self.get_user(child_id)

    def delete_child(self, child_id: int, parent_account_id: int) -> bool:
        """删除孩子档案（同时级联删除其会话、积分、奖励）"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE id=? AND parent_account_id=?",
                (child_id, parent_account_id)).fetchone()
            if not row:
                return False
            # 手动删级联数据（SQLite 可能未启用 FK 级联）
            sessions = conn.execute(
                "SELECT id FROM sessions WHERE user_id=?", (child_id,)).fetchall()
            for s in sessions:
                conn.execute(
                    "DELETE FROM posture_records WHERE session_id=?", (s["id"],))
            conn.execute("DELETE FROM sessions WHERE user_id=?", (child_id,))
            conn.execute("DELETE FROM points_log WHERE user_id=?", (child_id,))
            conn.execute("DELETE FROM rewards WHERE user_id=?", (child_id,))
            conn.execute("DELETE FROM users WHERE id=?", (child_id,))
        return True

    def _seed_rewards(self, conn, child_id: int):
        """为新孩子插入默认奖励"""
        defaults = [
            ("🎮 游戏时间", "额外30分钟游戏时间", 200),
            ("🍦 冰淇淋",   "一个喜欢的口味",     150),
            ("📚 新书",     "一本自选图书",       300),
            ("🎬 电影之夜", "一起看一部电影",     250),
            ("🏖️ 外出游玩", "周末出游计划",       500),
        ]
        for name, desc, pts in defaults:
            conn.execute(
                "INSERT OR IGNORE INTO rewards (user_id, name, description, points_needed)"
                " VALUES (?,?,?,?)",
                (child_id, name, desc, pts))

    # ════════════════════════════════════════════════════
    # 用户（孩子档案）
    # ════════════════════════════════════════════════════

    def get_user(self, uid: int) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE id=?", (uid,)).fetchone()
            return dict(row) if row else {"id": uid, "name": "小朋友", "age": 10, "avatar": "🧒"}

    def update_user(self, name: str, age: int, avatar: str = None, uid: int = 1):
        with self._conn() as conn:
            if avatar is not None:
                conn.execute(
                    "UPDATE users SET name=?, age=?, avatar=? WHERE id=?",
                    (name, age, avatar, uid))
            else:
                conn.execute(
                    "UPDATE users SET name=?, age=? WHERE id=?", (name, age, uid))

    # ════════════════════════════════════════════════════
    # 会话
    # ════════════════════════════════════════════════════

    def start_session(self, uid: int = 1) -> int:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO sessions (user_id, start_time) VALUES (?,?)", (uid, now))
            return cur.lastrowid

    def end_session(self, session_id: int, duration_sec: int):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conn() as conn:
            conn.execute(
                "UPDATE sessions SET end_time=?, duration=? WHERE id=?",
                (now, duration_sec, session_id))

    # ════════════════════════════════════════════════════
    # 姿势记录
    # ════════════════════════════════════════════════════

    def insert_posture(self, session_id, theta1, theta2, theta3, theta4,
                       distance_cm, is_good):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO posture_records
                  (session_id,ts,theta1,theta2,theta3,theta4,distance_cm,is_good)
                VALUES (?,?,?,?,?,?,?,?)
            """, (session_id, now, theta1, theta2, theta3, theta4,
                  distance_cm, int(is_good)))

    # ════════════════════════════════════════════════════
    # 积分
    # ════════════════════════════════════════════════════

    def add_points(self, delta: int, reason: str, uid: int = 1):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO points_log (user_id,ts,delta,reason) VALUES (?,?,?,?)",
                (uid, now, delta, reason))

    def get_total_points(self, uid: int = 1) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(delta),0) AS total FROM points_log WHERE user_id=?",
                (uid,)).fetchone()
            return int(row["total"])

    def redeem_reward(self, reward_id: int, uid: int = 1) -> bool:
        reward = self.get_reward(reward_id)
        total  = self.get_total_points(uid)
        if not reward or total < reward["points_needed"]:
            return False
        with self._conn() as conn:
            conn.execute("UPDATE rewards SET is_redeemed=1 WHERE id=?", (reward_id,))
            conn.execute(
                "INSERT INTO points_log (user_id,ts,delta,reason) VALUES (?,?,?,?)",
                (uid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 -reward["points_needed"], f"兑换：{reward['name']}"))
        return True

    # ════════════════════════════════════════════════════
    # 奖励管理
    # ════════════════════════════════════════════════════

    def get_rewards(self, uid: int = 1) -> list:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM rewards WHERE user_id=? ORDER BY points_needed",
                (uid,)).fetchall()
            return [dict(r) for r in rows]

    def get_reward(self, reward_id: int) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM rewards WHERE id=?", (reward_id,)).fetchone()
            return dict(row) if row else None

    def add_reward(self, name: str, description: str,
                   points_needed: int, uid: int = 1):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO rewards (user_id, name, description, points_needed)"
                " VALUES (?,?,?,?)",
                (uid, name, description, points_needed))

    def update_reward(self, reward_id: int, name: str,
                      description: str, points_needed: int):
        with self._conn() as conn:
            conn.execute(
                "UPDATE rewards SET name=?,description=?,points_needed=? WHERE id=?",
                (name, description, points_needed, reward_id))

    def delete_reward(self, reward_id: int):
        with self._conn() as conn:
            conn.execute("DELETE FROM rewards WHERE id=?", (reward_id,))

    # ════════════════════════════════════════════════════
    # 统计查询
    # ════════════════════════════════════════════════════

    def get_daily_stats(self, uid: int = 1, target_date: date = None) -> dict:
        if target_date is None:
            target_date = date.today()
        d_str = target_date.strftime("%Y-%m-%d")
        with self._conn() as conn:
            row = conn.execute("""
                SELECT
                  COUNT(*)                              AS record_count,
                  COALESCE(AVG(distance_cm),0)          AS avg_distance,
                  COALESCE(AVG(is_good)*100,0)          AS good_ratio,
                  COALESCE(AVG(ABS(theta1)),0)          AS avg_theta1,
                  COALESCE(AVG(ABS(theta2)),0)          AS avg_theta2,
                  COALESCE(AVG(ABS(theta3)),0)          AS avg_theta3,
                  COALESCE(AVG(ABS(theta4)),0)          AS avg_theta4
                FROM posture_records pr
                JOIN sessions s ON pr.session_id = s.id
                WHERE s.user_id=? AND pr.ts LIKE ?
            """, (uid, d_str + "%")).fetchone()
            duration_row = conn.execute("""
                SELECT COALESCE(SUM(duration),0) AS total_sec
                FROM sessions WHERE user_id=? AND start_time LIKE ?
            """, (uid, d_str + "%")).fetchone()
            return {
                "date"         : d_str,
                "record_count" : row["record_count"],
                "avg_distance" : round(row["avg_distance"], 1),
                "good_ratio"   : round(row["good_ratio"],   1),
                "avg_theta1"   : round(row["avg_theta1"],   1),
                "avg_theta2"   : round(row["avg_theta2"],   1),
                "avg_theta3"   : round(row["avg_theta3"],   1),
                "avg_theta4"   : round(row["avg_theta4"],   1),
                "total_sec"    : int(duration_row["total_sec"]),
            }

    def get_weekly_stats(self, uid: int = 1, end_date: date = None) -> list:
        if end_date is None:
            end_date = date.today()
        return [self.get_daily_stats(uid, end_date - timedelta(days=i))
                for i in range(6, -1, -1)]

    def get_hourly_usage_today(self, uid: int = 1) -> dict:
        d_str = date.today().strftime("%Y-%m-%d")
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT strftime('%H', pr.ts) AS hour, COUNT(*) AS cnt
                FROM posture_records pr
                JOIN sessions s ON pr.session_id = s.id
                WHERE s.user_id=? AND pr.ts LIKE ?
                GROUP BY hour ORDER BY hour
            """, (uid, d_str + "%")).fetchall()
        hour_map = {str(h).zfill(2): 0 for h in range(24)}
        for r in rows:
            hour_map[r["hour"]] = r["cnt"] * config.RECORD_INTERVAL_SEC // 60
        return hour_map

    def get_longterm_stats(self, uid: int = 1, days: int = 30) -> list:
        end   = date.today()
        start = end - timedelta(days=days - 1)
        results = []
        cur = start
        while cur <= end:
            results.append(self.get_daily_stats(uid, cur))
            cur += timedelta(days=1)
        return results

    # ════════════════════════════════════════════════════
    # 设置（按 account_id 存储）
    # ════════════════════════════════════════════════════

    def get_setting(self, key: str, default=None, account_id: int = 1):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE account_id=? AND key=?",
                (account_id, key)).fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value, account_id: int = 1):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (account_id, key, value)"
                " VALUES (?,?,?)",
                (account_id, key, str(value)))

    def get_all_settings(self, account_id: int = 1) -> dict:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT key,value FROM settings WHERE account_id=?",
                (account_id,)).fetchall()
            return {r["key"]: r["value"] for r in rows}