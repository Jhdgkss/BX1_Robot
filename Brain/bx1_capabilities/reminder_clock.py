from __future__ import annotations

import sqlite3
import threading
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo


SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
    reminder_id TEXT PRIMARY KEY,
    message TEXT NOT NULL,
    trigger_datetime TEXT NOT NULL,
    timezone TEXT NOT NULL,
    recurrence TEXT NOT NULL DEFAULT '',
    reminder_or_alarm TEXT NOT NULL DEFAULT 'reminder',
    enabled INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    fired_at TEXT,
    dismissed_at TEXT,
    snooze_count INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'brain'
);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(enabled, status, trigger_datetime);
"""


class ReminderClockService:
    capability_id = "reminder_clock"
    version = "1.0.0"

    def __init__(
        self, root: Path, *, timezone_name: str = "Europe/London",
        announce: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        activity: Optional[Callable[[str, str], None]] = None,
        now: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "reminders.db"
        self.timezone_name = timezone_name
        self.tz = ZoneInfo(timezone_name)
        self.announce = announce or (lambda _text, _record: None)
        self.activity = activity or (lambda _event, _message: None)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._condition = threading.Condition()
        self._stop = False
        self._thread: Optional[threading.Thread] = None
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with closing(self._connect()) as connection:
            connection.executescript(SCHEMA)
            connection.commit()

    def start(self) -> None:
        with self._condition:
            if self._thread and self._thread.is_alive():
                return
            self._stop = False
            self._thread = threading.Thread(target=self._scheduler_loop, name="bx1-reminder-clock", daemon=True)
            self._thread.start()
        self.activity("scheduler_started", "Reminder Clock scheduler loaded pending reminders.")

    def shutdown(self) -> None:
        with self._condition:
            self._stop = True
            self._condition.notify_all()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self.activity("scheduler_stopped", "Reminder Clock scheduler stopped.")

    def _wake_scheduler(self) -> None:
        with self._condition:
            self._condition.notify_all()

    def parse_trigger(self, value: str, *, base: Optional[datetime] = None) -> datetime:
        text = " ".join(str(value or "").strip().lower().split())
        local_now = (base or self._now()).astimezone(self.tz)
        if text.startswith("in "):
            import re
            match = re.fullmatch(r"in\s+(\d+)\s+(minute|minutes|hour|hours|day|days)", text)
            if not match:
                raise ValueError("Unsupported relative reminder time")
            amount = int(match.group(1))
            unit = match.group(2)
            delta = timedelta(minutes=amount) if "minute" in unit else timedelta(hours=amount) if "hour" in unit else timedelta(days=amount)
            return (local_now + delta).astimezone(timezone.utc)
        if text.startswith(("today", "tomorrow")):
            import re
            match = re.fullmatch(r"(today|tomorrow)(?:\s+at\s+(\d{1,2})(?::(\d{2}))?)?", text)
            if not match:
                raise ValueError("Unsupported reminder time")
            day = local_now.date() + (timedelta(days=1) if match.group(1) == "tomorrow" else timedelta())
            hour, minute = int(match.group(2) or 9), int(match.group(3) or 0)
            return datetime(day.year, day.month, day.day, hour, minute, tzinfo=self.tz).astimezone(timezone.utc)
        import re
        match = re.fullmatch(r"(?:at|for\s+)?(\d{1,2}):(\d{2})", text)
        if match:
            candidate = local_now.replace(hour=int(match.group(1)), minute=int(match.group(2)), second=0, microsecond=0)
            if candidate <= local_now:
                candidate += timedelta(days=1)
            return candidate.astimezone(timezone.utc)
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Reminder time must be relative, local HH:MM, or ISO datetime") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=self.tz)
        return parsed.astimezone(timezone.utc)

    def create(self, parameters: Dict[str, Any], *, alarm: bool = False) -> Dict[str, Any]:
        message = str(parameters.get("reminder_text") or parameters.get("message") or parameters.get("text") or "").strip()
        if not message:
            return {"ok": False, "error": "missing_message", "message": "Reminder text is required."}
        trigger = self.parse_trigger(str(parameters.get("trigger_datetime") or parameters.get("trigger_text") or ""))
        recurrence = str(parameters.get("recurrence") or "").strip().lower()
        if recurrence not in {"", "daily", "weekly"}:
            return {"ok": False, "error": "invalid_recurrence", "message": "Recurrence must be daily or weekly."}
        reminder_id = uuid.uuid4().hex
        created = self._now().astimezone(timezone.utc).isoformat()
        with closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO reminders VALUES (?, ?, ?, ?, ?, ?, 1, 'pending', ?, NULL, NULL, 0, ?)",
                (reminder_id, message, trigger.isoformat(), self.timezone_name, recurrence,
                 "alarm" if alarm else "reminder", created, str(parameters.get("source") or "brain")),
            )
            connection.commit()
        self.activity("reminder_scheduled", f"Reminder {reminder_id} scheduled for {trigger.isoformat()}.")
        self._wake_scheduler()
        return {"ok": True, "reminder_id": reminder_id, "message": message,
                "trigger_datetime": trigger.isoformat(), "confirmed_trigger_datetime": trigger.isoformat(),
                "timezone": self.timezone_name, "recurrence": recurrence, "status": "pending",
                "persistent_record": True, "scheduler_registered": True}

    def list_reminders(self, *, include_completed: bool = False) -> Dict[str, Any]:
        query = "SELECT * FROM reminders" if include_completed else "SELECT * FROM reminders WHERE enabled=1 AND status='pending'"
        with closing(self._connect()) as connection:
            rows = [dict(row) for row in connection.execute(query + " ORDER BY trigger_datetime")]
        return {"ok": True, "reminders": rows, "count": len(rows), "message": f"{len(rows)} reminder(s)."}

    def _update(self, reminder_id: str, sql: str, values: tuple[Any, ...], event: str) -> Dict[str, Any]:
        with closing(self._connect()) as connection:
            cursor = connection.execute(sql, (*values, reminder_id))
            connection.commit()
        if cursor.rowcount != 1:
            return {"ok": False, "error": "not_found", "message": "Reminder not found."}
        self.activity(event, f"Reminder {reminder_id}: {event.replace('_', ' ')}.")
        self._wake_scheduler()
        return {"ok": True, "reminder_id": reminder_id, "status": event.replace("reminder_", "")}

    def cancel(self, reminder_id: str) -> Dict[str, Any]:
        return self._update(reminder_id, "UPDATE reminders SET enabled=0, status='cancelled' WHERE reminder_id=?", (), "reminder_cancelled")

    def dismiss(self, reminder_id: str) -> Dict[str, Any]:
        return self._update(reminder_id, "UPDATE reminders SET enabled=0, status='dismissed', dismissed_at=? WHERE reminder_id=?",
                            (self._now().isoformat(),), "reminder_dismissed")

    def snooze(self, reminder_id: str, minutes: int = 10) -> Dict[str, Any]:
        trigger = self._now().astimezone(timezone.utc) + timedelta(minutes=max(1, min(1440, int(minutes))))
        return self._update(reminder_id,
                            "UPDATE reminders SET enabled=1, status='pending', trigger_datetime=?, snooze_count=snooze_count+1 WHERE reminder_id=?",
                            (trigger.isoformat(),), "reminder_snoozed")

    def status(self, reminder_id: str) -> Dict[str, Any]:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM reminders WHERE reminder_id=?", (reminder_id,)).fetchone()
        return {"ok": bool(row), "reminder": dict(row) if row else {}, "error": "" if row else "not_found"}

    def execute(self, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        if action == "create_reminder":
            return self.create(parameters)
        if action == "create_alarm":
            return self.create(parameters, alarm=True)
        if action == "list_reminders":
            return self.list_reminders(include_completed=bool(parameters.get("include_completed")))
        reminder_id = str(parameters.get("reminder_id") or "")
        if action == "cancel_reminder":
            return self.cancel(reminder_id)
        if action == "snooze_reminder":
            return self.snooze(reminder_id, int(parameters.get("minutes") or 10))
        if action == "dismiss_reminder":
            return self.dismiss(reminder_id)
        if action == "get_reminder_status":
            return self.status(reminder_id)
        return {"ok": False, "error": "unknown_action", "message": f"Unknown reminder action: {action}"}

    def _next_due(self) -> Optional[Dict[str, Any]]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM reminders WHERE enabled=1 AND status='pending' ORDER BY trigger_datetime LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def process_due(self) -> int:
        now_iso = self._now().astimezone(timezone.utc).isoformat()
        fired: List[Dict[str, Any]] = []
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT * FROM reminders WHERE enabled=1 AND status='pending' AND trigger_datetime<=? ORDER BY trigger_datetime",
                (now_iso,),
            ).fetchall()
            for row in rows:
                record = dict(row)
                recurrence = record.get("recurrence") or ""
                if recurrence:
                    old = datetime.fromisoformat(record["trigger_datetime"])
                    next_trigger = old + (timedelta(days=1) if recurrence == "daily" else timedelta(days=7))
                    connection.execute(
                        "UPDATE reminders SET trigger_datetime=?, fired_at=?, status='pending' WHERE reminder_id=?",
                        (next_trigger.isoformat(), now_iso, record["reminder_id"]),
                    )
                else:
                    connection.execute(
                        "UPDATE reminders SET enabled=0, status='fired', fired_at=? WHERE reminder_id=? AND status='pending'",
                        (now_iso, record["reminder_id"]),
                    )
                fired.append(record)
            connection.commit()
        for record in fired:
            self.activity("reminder_fired", f"Reminder {record['reminder_id']} fired.")
            try:
                self.announce(str(record["message"]), record)
                self.activity("tts_completed", f"Reminder {record['reminder_id']} announcement queued.")
            except Exception as exc:
                self.activity("tts_failed", f"Reminder {record['reminder_id']} TTS failed: {exc}")
        return len(fired)

    def _scheduler_loop(self) -> None:
        while True:
            self.process_due()
            next_item = self._next_due()
            wait_seconds = 60.0
            if next_item:
                due = datetime.fromisoformat(next_item["trigger_datetime"])
                wait_seconds = max(.05, min(60.0, (due - self._now().astimezone(timezone.utc)).total_seconds()))
            with self._condition:
                if self._stop:
                    return
                self._condition.wait(timeout=wait_seconds)
