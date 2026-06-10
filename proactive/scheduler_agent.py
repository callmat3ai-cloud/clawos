"""
SchedulerAgent — parses natural language into cron jobs and scheduled tasks.
Handles: /cron, /monitor, and proactive suggestions.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger("scheduler_agent")

# ── helpers ──────────────────────────────────────────────────────────

def _base_dir() -> Path:
    import sys
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent


BASE_DIR = _base_dir()
TASKS_FILE = BASE_DIR / "config" / "scheduled_tasks.json"


@dataclass
class ScheduledTask:
    id: str
    description: str
    schedule: str  # natural language: "every 5 minutes", "daily at 9am", "every Monday"
    cron_expr: str | None = None  # parsed crontab, None = use interval
    interval_seconds: int = 0  # for interval-based tasks
    task_type: str = "reminder"  # reminder | monitor | command
    payload: dict = field(default_factory=dict)  # task-specific data
    created_at: str = ""
    last_run: str = ""
    next_run: str = ""
    enabled: bool = True
    active: bool = True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "schedule": self.schedule,
            "cron_expr": self.cron_expr,
            "interval_seconds": self.interval_seconds,
            "task_type": self.task_type,
            "payload": self.payload,
            "created_at": self.created_at,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "enabled": self.enabled,
            "active": self.active,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ScheduledTask":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ── Natural Language Parser ─────────────────────────────────────────

class SchedulerAgent:
    """
    Parse natural language scheduling requests into ScheduledTask objects.
    Examples:
      - "every 5 minutes" → interval=300
      - "daily at 9am" → cron="0 9 * * *"
      - "every Monday at 9am" → cron="0 9 * * 1"
      - "check google.com every 10 minutes" → task_type=monitor
    """

    # Keywords → interval multipliers
    INTERVAL_KEYWORDS = {
        r"every\s+(\d+)\s*second": 1,
        r"every\s+(\d+)\s*minute": 60,
        r"every\s+(\d+)\s*hour": 3600,
        r"every\s+(\d+)\s*day": 86400,
        r"every\s+second": 1,
        r"every\s+minute": 60,
        r"every\s+hour": 3600,
        r"every\s+day": 86400,
        r"every\s+(\d+)\s*min": 60,
        r"every\s+(\d+)\s*hr": 3600,
    }

    # Day-of-week keywords
    DOW_MAP = {"monday": 1, "tuesday": 2, "wednesday": 3, "thursday": 4,
               "friday": 5, "saturday": 6, "sunday": 0}
    DOW_ALIASES = {**DOW_MAP, "mon": 1, "tue": 2, "wed": 3, "thu": 4,
                   "fri": 5, "sat": 6, "sun": 0}

    def __init__(self):
        self._tasks: dict[str, ScheduledTask] = {}
        self._task_counter = 0
        self._load_tasks()

    # ── Public API ──────────────────────────────────────────────────

    def create_task(self, text: str, task_type: str = "reminder",
                    payload: dict | None = None) -> ScheduledTask | None:
        """
        Parse natural language and create a scheduled task.
        Returns ScheduledTask or None if parsing failed.
        """
        text_lower = text.lower().strip()
        task_id = self._next_id()
        now = datetime.now().isoformat()

        # Interval-based: "every 5 minutes", "every hour"
        interval = self._parse_interval(text_lower)
        if interval:
            next_run = datetime.now() + timedelta(seconds=interval)
            task = ScheduledTask(
                id=task_id,
                description=text,
                schedule=text,
                interval_seconds=interval,
                task_type=task_type,
                payload=payload or {},
                created_at=now,
                next_run=next_run.isoformat(),
            )
            self._save_task(task)
            log.info(f"Created interval task [{task_id}]: {text} (every {interval}s)")
            return task

        # Cron-based: "daily at 9am", "every Monday at 9am"
        cron_expr = self._parse_cron(text_lower)
        if cron_expr:
            next_run = self._cron_next_run(cron_expr)
            task = ScheduledTask(
                id=task_id,
                description=text,
                schedule=text,
                cron_expr=cron_expr,
                task_type=task_type,
                payload=payload or {},
                created_at=now,
                next_run=next_run.isoformat() if next_run else "",
            )
            self._save_task(task)
            log.info(f"Created cron task [{task_id}]: {text} ({cron_expr})")
            return task

        # One-time: "in 5 minutes", "at 9pm today"
        delay = self._parse_one_time(text_lower)
        if delay:
            next_run = datetime.now() + delay
            task = ScheduledTask(
                id=task_id,
                description=text,
                schedule=text,
                interval_seconds=int(delay.total_seconds()),
                task_type=task_type,
                payload=payload or {},
                created_at=now,
                next_run=next_run.isoformat(),
            )
            self._save_task(task)
            log.info(f"Created one-time task [{task_id}]: {text}")
            return task

        return None

    def list_tasks(self) -> list[ScheduledTask]:
        """Return all tasks."""
        return list(self._tasks.values())

    def get_task(self, task_id: str) -> ScheduledTask | None:
        return self._tasks.get(task_id)

    def cancel_task(self, task_id: str) -> bool:
        """Cancel and delete a task."""
        if task_id in self._tasks:
            task = self._tasks.pop(task_id)
            self._persist()
            log.info(f"Cancelled task [{task_id}]: {task.description}")
            return True
        return False

    def tick(self) -> list[ScheduledTask]:
        """
        Called periodically (e.g. every 10s). Returns tasks that are due to fire.
        Marks them as inactive for one-time tasks.
        """
        now = datetime.now()
        due = []
        for task in list(self._tasks.values()):
            if not task.enabled or not task.active:
                continue
            if not task.next_run:
                continue
            try:
                next_dt = datetime.fromisoformat(task.next_run)
                if now >= next_dt:
                    due.append(task)
                    # Update next_run for recurring
                    if task.interval_seconds:
                        next_dt = now + timedelta(seconds=task.interval_seconds)
                        task.next_run = next_dt.isoformat()
                    else:
                        # Compute next cron
                        if task.cron_expr:
                            nr = self._cron_next_run(task.cron_expr, after=now)
                            task.next_run = nr.isoformat() if nr else ""
                    task.last_run = now.isoformat()
                    # One-time tasks: disable after first run
                    if "once" in task.schedule.lower() or "in " in task.schedule.lower():
                        task.active = False
                    self._persist()
            except Exception:
                pass
        return due

    # ── Parser helpers ──────────────────────────────────────────────

    def _parse_interval(self, text: str) -> int | None:
        """Parse interval expressions like 'every 5 minutes'."""
        for pattern, multiplier in self.INTERVAL_KEYWORDS.items():
            m = re.search(pattern, text)
            if m:
                if m.groups():
                    count = int(m.group(1))
                    return count * multiplier
                return multiplier
        return None

    def _parse_cron(self, text: str) -> str | None:
        """Parse expressions like 'daily at 9am', 'every monday at 9am'."""
        # "at HH:MM" or "at H am/pm"
        time_m = re.search(r"at\s+(\d{1,2}):?(\d{2})?\s*(am|pm)?", text)
        hour, minute, ampm = None, 0, None
        if time_m:
            hour = int(time_m.group(1))
            if time_m.group(2):
                minute = int(time_m.group(2))
            ampm = time_m.group(3)

        if ampm == "pm" and hour != 12 and hour is not None:
            hour += 12
        elif ampm == "am" and hour == 12 and hour is not None:
            hour = 0

        # Detect day of week
        dow = None
        for day_name, dow_num in self.DOW_ALIASES.items():
            if day_name in text:
                dow = dow_num
                break

        if time_m and hour is not None:
            # daily at HH:MM
            if dow is not None:
                return f"{minute} {hour} * * {dow}"  # weekly
            elif "daily" in text or "every day" in text:
                return f"{minute} {hour} * * *"
            elif "weekday" in text:
                return f"{minute} {hour} * * 1-5"
            else:
                # Just "at 9am" → daily
                return f"{minute} {hour} * * *"
        return None

    def _parse_one_time(self, text: str) -> timedelta | None:
        """Parse one-time delays like 'in 5 minutes', 'in 2 hours'."""
        m = re.search(r"in\s+(\d+)\s*(second|minute|hour|min|hr)s?", text)
        if m:
            count = int(m.group(1))
            unit = m.group(2)
            multipliers = {"second": 1, "minute": 60, "min": 60,
                          "hour": 3600, "hr": 3600}
            return timedelta(seconds=count * multipliers.get(unit, 60))
        return None

    def _cron_next_run(self, expr: str, after: datetime | None = None) -> datetime | None:
        """Simple cron parser for common patterns (min hour dom mon dow)."""
        try:
            parts = expr.split()
            if len(parts) != 5:
                return None
            minute, hour, dom, month, dow = parts
            now = after or datetime.now()
            # Build next candidate: same day first, then next day
            for offset in range(366):
                candidate = now + timedelta(days=offset)
                # Check dow
                if dow != "*":
                    dow_vals = [int(d) for d in dow.split(",") if d.isdigit()]
                    if candidate.weekday() not in dow_vals:
                        continue
                # Check hour
                h = int(hour) if hour.isdigit() else None
                if h is None:
                    continue
                m = int(minute) if minute.isdigit() else 0
                if offset == 0:
                    # Same day — only future times
                    if h < now.hour:
                        continue
                    if h == now.hour and m <= now.minute:
                        continue
                return candidate.replace(hour=h, minute=m, second=0, microsecond=0)
        except Exception:
            pass
        return None

    # ── Storage ────────────────────────────────────────────────────

    def _next_id(self) -> str:
        self._task_counter += 1
        return f"task_{self._task_counter:04d}"

    def _save_task(self, task: ScheduledTask):
        self._tasks[task.id] = task
        self._persist()

    def _load_tasks(self):
        TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not TASKS_FILE.exists():
            return
        try:
            data = json.loads(TASKS_FILE.read_text())
            for d in data.get("tasks", []):
                t = ScheduledTask.from_dict(d)
                self._tasks[t.id] = t
                # Track counter
                if t.id.startswith("task_"):
                    try:
                        n = int(t.id.split("_")[1])
                        if n >= self._task_counter:
                            self._task_counter = n + 1
                    except Exception:
                        pass
        except Exception as e:
            log.warning(f"Failed to load tasks: {e}")

    def _persist(self):
        TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        TASKS_FILE.write_text(json.dumps({
            "tasks": [t.to_dict() for t in self._tasks.values()]
        }, indent=2))
