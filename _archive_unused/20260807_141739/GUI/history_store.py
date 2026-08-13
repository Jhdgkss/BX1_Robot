"""
BX1 GUI History Store
=====================

A single bounded SQLite database for GUI/debug history.

No per-message log files are created. Old data is automatically pruned
so the GUI history cannot grow forever.

Audio is deliberately NOT stored here.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional


class HistoryStore:
    def __init__(
        self,
        db_path: Optional[str] = None,
        retention_days: int = 30,
        max_messages: int = 10000,
        max_events: int = 50000,
    ) -> None:
        if db_path is None:
            data_dir = Path(__file__).resolve().parent / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(data_dir / "bx1_gui_history.sqlite3")

        self.db_path = str(db_path)
        self.retention_days = max(1, int(retention_days))
        self.max_messages = max(100, int(max_messages))
        self.max_events = max(1000, int(max_events))

        self._db = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
        )
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._create_tables()
        self.prune()

    def _create_tables(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                sender TEXT NOT NULL,
                text TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS metrics (
                message_id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                json_data TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                message_id TEXT,
                source TEXT,
                event TEXT,
                json_data TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_events_message
                ON events(message_id);

            CREATE INDEX IF NOT EXISTS idx_events_time
                ON events(timestamp);
            """
        )
        self._db.commit()

    def save_message(
        self,
        message_id: str,
        sender: str,
        text: str,
        timestamp: Optional[float] = None,
    ) -> None:
        timestamp = float(timestamp or time.time())

        self._db.execute(
            """
            INSERT OR REPLACE INTO messages
                (message_id, timestamp, sender, text)
            VALUES (?, ?, ?, ?)
            """,
            (
                str(message_id),
                timestamp,
                str(sender),
                str(text),
            ),
        )
        self._db.commit()

    def save_metrics(
        self,
        message_id: str,
        metrics: Dict[str, Any],
        timestamp: Optional[float] = None,
    ) -> None:
        timestamp = float(timestamp or time.time())

        self._db.execute(
            """
            INSERT OR REPLACE INTO metrics
                (message_id, timestamp, json_data)
            VALUES (?, ?, ?)
            """,
            (
                str(message_id),
                timestamp,
                json.dumps(metrics, ensure_ascii=False),
            ),
        )
        self._db.commit()

    def save_event(self, event: Dict[str, Any]) -> None:
        timestamp = float(event.get("timestamp") or time.time())

        self._db.execute(
            """
            INSERT INTO events
                (timestamp, message_id, source, event, json_data)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                event.get("message_id"),
                str(event.get("source", "")),
                str(event.get("event", "")),
                json.dumps(event.get("data", {}), ensure_ascii=False),
            ),
        )
        self._db.commit()

    def get_message(self, message_id: str) -> Optional[Dict[str, Any]]:
        row = self._db.execute(
            """
            SELECT message_id, timestamp, sender, text
            FROM messages
            WHERE message_id = ?
            """,
            (str(message_id),),
        ).fetchone()

        if row is None:
            return None

        return {
            "message_id": row[0],
            "timestamp": row[1],
            "sender": row[2],
            "text": row[3],
        }

    def get_metrics(self, message_id: str) -> Dict[str, Any]:
        row = self._db.execute(
            """
            SELECT json_data
            FROM metrics
            WHERE message_id = ?
            """,
            (str(message_id),),
        ).fetchone()

        if row is None:
            return {}

        try:
            return json.loads(row[0])
        except Exception:
            return {}

    def get_events(self, message_id: str) -> list[Dict[str, Any]]:
        rows = self._db.execute(
            """
            SELECT timestamp, source, event, json_data
            FROM events
            WHERE message_id = ?
            ORDER BY timestamp ASC
            """,
            (str(message_id),),
        ).fetchall()

        result = []

        for timestamp, source, event_name, json_data in rows:
            try:
                data = json.loads(json_data)
            except Exception:
                data = {}

            result.append(
                {
                    "timestamp": timestamp,
                    "source": source,
                    "event": event_name,
                    "message_id": str(message_id),
                    "data": data,
                }
            )

        return result

    def prune(self) -> None:
        cutoff = time.time() - (self.retention_days * 86400)

        self._db.execute(
            "DELETE FROM messages WHERE timestamp < ?",
            (cutoff,),
        )
        self._db.execute(
            "DELETE FROM metrics WHERE timestamp < ?",
            (cutoff,),
        )
        self._db.execute(
            "DELETE FROM events WHERE timestamp < ?",
            (cutoff,),
        )

        self._db.execute(
            """
            DELETE FROM messages
            WHERE message_id NOT IN (
                SELECT message_id
                FROM messages
                ORDER BY timestamp DESC
                LIMIT ?
            )
            """,
            (self.max_messages,),
        )

        self._db.execute(
            """
            DELETE FROM metrics
            WHERE message_id NOT IN (
                SELECT message_id
                FROM messages
            )
            """
        )

        self._db.execute(
            """
            DELETE FROM events
            WHERE id NOT IN (
                SELECT id
                FROM events
                ORDER BY timestamp DESC
                LIMIT ?
            )
            """,
            (self.max_events,),
        )

        self._db.commit()

    def close(self) -> None:
        try:
            self._db.commit()
            self._db.close()
        except Exception:
            pass
