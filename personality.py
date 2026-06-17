import sqlite3
from pathlib import Path


class ProductionLogger:
    """Persistent event store with WAL-mode SQLite for SD-card longevity."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize_database()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        # WAL mode + NORMAL sync eliminates continuous tiny writes
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _initialize_database(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    notification_id TEXT,
                    category TEXT,
                    urgency TEXT,
                    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    action TEXT,
                    response_time_sec INTEGER
                );
            """)

    def log_received(self, target: dict):
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO events (id, notification_id, category, urgency, action) "
                "VALUES (?, ?, ?, ?, 'received')",
                (
                    target["id"],
                    target["id"],
                    target.get("category", "general"),
                    target.get("urgency", "low"),
                )
            )

    def log_action(self, notification_id: str, action: str, response_time_sec: int):
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE events SET action = ?, response_time_sec = ? "
                "WHERE notification_id = ? AND action = 'received'",
                (action, response_time_sec, notification_id)
            )
