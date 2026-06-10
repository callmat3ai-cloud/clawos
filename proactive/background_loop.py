"""
ProactiveBackgroundLoop — orchestrates the proactive agent.
Runs when: (a) voice orb is active, (b) streaming is running.
Drives: scheduler_agent, app_monitor, and surfaces alerts via UI.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger("proactive_bg")

BASE_DIR = Path(__file__).resolve().parent.parent.parent


@dataclass
class Alert:
    id: str
    source: str  # "scheduler" | "monitor"
    title: str
    body: str
    severity: str = "info"  # info | warning | critical
    timestamp: str = ""
    task_id: str = ""
    dismissed: bool = False


class ProactiveBackgroundLoop:
    """
    Coordinates proactive intelligence:
    - SchedulerAgent: cron/scheduled tasks
    - AppMonitor: URL/file/process watchers
    - Alert queue: surfaces to UI

    Triggers when:
    - Voice orb is active (orb_active = True)
    - Streaming is running (streaming_active = True)
    - Or when manual mode enabled (always_active = True)
    """

    def __init__(
        self,
        on_alert: Callable[[Alert], None] | None = None,
        on_task_fire: Callable[[dict], None] | None = None,
    ):
        self._on_alert = on_alert
        self._on_task_fire = on_task_fire

        # Trigger flags
        self.orb_active = False
        self.streaming_active = False
        self.always_active = False  # for /yolo mode

        # Sub-systems
        from proactive.scheduler_agent import SchedulerAgent
        from proactive.app_monitor import AppMonitor
        self._scheduler = SchedulerAgent()

        def _on_monitor_alert(result):
            alert = Alert(
                id=f"mon_{result.monitor_id}_{int(time.time())}",
                source="monitor",
                title=f"🔴 Monitor: {result.status.upper()}",
                body=result.message,
                severity="warning" if result.status == "error" else "info",
                timestamp=result.timestamp,
                task_id=result.monitor_id,
            )
            self._add_alert(alert)

        self._monitor = AppMonitor(on_alert=_on_monitor_alert)

        # State
        self._running = False
        self._thread: threading.Thread | None = None
        self._alerts: list[Alert] = []
        self._alert_counter = 0
        self._tick_interval = 10  # seconds

        # Config
        self._alerts_file = BASE_DIR / "config" / "proactive_alerts.json"
        self._load_alerts()

    # ── Control ────────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="ProactiveLoop")
        self._thread.start()
        log.info("ProactiveBackgroundLoop started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        log.info("ProactiveBackgroundLoop stopped")

    def is_active(self) -> bool:
        return self.orb_active or self.streaming_active or self.always_active

    def set_orb_active(self, active: bool):
        self.orb_active = active

    def set_streaming_active(self, active: bool):
        self.streaming_active = active

    def set_always_active(self, active: bool):
        self.always_active = active

    # ── Task Management ─────────────────────────────────────────────

    def schedule_task(self, text: str, task_type: str = "reminder",
                      payload: dict | None = None) -> str | None:
        """
        Create a scheduled task from natural language.
        Returns task_id or None.
        """
        task = self._scheduler.create_task(text, task_type, payload)
        return task.id if task else None

    def cancel_task(self, task_id: str) -> bool:
        return self._scheduler.cancel_task(task_id)

    def list_tasks(self) -> list[dict]:
        return [t.to_dict() for t in self._scheduler.list_tasks()]

    def get_task(self, task_id: str) -> dict | None:
        t = self._scheduler.get_task(task_id)
        return t.to_dict() if t else None

    # ── Monitor Management ─────────────────────────────────────────

    def add_url_monitor(self, url: str, interval: int = 300) -> str:
        """Add a URL monitor. Returns monitor_id."""
        import uuid
        mid = f"url_{uuid.uuid4().hex[:8]}"
        self._monitor.add_url_monitor(mid, url, check_interval=interval)
        return mid

    def remove_monitor(self, monitor_id: str) -> bool:
        return self._monitor.remove_monitor(monitor_id)

    def list_monitors(self) -> list[dict]:
        return self._monitor.list_monitors()

    def check_monitor_now(self, monitor_id: str) -> str:
        result = self._monitor.check_now(monitor_id)
        return result.message if result else "Monitor not found"

    # ── Alerts ─────────────────────────────────────────────────────

    def get_alerts(self) -> list[dict]:
        return [a.__dict__ for a in self._alerts if not a.dismissed]

    def dismiss_alert(self, alert_id: str):
        for a in self._alerts:
            if a.id == alert_id:
                a.dismissed = True
                self._persist_alerts()
                return

    def clear_alerts(self):
        self._alerts = []
        self._persist_alerts()

    def _add_alert(self, alert: Alert):
        self._alerts.insert(0, alert)
        # Keep last 50 alerts
        self._alerts = self._alerts[:50]
        self._persist_alerts()
        if self._on_alert:
            self._on_alert(alert)

    # ── Main Loop ──────────────────────────────────────────────────

    def _run_loop(self):
        while self._running:
            try:
                if self.is_active():
                    self._tick()
                # Sleep shorter when active for faster response
                time.sleep(1 if self.is_active() else self._tick_interval)
            except Exception as e:
                log.error(f"Proactive loop error: {e}")
                time.sleep(5)

    def _tick(self):
        # Run scheduled tasks
        due = self._scheduler.tick()
        for task in due:
            self._fire_task(task)

        # Run monitors
        alerts = self._monitor.tick()
        for result in alerts:
            log.info(f"Monitor alert: {result.message}")

    def _fire_task(self, task):
        import datetime
        log.info(f"Firing task: {task.description}")

        # Surface as alert
        alert = Alert(
            id=f"task_{task.id}_{int(time.time())}",
            source="scheduler",
            title=f"⏰ {task.description}",
            body=f"Scheduled task fired: {task.description}",
            severity="info",
            timestamp=datetime.datetime.now().isoformat(),
            task_id=task.id,
        )
        self._add_alert(alert)

        # Notify handler
        if self._on_task_fire:
            try:
                self._on_task_fire(task.to_dict())
            except Exception as e:
                log.error(f"Task fire handler error: {e}")

    # ── Status ─────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """Return proactive agent status for /status command."""
        return {
            "active": self.is_active(),
            "triggers": {
                "orb_active": self.orb_active,
                "streaming_active": self.streaming_active,
                "always_active": self.always_active,
            },
            "tasks": {
                "total": len(self._scheduler.list_tasks()),
                "active": len([t for t in self._scheduler.list_tasks() if t.active]),
            },
            "monitors": {
                "total": len(self._monitor.list_monitors()),
            },
            "alerts": {
                "unread": len([a for a in self._alerts if not a.dismissed]),
            },
        }

    # ── Persistence ────────────────────────────────────────────────

    def _load_alerts(self):
        if not self._alerts_file.exists():
            return
        try:
            data = json.loads(self._alerts_file.read_text())
            self._alerts = [Alert(**a) for a in data.get("alerts", [])]
        except Exception as e:
            log.warning(f"Failed to load alerts: {e}")

    def _persist_alerts(self):
        self._alerts_file.parent.mkdir(parents=True, exist_ok=True)
        self._alerts_file.write_text(json.dumps({
            "alerts": [a.__dict__ for a in self._alerts]
        }, indent=2))


import datetime
