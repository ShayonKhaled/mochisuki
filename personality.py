import logging
import sqlite3
from pathlib import Path


class ProductionLogger:
    """Persistent event store with WAL-mode SQLite for SD-card longevity."""

    _CLEANUP_EVERY = 50   # call cleanup_old_events every N inserts

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize_database()
        self._insert_count: int = 0

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
        self._insert_count += 1
        if self._insert_count % self._CLEANUP_EVERY == 0:
            self.cleanup_old_events()

    def cleanup_old_events(self, max_age_days: int = 30):
        """Purge events older than *max_age_days* to prevent unbounded DB growth."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM events WHERE received_at < datetime('now', ?)",
                (f"-{max_age_days} days",),
            )
        deleted = cursor.rowcount
        if deleted:
            logger = logging.getLogger("mochisuki.db")
            logger.info("Cleaned %d old event(s) (>%d days)", deleted, max_age_days)

    def log_action(self, notification_id: str, action: str, response_time_sec: int):
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE events SET action = ?, response_time_sec = ? "
                "WHERE notification_id = ? AND action = 'received'",
                (action, response_time_sec, notification_id)
            )
