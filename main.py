"""
ClawOS v2.0.1 — Desktop AI Agent
Full agentic OS with streaming, safety, voice, memory, subagents, messaging, MCP.
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

        # ── Create QApplication FIRST (before any Qt widgets) ──────────
        self._qapp = QApplication.instance()
        if self._qapp is None:
            self._qapp = QApplication(sys.argv)
            self._qapp.setApplicationName("ClawOS")
            self._qapp.setStyle("Fusion")

        # ── Load all subsystems ────────────────────────────────
        self._voice_engine = None
        self._memory_engine = None
        self._subagent_orchestrator = None
        self._messaging_hub = None
        self._mcp_manager = None

        # Import UI (safe now — QApplication exists)
        from clawos_ui import ClawOSWindow

        self.window = ClawOSWindow()
        self.window._app = self
        self.window._profile_manager = None

        # Wire up signals
        self.window.streaming_token.connect(self._on_token)
        self.window.response_complete.connect(self._on_complete)
        # Approval is handled asynchronously via _approval_resolver in clawos_ui.py

        # Connect Enter key → main.py handler (slash/yolo-aware, single entry point)
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

        # ── Initialize subsystems ──────────────────────────────
        self._init_voice()
        self._init_memory()
        self._init_subagents()
        self._init_messaging()
        self._init_mcp()
        self._init_proactive()

    def _init_voice(self):
        """Phase 3: Initialize voice engine."""
        try:
            from agent.voice_engine import get_voice_engine, VoiceEngine
            self._voice_engine = get_voice_engine()
            self.window._voice_engine = self._voice_engine
            log.info("✅ Voice engine ready")
        except Exception as e:
            log.warning(f"Voice engine init failed: {e}")

    def _init_memory(self):
        """Phase 4: Initialize memory compression engine."""
        try:
            from memory.memory_engine import get_memory_engine
            self._memory_engine = get_memory_engine()
            self.window._memory_engine = self._memory_engine
            log.info("✅ Memory engine ready")
        except Exception as e:
            log.warning(f"Memory engine init failed: {e}")

    def _init_subagents(self):
        """Phase 5: Initialize subagent orchestrator."""
        try:
            from agent.subagent_orchestrator import get_orchestrator
            self._subagent_orchestrator = get_orchestrator()
            self.window._subagent_orchestrator = self._subagent_orchestrator

            def on_subagent_status(agent_id, status):
                self.window._log_activity(f"Subagent {agent_id[:12]}: {status}")
            self._subagent_orchestrator.set_progress_callback(on_subagent_status)

            log.info("✅ Subagent orchestrator ready")
        except Exception as e:
            log.warning(f"Subagent init failed: {e}")

    def _init_messaging(self):
        """Phase 7: Start incoming message polling."""
        try:
            from messaging.messaging_hub import get_messaging_hub
            self._messaging_hub = get_messaging_hub()

            def on_incoming(msg):
                if hasattr(self.window, "_add_message"):
                    sender = msg.sender_name or msg.sender
                    self.window._add_message(
                        "assistant",
                        f"📩 [{msg.platform.upper()}] {sender}: {msg.body[:80]}",
                    )
                self.window._log_activity(f"Incoming {msg.platform}: {msg.body[:40]}")

            self._messaging_hub.on_message = on_incoming
            self._messaging_hub.start()
            self.window._messaging_hub = self._messaging_hub
            log.info("✅ Messaging hub started")
        except Exception as e:
            log.warning(f"Messaging hub init failed: {e}")

    def _init_mcp(self):
        """Phase 8: Connect all MCP servers."""
        try:
            from mcp.mcp_manager import get_mcp_manager
            self._mcp_manager = get_mcp_manager()
            self._mcp_manager.connect_all()
            self.window._mcp_manager = self._mcp_manager

            mcp_tools = self._mcp_manager.get_tools_for_prompt()
            if mcp_tools:
                log.info(f"✅ MCP: {len(mcp_tools.split(chr(10)))-1} tools loaded")

            log.info("✅ MCP manager ready")
        except Exception as e:
            log.warning(f"MCP init failed: {e}")

    def _init_proactive(self):
        """Proactive agent: scheduler + monitors + background loop."""
        try:
            from proactive.background_loop import ProactiveBackgroundLoop
            self._proactive = ProactiveBackgroundLoop(
                on_alert=self._on_proactive_alert,
                on_task_fire=self._on_task_fire,
            )
            self._proactive.start()
            self.window._proactive = self._proactive
            log.info("✅ Proactive agent ready")
        except Exception as e:
            log.warning(f"Proactive init failed: {e}")

    def _on_proactive_alert(self, alert):
        """Surface proactive alerts to the UI."""
        if hasattr(self.window, "_add_message"):
            self.window._add_message(
                "assistant",
                f"{alert.title}\n{alert.body}",
            )
        if hasattr(self.window, "_log_activity"):
            self.window._log_activity(f"Alert: {alert.title}")

    def _on_task_fire(self, task: dict):
        """Handle fired scheduled tasks."""
        if hasattr(self.window, "_add_message"):
            self.window._add_message(
                "assistant",
                f"⏰ *Task fired:* {task.get('description', 'Scheduled task')}",
            )

    def _on_state_change(self, state: str):
        """Sync proactive triggers with UI state."""
        orb_active = (state == "listening")
        streaming_active = (state == "processing")
        if hasattr(self, "_proactive") and self._proactive:
            self._proactive.set_orb_active(orb_active)
            self._proactive.set_streaming_active(streaming_active)

    def start(self):
        self._qapp.setQuitOnLastWindowClosed(False)
        self.window.show()
        self._print_banner()
        sys.exit(self._qapp.exec())

    def _print_banner(self):
        print()
        print("  🟣 CLAWOS v2.0.1")
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
        """Single message entry point — handles slash commands and yolo mode."""
        if not text.strip():
            return
        # Detect /yolo and update badge
        from agent.streaming_executor import parse_slash_command
        is_yolo, clean = parse_slash_command(text)
        if is_yolo:
            self.window._set_yolo_mode(True)
        # Handle slash commands (don't pass to LLM)
        if text.strip().startswith("/") and self._handle_slash_command(text):
            return
        self.window._center_input.clear()
        self.window._add_message("user", text)
        self._process_message(text)

    def _handle_slash_command(self, text: str):
        """Run a slash command, surface result as assistant message."""
        from agent.slash_commands import execute_slash_command
        response, handled = execute_slash_command(
            text,
            window=self.window,
            main_app=self,
            executor=None,
        )
        if handled and response:
            self.window._add_message("assistant", response)
        return handled

    def _process_message(self, text: str):
        if self._processing:
            self.window._add_message("assistant", "⏳ Still working on your previous request...")
            return

        self._processing = True
        self.window._set_orb_state("processing")
        self.window._log_activity(f"Sent: {text[:60]}")
        # Trigger proactive background loop
        if hasattr(self, "_proactive") and self._proactive:
            self._proactive.set_streaming_active(True)

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

                # Use window's streaming toggle state
                streaming = self.window._streaming_enabled

                def on_token(token: str):
                    self.window.streaming_token.emit(token)

                def on_show_approval(action: str):
                    self.window.approval_request.emit(action)

                # Wire callbacks
                executor.set_approval_callbacks(
                    on_show=on_show_approval,
                    on_done=lambda approved: setattr(executor, '_approval_result', approved),
                )

                def on_complete(text: str = ""):
                    self.window.response_complete.emit(text)

                result = executor.execute(
                    goal=text,
                    on_token=on_token,
                    on_complete=on_complete,
                    memory_context=memory_ctx,
                    composio_context=composio_ctx,
                )

            except Exception as e:
                log.error(f"Executor error: {traceback.format_exc()}")
                error_msg = f"⚠️ Error: {str(e)[:200]}"
                self.window.streaming_token.emit(error_msg)
                self.window.response_complete.emit(error_msg)

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
        self.window._log_activity("Response ready")
        # Stop proactive streaming trigger
        if hasattr(self, "_proactive") and self._proactive:
            self._proactive.set_streaming_active(False)
        # Cleanup streaming bubble
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


def main():
    app = ClawOSApp()
    app.start()


if __name__ == "__main__":
    main()
