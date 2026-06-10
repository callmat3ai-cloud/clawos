"""
ClawOS v2 — Desktop AI Agent
Full agentic OS with streaming, safety, messaging integrations.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("clawos")


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _load_keys() -> dict:
    path = CONFIG_DIR / "api_keys.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_approval() -> dict:
    path = CONFIG_DIR / "approval_config.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


class ClawOSApp:
    """
    Main ClawOS application controller.
    Wires: UI → Executor → Memory → Profiles → Scheduler → Composio
    """

    def __init__(self):
        self._current_session_id: str | None = None
        self._processing = False
        self._approval_callback_result: bool = True
        self._pending_executor = None

        # Import UI
        from clawos_ui import ClawOSWindow

        self.window = ClawOSWindow()
        self.window._profile_manager = None

        # Wire up signals
        self.window.streaming_token.connect(self._on_token)
        self.window.response_complete.connect(self._on_complete)
        self.window.approval_request.connect(self._on_approval_request)

        # Connect click handlers in left panel
        self.window._center_input.returnPressed.connect(
            lambda: self._handle_send(self.window._center_input.text())
        )

        # Restore cron jobs
        try:
            from scheduler.cron_manager import get_cron_manager
            self.window._cron_manager = get_cron_manager()
            get_cron_manager().restore_all()
        except Exception as e:
            log.warning(f"Cron restore error: {e}")

    def start(self):
        app = QApplication(sys.argv)
        app.setApplicationName("ClawOS")
        app.setStyle("Fusion")
        app.setQuitOnLastWindowClosed(False)

        self.window.show()
        self._print_banner()
        sys.exit(app.exec())

    def _print_banner(self):
        print()
        print("  🟣 CLAWOS v2.0.0")
        print("  Desktop AI Agent — Agentic OS")
        print(f"  Composio: {'✅ Connected' if self._composio_configured() else '⚠️ Add API key in Settings'}")
        print(f"  WhatsApp: {'✅ Configured' if self._whatsapp_configured() else '⚠️ Add credentials in Settings'}")
        print()

    def _composio_configured(self) -> bool:
        keys = _load_keys()
        return bool(keys.get("composio_api_key"))

    def _whatsapp_configured(self) -> bool:
        keys = _load_keys()
        return bool(keys.get("evolution_api_key") and keys.get("evolution_instance"))

    def _handle_send(self, text: str):
        if not text.strip():
            return
        self.window._center_input.clear()
        self.window._add_message("user", text)
        self._process_message(text)

    def _process_message(self, text: str):
        if self._processing:
            self.window._add_message("assistant", "⏳ Still working on your previous request...")
            return

        self._processing = True
        self.window._set_orb_state("processing")
        self.window._log_activity(f"Sent: {text[:60]}")

        # Load context
        try:
            from memory.profile_manager import format_memory_for_prompt
            memory_ctx = format_memory_for_prompt(limit=20)
        except Exception:
            memory_ctx = ""

        try:
            from integrations.composio_mcp import get_composio, is_configured as composio_configured
            composio_ctx = ""
            if composio_configured():
                composio_ctx = get_composio().get_tools_for_prompt()
        except Exception:
            composio_ctx = ""

        # Build assistant bubble for streaming
        from clawos_ui import ChatBubble
        ts = datetime.now().strftime("%H:%M")
        bubble = ChatBubble("assistant", "", ts)
        self.window._chat_layout.insertWidget(
            self.window._chat_layout.count() - 1, bubble
        )
        self.window._current_bubble = bubble

        def run():
            try:
                from agent.streaming_executor import StreamingExecutor

                approval = _load_approval()
                executor = StreamingExecutor(approval)

                # Store reference for approval dialogs
                self._pending_executor = executor

                # Use window's streaming toggle state
                streaming = self.window._streaming_enabled

                def on_token(token: str):
                    self.window.streaming_token.emit(token)

                def on_complete(text: str):
                    self.window.response_complete.emit()

                def on_approval(action: str):
                    self.window.approval_request.emit(action)

                result = executor.execute(
                    goal=text,
                    on_token=on_token,
                    on_complete=on_complete,
                    on_approval=on_approval,
                    memory_context=memory_ctx,
                    composio_context=composio_ctx,
                )

                # If streaming was off, show full response
                if not self.window._streaming_enabled:
                    if result.text:
                        self.window.streaming_token.emit(result.text)
                    self.window.response_complete.emit()

            except Exception as e:
                log.error(f"Executor error: {traceback.format_exc()}")
                error_msg = f"⚠️ Error: {str(e)[:200]}"
                self.window.streaming_token.emit(error_msg)
                self.window.response_complete.emit()

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    def _on_token(self, token: str):
        if hasattr(self.window, "_current_bubble") and self.window._current_bubble:
            self.window._current_bubble.append(token)
            QTimer.singleShot(10, lambda: self.window._chat_scroll.verticalScrollBar().setValue(
                self.window._chat_scroll.verticalScrollBar().maximum()
            ))

    def _on_complete(self, text: str = ""):
        self._processing = False
        self.window._set_orb_state("idle")
        if hasattr(self.window, "_current_bubble") and self.window._current_bubble:
            b = self.window._current_bubble
            if hasattr(b, "_streaming_done"):
                b._streaming_done = True
            if hasattr(b, "_stream_timer"):
                b._stream_timer.stop()
            self.window._current_bubble = None
        self.window._log_activity("Response complete")

        # Save to memory
        try:
            from memory.profile_manager import save_memory
            save_memory(
                category="conversation",
                key=f"interaction_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                value=f"ClawOS: {text[:200]}",
                confidence=0.8,
                source="auto",
            )
        except Exception:
            pass

    def _on_approval_request(self, action: str):
        from clawos_ui import ApprovalDialog
        dialog = ApprovalDialog(action, self.window)
        self._approval_callback_result = dialog.get_result()
        if self._pending_executor:
            self._pending_executor._approval_callback_result = self._approval_callback_result


def main():
    app = ClawOSApp()
    app.start()


if __name__ == "__main__":
    main()
