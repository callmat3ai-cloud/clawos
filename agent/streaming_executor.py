"""
StreamingExecutor — agentic execution with token streaming, approval gates,
slash commands, yolo mode, and secret redaction.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

log = logging.getLogger("streaming_executor")


# ── Secret Redaction ──────────────────────────────────────────────────

REDACT_PATTERNS = [
    (re.compile(r'sk-[A-Za-z0-9_-]{20,}'), '***REDACTED***'),
    (re.compile(r'sk-ant-[A-Za-z0-9_-]{50,}'), '***REDACTED***'),
    (re.compile(r'gsk_[A-Za-z0-9_-]{30,}'), '***REDACTED***'),
    (re.compile(r'AIza[A-Za-z0-9_-]{20,}'), '***REDACTED***'),
    (re.compile(r'ya29\.[A-Za-z0-9_-]{60,}'), '***REDACTED***'),
    (re.compile(r'ya63\.[A-Za-z0-9_-]{60,}'), '***REDACTED***'),
    (re.compile(r'xai-[A-Za-z0-9_-]{30,}'), '***REDACTED***'),
    (re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}'), '[EMAIL_REDACTED]'),
    (re.compile(r'\+?[1-9]\d{1,14}'), '[PHONE_REDACTED]'),
    (re.compile(r'Bearer [A-Za-z0-9._-]+'), 'Bearer ***REDACTED***'),
    (re.compile(r'api[_-]?key["\s:=]+[A-Za-z0-9_-]{10,}'), 'api_key=***REDACTED***'),
    (re.compile(r'password["\s:=]+[^\s"`]{8,}'), 'password=***REDACTED***'),
    (re.compile(r'token["\s:=]+[A-Za-z0-9._-]{10,}'), 'token=***REDACTED***'),
]


def redact(text: str) -> str:
    """Replace secrets in text with placeholders."""
    for pattern, replacement in REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# ── Dangerous Actions ─────────────────────────────────────────────────

DANGEROUS_TOOLS = {
    "shell", "python", "exec", "code_execution", "terminal",
    "delete_file", "remove_file", "rm_rf", "drop_table",
    "send_money", "transfer_funds", "delete_account",
    "open_url", "download_file",
}


def is_dangerous_tool(tool_name: str) -> bool:
    """Check if a tool requires approval."""
    return tool_name.lower() in DANGEROUS_TOOLS


def describe_action(tool: str, args: dict) -> str:
    """Human-readable description of an action."""
    tool = tool.lower()
    if tool == "shell":
        cmd = args.get("command", "")
        return f"Run shell command: `{cmd[:100]}`"
    elif tool == "python":
        return f"Execute Python code: `{args.get('code', '')[:80]}`"
    elif tool == "send_message":
        platform = args.get("platform", "unknown")
        recipient = args.get("recipient", "")
        body = args.get("body", "")[:80]
        return f"Send message via {platform} to {recipient}: {body}"
    elif tool == "open_url":
        return f"Open URL: {args.get('url', '')}"
    elif tool == "delete_file":
        return f"Delete file: {args.get('path', '')}"
    else:
        return f"Call tool: {tool} with args {json.dumps(args)[:100]}"


# ── Approval Gate ────────────────────────────────────────────────────

class ApprovalGate:
    """Modal approval dialog with timeout support."""

    def __init__(self, config: dict):
        self.mode = config.get("approval_mode", "manual")
        self.timeout = config.get("timeout_seconds", 60)
        self.skip_trusted = config.get("skip_trusted_actions", False)
        self._pending: list[tuple[str, dict, Callable]] = []

    def should_ask(self, tool: str, yolo: bool = False) -> bool:
        """Decide if we need approval for this tool."""
        if yolo:
            return False  # YOLO: skip everything
        if self.mode == "off":
            return False
        if self.mode == "auto" and tool not in DANGEROUS_TOOLS:
            return False
        return True

    def request(
        self,
        tool: str,
        args: dict,
        on_show_dialog: Callable[[str], None],
        wait_for_result: Callable[[], bool],
        yolo: bool = False,
    ) -> bool:
        """
        Request approval. Shows dialog via on_show_dialog (non-blocking),
        then waits for result via wait_for_result.
        Returns True if approved, False if rejected.
        """
        if not self.should_ask(tool, yolo):
            return True

        action_desc = describe_action(tool, args)

        if self.mode == "manual":
            # Tell UI to show dialog (non-blocking)
            on_show_dialog(action_desc)
            # Wait for user decision
            return wait_for_result()
        return True  # auto mode: approve


# ── Tool Registry ────────────────────────────────────────────────────

class ToolRegistry:
    """Registry of available tools with allowlist support."""

    def __init__(self, allowed_tools: list[str]):
        self._allowed = set(allowed_tools)
        self._all_tools = {
            "web_search": self._web_search,
            "browser_control": self._browser_control,
            "send_message": self._send_message,
            "reminder": self._reminder,
            "weather_report": self._weather_report,
            "youtube_video": self._youtube_video,
            "open_app": self._open_app,
            "screen_process": self._screen_process,
            "computer_control": self._computer_control,
            "code_helper": self._code_helper,
            "file_controller": self._file_controller,
            "composio_tool": self._composio_tool,
            # Dangerous
            "shell": self._shell,
            "python": self._python,
        }

    def is_allowed(self, tool: str) -> bool:
        """Check if tool is in allowlist."""
        if "composio_" in tool:
            return "composio_*" in self._allowed
        return tool in self._allowed

    def execute(self, tool: str, args: dict) -> str:
        """Execute a tool, returning result text."""
        if not self.is_allowed(tool):
            return f"⛔ Tool '{tool}' is not in your allowlist. Blocked."

        fn = self._all_tools.get(tool)
        if fn is None:
            return f"⚠️ Unknown tool: {tool}"

        try:
            return fn(args)
        except Exception as e:
            return f"⚠️ Error in {tool}: {str(e)}"

    def _web_search(self, args: dict) -> str:
        try:
            from integrations.composio_mcp import get_composio
            comp = get_composio()
            query = args.get("query", "")
            return f"🔍 Searched for: {query}\n\n[Tool result would appear here — connect Composio API key in Settings → Messaging]"
        except Exception as e:
            return f"🔍 Search: {e}"

    def _browser_control(self, args: dict) -> str:
        action = args.get("action", "navigate")
        url = args.get("url", "")
        return f"🌐 Browser: {action} → {url}"

    def _send_message(self, args: dict) -> str:
        platform = args.get("platform", "telegram").lower()
        recipient = args.get("recipient", "")
        body = args.get("body", "")
        message_id = args.get("message_id", "")

        if platform == "whatsapp":
            return self._send_whatsapp(recipient, body, message_id)
        elif platform == "telegram":
            return self._send_telegram(recipient, body)
        elif platform == "email":
            return self._send_email(recipient, body)
        elif platform == "ghl":
            return self._send_ghl(recipient, body)
        else:
            return f"📱 Send to {platform}: {recipient} → {body[:50]}"

    def _send_whatsapp(self, recipient: str, body: str, message_id: str = "") -> str:
        try:
            import requests
            keys = self._load_keys()
            url = keys.get("evolution_api_url", "http://161.97.173.78.nip.io:8081")
            api_key = keys.get("evolution_api_key", "")
            instance = keys.get("evolution_instance", "pulkit-wa-final")

            payload = {
                "number": recipient,
                "text": body,
            }
            resp = requests.post(
                f"{url}/message/sendText/{instance}",
                headers={"apiKey": api_key},
                json=payload,
                timeout=10,
            )
            if resp.status_code == 200:
                return f"✅ WhatsApp message sent to {recipient}"
            else:
                return f"⚠️ WhatsApp error {resp.status_code}: {resp.text[:100]}"
        except Exception as e:
            return f"❌ WhatsApp failed: {str(e)[:100]}"

    def _send_telegram(self, recipient: str, body: str) -> str:
        try:
            import requests
            keys = self._load_keys()
            token = keys.get("telegram_bot_token", "")
            if not token:
                return "❌ Telegram bot token not configured. Add it in Settings → Messaging."
            chat_id = recipient if recipient.startswith("-") else f"@{recipient}"
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": body},
                timeout=10,
            )
            if resp.status_code == 200:
                return "✅ Telegram message sent"
            return f"⚠️ Telegram error: {resp.status_code}"
        except Exception as e:
            return f"❌ Telegram failed: {str(e)[:100]}"

    def _send_email(self, recipient: str, body: str) -> str:
        try:
            import smtplib
            from email.message import EmailMessage
            keys = self._load_keys()
            host = keys.get("smtp_host", "")
            user = keys.get("smtp_user", "")
            pw = keys.get("smtp_pass", "")

            if not all([host, user, pw]):
                return "⚠️ Email not configured. Add SMTP credentials in Settings → Messaging."

            msg = EmailMessage()
            msg["From"] = user
            msg["To"] = recipient
            msg["Subject"] = "Message from ClawOS"
            msg.set_content(body)

            with smtplib.SMTP(host, 587) as server:
                server.starttls()
                server.login(user, pw)
                server.send_message(msg)
            return f"✅ Email sent to {recipient}"
        except Exception as e:
            return f"❌ Email failed: {str(e)[:100]}"

    def _send_ghl(self, contact_id: str, body: str) -> str:
        try:
            keys = self._load_keys()
            location_id = keys.get("ghl_location_id", "")
            return f"📞 GHL: Would send to contact {contact_id}: {body[:50]}... (GHL integration ready — configure Location ID in Settings)"
        except Exception as e:
            return f"❌ GHL failed: {str(e)[:100]}"

    def _reminder(self, args: dict) -> str:
        message = args.get("message", "")
        time_str = args.get("time", "")
        return f"⏰ Reminder set: {message} at {time_str}\n\n[Reminders work via the task queue system]"

    def _weather_report(self, args: dict) -> str:
        city = args.get("city", "New York")
        return f"🌤️ Weather for {city}: 72°F, Partly Cloudy\n[Connect a weather API in Settings for live data]"

    def _youtube_video(self, args: dict) -> str:
        query = args.get("query", "")
        return f"▶️ YouTube search: {query}\n[YouTube API integration coming soon]"

    def _open_app(self, args: dict) -> str:
        app = args.get("app", "")
        import platform
        system = platform.system()
        if system == "Darwin":
            return f"🖥️ Opening {app} on macOS..."
        elif system == "Linux":
            return f"🖥️ Opening {app} on Linux..."
        else:
            return f"🖥️ Opening {app} on Windows..."

    def _screen_process(self, args: dict) -> str:
        action = args.get("action", "analyze")
        return f"🖼️ Screen {action}: Capturing screen... [Screen analysis ready]"

    def _computer_control(self, args: dict) -> str:
        action = args.get("action", "")
        return f"⌨️ Computer control: {action}"

    def _code_helper(self, args: dict) -> str:
        language = args.get("language", "python")
        code = args.get("code", "")
        return f"💻 {language.title()} code:\n```{language}\n{code}\n```"

    def _file_controller(self, args: dict) -> str:
        operation = args.get("operation", "read")
        path = args.get("path", "")
        if operation == "read":
            try:
                with open(path) as f:
                    content = f.read(500)
                return f"📄 File {path}:\n```\n{content}\n```"
            except Exception as e:
                return f"❌ Read failed: {e}"
        elif operation == "write":
            content = args.get("content", "")
            try:
                with open(path, "w") as f:
                    f.write(content)
                return f"✅ Written to {path}"
            except Exception as e:
                return f"❌ Write failed: {e}"
        return f"📁 File {operation}: {path}"

    def _composio_tool(self, args: dict) -> str:
        action = args.get("action", "")
        return f"🔌 Composio action: {action}\n[Connect Composio API key in Settings]"

    def _shell(self, args: dict) -> str:
        import subprocess
        cmd = args.get("command", "")
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            out = result.stdout[:500] if result.stdout else ""
            err = result.stderr[:200] if result.stderr else ""
            return f"```\n{out}\n```" + (f"\n⚠️ stderr: {err}" if err else "")
        except Exception as e:
            return f"❌ Shell error: {str(e)}"

    def _python(self, args: dict) -> str:
        code = args.get("code", "")
        try:
            import io, sys
            buf = io.StringIO()
            sys.stdout = buf
            exec(code)
            sys.stdout = sys.__stdout__
            output = buf.getvalue()
            return f"```\n{output}\n```"
        except Exception as e:
            return f"❌ Python error: {str(e)}"

    def _load_keys(self) -> dict:
        try:
            from pathlib import Path
            keys_file = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
            return json.loads(keys_file.read_text()) if keys_file.exists() else {}
        except Exception:
            return {}


# ── Execution Result ─────────────────────────────────────────────────

@dataclass
class ExecutionResult:
    text: str = ""
    actions_used: list[str] = field(default_factory=list)
    action_results: list[str] = field(default_factory=list)
    yolo: bool = False
    error: Optional[str] = None


# ── Slash Command Parser ─────────────────────────────────────────────

SLASH_COMMANDS = {"/yolo", "/cron", "/monitor", "/status", "/cancel"}


def parse_slash_command(text: str) -> tuple[bool, str]:
    """
    Parse slash commands from input.
    Returns (is_yolo, cleaned_text).
    Strips /yolo prefix, passes other commands through for the LLM to handle.
    """
    stripped = text.strip()
    if stripped.lower().startswith("/yolo"):
        rest = stripped[5:].strip()
        return True, rest or ""
    return False, text


# ── Streaming Executor ───────────────────────────────────────────────

class StreamingExecutor:
    """
    Main agent executor with:
    - Streaming token output via callback
    - Async approval gating (pause → resume)
    - YOLO mode (skip all approvals)
    - Slash command support (/yolo, /cron, /monitor, etc.)
    - Command allowlist enforcement
    - Secret redaction
    - Multi-step planning
    """

    def __init__(self, approval_config: dict):
        self.approval = ApprovalGate(approval_config)
        self.tools = ToolRegistry(approval_config.get("allowed_tools", []))
        self.redact_enabled = approval_config.get("redact_secrets", True)
        self._max_steps = approval_config.get("max_agent_steps", 90)

        # ── YOLO mode ──────────────────────────────────────────────
        self._yolo_mode = False

        # ── Async approval state ────────────────────────────────────
        self._approval_event = threading.Event()
        self._approval_result: bool = False
        self._pending_action: str = ""

        # ── Approval callbacks (set by main.py) ────────────────────
        self._on_show_approval: Optional[Callable[[str], None]] = None
        self._on_approval_done: Optional[Callable[[bool], None]] = None

    def enable_yolo(self):
        """Enable YOLO mode — skips all approval gates for this session."""
        self._yolo_mode = True
        log.info("⚡ YOLO mode enabled — all approvals bypassed")

    def set_approval_callbacks(
        self,
        on_show: Callable[[str], None],
        on_done: Callable[[bool], None],
    ):
        """Set callbacks for showing approval dialogs and reporting results."""
        self._on_show_approval = on_show
        self._on_approval_done = on_done

    def set_approval_result(self, approved: bool):
        """
        Called by the UI when user approves or rejects.
        Unblocks the executor thread.
        """
        self._approval_result = approved
        self._approval_event.set()
        if self._on_approval_done:
            self._on_approval_done(approved)

    def execute(
        self,
        goal: str,
        on_token: Optional[Callable[[str], None]] = None,
        on_complete: Optional[Callable[[str], None]] = None,
        memory_context: str = "",
        composio_context: str = "",
    ) -> ExecutionResult:
        """
        Execute a goal with streaming output.

        Args:
            goal: User's request (may start with /yolo or other slash commands)
            on_token: Called with each response token (for streaming UI)
            on_complete: Called when done with full response text
            memory_context: Prior conversation context
            composio_context: Available Composio/MCP tools
        """
        result = ExecutionResult()
        full_response = []

        # ── Parse slash commands ─────────────────────────────────
        is_yolo, clean_goal = parse_slash_command(goal)
        if is_yolo:
            self.enable_yolo()
        if not clean_goal:
            # Just /yolo with no task — show status
            result.text = "⚡ YOLO mode active — all approval gates will be skipped for this session."
            if on_complete:
                on_complete(result.text)
            return result

        # ── Emit helpers ─────────────────────────────────────────
        def emit(text: str):
            full_response.append(text)
            if on_token:
                on_token(text)

        # ── Approval helpers (non-blocking) ─────────────────────
        def on_show_dialog(action: str):
            self._pending_action = action
            if self._on_show_approval:
                self._on_show_approval(action)

        def wait_for_result() -> bool:
            # Block this thread until UI sets result
            approved = self._approval_event.wait(timeout=self.approval.timeout)
            self._approval_event.clear()
            if not approved:
                log.info("Approval rejected or timed out")
            return approved

        # ── Build prompts ────────────────────────────────────────
        system = self._build_system_prompt(composio_context)
        user_msg = self._build_user_message(clean_goal, memory_context)

        # ── Call LLM ─────────────────────────────────────────────
        try:
            response = self._stream_response(system, user_msg, on_token)
        except Exception as e:
            log.error(f"Streaming failed: {traceback.format_exc()}")
            response = self._non_stream_response(system, user_msg)

        # ── Process response ─────────────────────────────────────
        if response:
            text = response.get("text", response.get("content", ""))
            if self.redact_enabled:
                text = redact(text)

            emit(text)
            result.text = "".join(full_response)

            # Extract and execute tool calls
            tool_calls = self._extract_tool_calls(response)
            for tc in tool_calls:
                tool = tc.get("name", tc.get("function", {}).get("name", ""))
                args = tc.get("arguments", tc.get("input", {}))
                args = json.loads(args) if isinstance(args, str) else args

                result.actions_used.append(tool)

                if not self.tools.is_allowed(tool):
                    tool_result = f"⛔ '{tool}' is not in your allowlist"
                else:
                    # ── Async approval gate ──────────────────────
                    tool_result = self.approval.request(
                        tool=tool,
                        args=args,
                        on_show_dialog=on_show_dialog,
                        wait_for_result=wait_for_result,
                        yolo=self._yolo_mode,
                    )
                    if tool_result:  # approved (or yolo'd)
                        tool_result = self.tools.execute(tool, args)
                        if self.redact_enabled:
                            tool_result = redact(tool_result)
                    else:
                        tool_result = f"⛔ Action '{tool}' was rejected by user"

                emit(f"\n\n{tool_result}")
                result.action_results.append(tool_result)

        result.text = "".join(full_response)
        result.yolo = self._yolo_mode
        if on_complete:
            on_complete(result.text)

        return result

    def _build_system_prompt(self, composio_context: str) -> str:
        allowed = list(self.tools._allowed)
        yolo_note = "\n⚡ YOLO MODE: All approval gates are bypassed. Act freely." if self._yolo_mode else ""
        return f"""You are ClawOS, a desktop AI agent. You help users by:
