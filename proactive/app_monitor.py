"""
AppMonitor — monitors URLs, files, and processes for changes.
Triggers alerts when conditions are met.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger("app_monitor")


def _base_dir() -> Path:
    import sys
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent


BASE_DIR = _base_dir()
MONITORS_FILE = BASE_DIR / "config" / "monitors.json"


@dataclass
class MonitorResult:
    monitor_id: str
    monitor_type: str  # url | file | process
    target: str
    status: str  # ok | error | changed
    message: str
    timestamp: str


class AppMonitor:
    """
    Monitors system and web resources.
    Types:
    - URL: checks HTTP status / content changes
    - File: watches for modification
    - Process: checks if a process is running
    """

    def __init__(self, on_alert: Callable[[MonitorResult], None] | None = None):
        self._monitors: dict[str, dict] = {}
        self._last_results: dict[str, dict] = {}
        self._on_alert = on_alert
        self._load()

    # ── Public API ──────────────────────────────────────────────────

    def add_url_monitor(self, monitor_id: str, url: str,
                         check_interval: int = 300,
                         expected_status: int = 200,
                         alert_on_down: bool = True):
        """Add a URL monitoring task."""
        self._monitors[monitor_id] = {
            "id": monitor_id,
            "type": "url",
            "target": url,
            "interval": check_interval,
            "expected_status": expected_status,
            "alert_on_down": alert_on_down,
            "last_check": 0,
            "enabled": True,
        }
        self._persist()

    def add_file_monitor(self, monitor_id: str, file_path: str,
                          alert_on_change: bool = True):
        """Add a file watch task."""
        self._monitors[monitor_id] = {
            "id": monitor_id,
            "type": "file",
            "target": file_path,
            "alert_on_change": alert_on_change,
            "last_mtime": 0,
            "last_check": 0,
            "enabled": True,
        }
        self._persist()

    def add_process_monitor(self, monitor_id: str, process_name: str,
                             alert_on_down: bool = True):
        """Add a process monitor."""
        self._monitors[monitor_id] = {
            "id": monitor_id,
            "type": "process",
            "target": process_name,
            "alert_on_down": alert_on_down,
            "last_check": 0,
            "enabled": True,
        }
        self._persist()

    def remove_monitor(self, monitor_id: str) -> bool:
        """Remove a monitor."""
        if monitor_id in self._monitors:
            del self._monitors[monitor_id]
            self._persist()
            return True
        return False

    def list_monitors(self) -> list[dict]:
        return list(self._monitors.values())

    def tick(self) -> list[MonitorResult]:
        """
        Run all monitors that are due. Returns alerts.
        Call this every 10-30 seconds.
        """
        now = time.time()
        alerts = []

        for mid, mon in list(self._monitors.items()):
            if not mon.get("enabled", True):
                continue

            interval = mon.get("interval", 300)
            last_check = mon.get("last_check", 0)
            if now - last_check < interval:
                continue

            mon["last_check"] = now

            try:
                result = self._run_monitor(mon)
                self._last_results[mid] = {"status": result.status, "message": result.message}
                if result.status in ("error", "changed") and mon.get("alert_on_down", True):
                    alerts.append(result)
                    if self._on_alert:
                        self._on_alert(result)
            except Exception as e:
                log.error(f"Monitor {mid} failed: {e}")

        return alerts

    def check_now(self, monitor_id: str) -> MonitorResult | None:
        """Immediately run a specific monitor."""
        mon = self._monitors.get(monitor_id)
        if not mon:
            return None
        return self._run_monitor(mon)

    # ── Monitor runners ────────────────────────────────────────────

    def _run_monitor(self, mon: dict) -> MonitorResult:
        mtype = mon["type"]
        target = mon["target"]
        mid = mon["id"]

        if mtype == "url":
            return self._check_url(mid, target, mon)
        elif mtype == "file":
            return self._check_file(mid, target, mon)
        elif mtype == "process":
            return self._check_process(mid, target, mon)
        else:
            return MonitorResult(mid, mtype, target, "error", f"Unknown type: {mtype}", "")

    def _check_url(self, mid: str, url: str, mon: dict) -> MonitorResult:
        import datetime
        try:
            import requests
            expected = mon.get("expected_status", 200)
            resp = requests.get(url, timeout=10, headers={"User-Agent": "ClawOS Monitor/1.0"})
            if resp.status_code == expected:
                return MonitorResult(mid, "url", url, "ok",
                                    f"✅ {url} — HTTP {resp.status_code}",
                                    datetime.datetime.now().isoformat())
            else:
                return MonitorResult(mid, "url", url, "error",
                                    f"⚠️ {url} — HTTP {resp.status_code} (expected {expected})",
                                    datetime.datetime.now().isoformat())
        except Exception as e:
            return MonitorResult(mid, "url", url, "error",
                                f"❌ {url} — {str(e)[:100]}",
                                datetime.datetime.now().isoformat())

    def _check_file(self, mid: str, file_path: str, mon: dict) -> MonitorResult:
        import datetime
        p = Path(file_path)
        if not p.exists():
            return MonitorResult(mid, "file", file_path, "error",
                                f"❌ File not found: {file_path}",
                                datetime.datetime.now().isoformat())

        mtime = p.stat().st_mtime
        last_mtime = mon.get("last_mtime", 0)
        if last_mtime == 0:
            # First check — store mtime
            mon["last_mtime"] = mtime
            return MonitorResult(mid, "file", file_path, "ok",
                                f"👁️ Watching {file_path}",
                                datetime.datetime.now().isoformat())
        elif mtime != last_mtime:
            mon["last_mtime"] = mtime
            return MonitorResult(mid, "file", file_path, "changed",
                                f"📝 {file_path} was modified",
                                datetime.datetime.now().isoformat())
        else:
            return MonitorResult(mid, "file", file_path, "ok",
                                f"👁️ {file_path} — unchanged",
                                datetime.datetime.now().isoformat())

    def _check_process(self, mid: str, process_name: str, mon: dict) -> MonitorResult:
        import datetime
        try:
            import subprocess
            if Platform.system() == "Windows":
                result = subprocess.run(["tasklist"], capture_output=True, text=True)
                found = process_name.lower() in result.stdout.lower()
            else:
                result = subprocess.run(["pgrep", "-x", process_name],
                                       capture_output=True, text=True)
                found = result.returncode == 0

            if found:
                return MonitorResult(mid, "process", process_name, "ok",
                                    f"✅ Process '{process_name}' is running",
                                    datetime.datetime.now().isoformat())
            else:
                return MonitorResult(mid, "process", process_name, "error",
                                    f"🔴 Process '{process_name}' is NOT running",
                                    datetime.datetime.now().isoformat())
        except Exception as e:
            return MonitorResult(mid, "process", process_name, "error",
                                f"❌ Process check failed: {e}",
                                datetime.datetime.now().isoformat())

    # ── Storage ────────────────────────────────────────────────────

    def _load(self):
        if not MONITORS_FILE.exists():
            return
        try:
            data = json.loads(MONITORS_FILE.read_text())
            self._monitors = {m["id"]: m for m in data.get("monitors", [])}
        except Exception as e:
            log.warning(f"Failed to load monitors: {e}")

    def _persist(self):
        MONITORS_FILE.parent.mkdir(parents=True, exist_ok=True)
        MONITORS_FILE.write_text(json.dumps({
            "monitors": list(self._monitors.values())
        }, indent=2))


import platform as Platform