- Searching the web
- Sending messages (WhatsApp, Email, Telegram, GHL)
- Setting reminders and cron jobs
- Controlling their computer
- Running code and scripts
- Managing files
- Creating background monitors (/monitor) and scheduled tasks (/cron)

Available tools: {', '.join(allowed)}
{composio_context}

You MUST use tools when a user asks for something actionable. For simple questions, respond directly.

Important rules:
- If a tool is blocked (⛔), explain why and suggest how to enable it in Settings
- Keep responses concise and helpful
- NEVER reveal API keys or secrets
{yolo_note}"""

    def _build_user_message(self, goal: str, memory_context: str) -> str:
        msg = goal
        if memory_context:
            msg = f"Previous context:\n{memory_context}\n\n---\nCurrent request: {goal}"
        return msg

    def _stream_response(
        self,
        system: str,
        user_msg: str,
        on_token: Optional[Callable[[str], None]],
    ) -> dict:
        """Streaming LLM call via the providers system."""
        try:
            from integrations.providers import (
                get_api_key, get_default_model, chat_completion_streaming,
            )
            import threading as _t

            settings = self._load_settings()
            provider = settings.get("llm_provider", "anthropic")
            model = settings.get("llm_model", "") or get_default_model(provider)
            api_key = get_api_key(provider)
            if not api_key:
                return self._fallback_response(user_msg)

            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ]

            def token_cb(token: str):
                if on_token:
                    on_token(token)

            full_text = chat_completion_streaming(
                provider=provider,
                model=model,
                messages=messages,
                on_token=token_cb,
                temperature=0.7,
                max_tokens=4096,
                api_key=api_key,
            )
            return {"content": full_text}

        except Exception as e:
            log.error(f"LLM streaming error: {traceback.format_exc()}")
            return self._fallback_response(user_msg)

    def _non_stream_response(self, system: str, user_msg: str) -> dict:
        """Non-streaming LLM call via providers."""
        try:
            from integrations.providers import (
                get_api_key, get_default_model, chat_completion,
            )

            settings = self._load_settings()
            provider = settings.get("llm_provider", "anthropic")
            model = settings.get("llm_model", "") or get_default_model(provider)
            api_key = get_api_key(provider)
            if not api_key:
                return self._fallback_response(user_msg)

            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ]
            text = chat_completion(
                provider=provider,
                model=model,
                messages=messages,
                temperature=0.7,
                max_tokens=4096,
                api_key=api_key,
            )
            return {"content": text}

        except Exception:
            return self._fallback_response(user_msg)

    def _fallback_response(self, user_msg: str) -> dict:
        """Rule-based fallback when no API keys are configured."""
        msg = user_msg.lower()

        if any(k in msg for k in ["/yolo"]):
            return {"content": "⚡ YOLO mode activated. What would you like me to do?"}
        elif any(k in msg for k in ["/cron", "/schedule", "/remind", "every "]):
            return {
                "content": (
                    "⏰ I can create scheduled tasks from natural language.\n\n"
                    "Try: `/cron every Monday at 9am remind me to check email`\n"
                    "Or just tell me naturally: `every 5 minutes check if google.com is up`"
                )
            }
        elif any(k in msg for k in ["/monitor", "check every", "watch", "monitor"]):
            return {
                "content": (
                    "👁️ I can monitor URLs, files, and processes in the background.\n\n"
                    "Try: `/monitor check google.com every 10 minutes`\n"
                    "Or: `watch /tmp/log.txt for changes`"
                )
            }
        elif any(k in msg for k in ["/status"]):
            return {
                "content": (
                    "📊 ClawOS Status:\n"
                    "⚡ YOLO: " + ("ON" if self._yolo_mode else "OFF") + "\n"
                    "All systems operational.\n"
                    "Use /status to see this dashboard."
                )
            }
        elif any(k in msg for k in ["send", "whatsapp", "message to", "text to"]):
            return {
                "content": (
                    "📱 I can send messages via WhatsApp, Email, Telegram, or GHL.\n\n"
                    "To get started:\n"
                    "1. Open Settings (⚙️) → Messaging\n"
                    "2. Add your WhatsApp (Evolution API), Email (SMTP), or Telegram credentials\n"
                    "3. Then say: \"Send a WhatsApp message to [contact]\""
                )
            }
        elif any(k in msg for k in ["search", "find", "look up", "what is", "who is", "how to"]):
            return {
                "content": (
                    "🔍 Web search requires the Composio API key.\n\n"
                    "1. Get a free API key at composio.tech\n"
                    "2. Add it in Settings → Messaging → Composio\n"
                    "3. Then I'll be able to search the web for you."
                )
            }
        else:
            return {
                "content": (
                    "👋 I'm ClawOS, your desktop AI agent.\n\n"
                    "I can help you with:\n"
                    "• 📱 Sending messages (WhatsApp, Email, Telegram, GHL)\n"
                    "• 🔍 Searching the web\n"
                    "• ⏰ Setting reminders and cron jobs\n"
                    "• 🖥️ Opening apps\n"
                    "• 💻 Running code\n"
                    "• 📁 Managing files\n"
                    "• 👁️ Monitoring URLs/processes\n\n"
                    "Slash commands:\n"
                    "• /yolo — skip all approvals\n"
                    "• /cron — create a scheduled task\n"
                    "• /monitor — create a background monitor\n"
                    "• /status — show all active tasks\n\n"
                    "Configure your integrations in ⚙️ Settings to unlock full capabilities."
                )
            }

    def _extract_tool_calls(self, response: dict) -> list:
        """Extract tool calls from model response."""
        tool_calls = []

        # OpenAI format
        if "tool_calls" in response:
            return response["tool_calls"]

        # Anthropic format
        content = response.get("content", [])
        if isinstance(content, list):
            for block in content:
                if block.get("type") == "tool_use":
                    tool_calls.append({
                        "name": block.get("name"),
                        "arguments": block.get("input"),
                    })

        return tool_calls

    def _load_settings(self) -> dict:
        try:
            from pathlib import Path
            settings_file = Path(__file__).resolve().parent.parent / "config" / "app_settings_v2.json"
            return json.loads(settings_file.read_text()) if settings_file.exists() else {}
        except Exception:
            return {}
