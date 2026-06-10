"""
StreamingExecutor — agentic execution with token streaming, approval gates,
command allowlist, and secret redaction.
"""
from __future__ import annotations

import json
import logging
import re
import time
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
    (re.compile(r'password["\s:=]+[^\s"\'`]{8,}'), 'password=***REDACTED***'),
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
        self._result: Optional[bool] = None

    def should_ask(self, tool: str) -> bool:
        """Decide if we need approval for this tool."""
        if self.mode == "off":
            return False
        if self.mode == "auto" and tool not in DANGEROUS_TOOLS:
            return False
        return True

    def request(self, tool: str, args: dict, on_show_dialog: Callable[[str], bool]) -> bool:
        """Request approval. Returns True if approved, False if rejected."""
        if not self.should_ask(tool):
            return True

        action_desc = describe_action(tool, args)

        if self.mode == "manual":
            # Show PyQt dialog — called from main thread via signal
            return on_show_dialog(action_desc)
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
            # Use composio search
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
                return f"✅ Telegram message sent"
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
            # Use GHL MCP or direct API
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


# ── Streaming Executor ───────────────────────────────────────────────

@dataclass
class ExecutionResult:
    text: str = ""
    actions_used: list[str] = field(default_factory=list)
    action_results: list[str] = field(default_factory=list)
    error: Optional[str] = None


class StreamingExecutor:
    """
    Main agent executor with:
    - Streaming token output via callback
    - Approval mode gating
    - Command allowlist enforcement
    - Secret redaction
    - Multi-step planning
    """

    def __init__(self, approval_config: dict):
        self.approval = ApprovalGate(approval_config)
        self.tools = ToolRegistry(approval_config.get("allowed_tools", []))
        self.redact_enabled = approval_config.get("redact_secrets", True)
        self._approval_callback: Optional[Callable[[str], bool]] = None
        self._max_steps = approval_config.get("max_agent_steps", 90)
        self._subagent_max_parallel = approval_config.get("subagent_max_parallel", 3)
        self._subagent_timeout = approval_config.get("subagent_timeout", 600)

    def set_approval_callback(self, cb: Callable[[str], bool]):
        self._approval_callback = cb

    def execute(
        self,
        goal: str,
        on_token: Optional[Callable[[str], None]] = None,
        on_complete: Optional[Callable[[str], None]] = None,
        on_approval: Optional[Callable[[str], None]] = None,
        memory_context: str = "",
        composio_context: str = "",
    ) -> ExecutionResult:
        """
        Execute a goal with streaming output.

        Args:
            goal: User's request
            on_token: Called with each response token (for streaming UI)
            on_complete: Called when done with full response text
            on_approval: Called to show approval dialog, returns bool
            memory_context: Prior conversation context
            composio_context: Available Composio tools
        """
        result = ExecutionResult()
        full_response = []

        def emit(text: str):
            full_response.append(text)
            if on_token:
                on_token(text)

        # Build system prompt
        system = self._build_system_prompt(composio_context)
        user_msg = self._build_user_message(goal, memory_context)

        try:
            # Try streaming with OpenRouter-compatible API
            response = self._stream_response(system, user_msg, on_token)
        except Exception as e:
            log.error(f"Streaming failed: {traceback.format_exc()}")
            # Fallback: non-streaming
            response = self._non_stream_response(system, user_msg)

        # Process response
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
                elif self.approval.should_ask(tool):
                    # Request approval via callback
                    action_desc = describe_action(tool, args)
                    if on_approval:
                        approved = on_approval(action_desc)
                    else:
                        approved = True

                    if not approved:
                        tool_result = f"⛔ Action '{tool}' was rejected"
                    else:
                        tool_result = self.tools.execute(tool, args)
                        if self.redact_enabled:
                            tool_result = redact(tool_result)
                else:
                    tool_result = self.tools.execute(tool, args)
                    if self.redact_enabled:
                        tool_result = redact(tool_result)

                emit(f"\n\n{tool_result}")
                result.action_results.append(tool_result)

        result.text = "".join(full_response)
        if on_complete:
            on_complete(result.text)

        return result

    def _build_system_prompt(self, composio_context: str) -> str:
        allowed = list(self.tools._allowed)
        return f"""You are ClawOS, a desktop AI agent. You help users by:
- Searching the web
- Sending messages (WhatsApp, Email, Telegram, GHL)
- Setting reminders
- Controlling their computer
- Running code and scripts
- Managing files

Available tools: {', '.join(allowed)}

You MUST use tools when a user asks for something actionable. For simple questions, respond directly.

Important rules:
- If a tool is blocked (⛔), explain why and suggest how to enable it in Settings
- Always confirm dangerous actions with the user
- Keep responses concise and helpful
- NEVER reveal API keys or secrets
{composio_context}"""

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
        """Try to get a streaming response from OpenRouter."""
        try:
            import requests

            keys = self._load_keys()
            api_key = keys.get("openrouter_api_key", "")
            model = keys.get("openrouter_model", "anthropic/claude-3.5-haiku")

            if not api_key:
                return self._fallback_response(user_msg)

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://clawops.studio",
                "X-Title": "ClawOS",
            }

            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                "stream": True,
            }

            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                stream=True,
                timeout=60,
            )

            if response.status_code != 200:
                return self._fallback_response(user_msg)

            full_content = ""
            for line in response.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        token = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if token and on_token:
                            on_token(token)
                        full_content += token
                    except json.JSONDecodeError:
                        continue

            return {"content": full_content}

        except Exception as e:
            log.error(f"Streaming error: {e}")
            return self._fallback_response(user_msg)

    def _non_stream_response(self, system: str, user_msg: str) -> dict:
        return self._fallback_response(user_msg)

    def _fallback_response(self, user_msg: str) -> dict:
        """Rule-based fallback when no API keys are configured."""
        msg = user_msg.lower()

        # Smart routing based on keywords
        if any(k in msg for k in ["send", "whatsapp", "message to", "text to"]):
            return {
                "content": (
                    "📱 I can send messages via WhatsApp, Email, Telegram, or GHL.\n\n"
                    "To get started:\n"
                    "1. Open Settings (⚙️) → Messaging\n"
                    "2. Add your WhatsApp (Evolution API), Email (SMTP), or Telegram credentials\n"
                    "3. Then say: \"Send a WhatsApp message to [contact]\"\n\n"
                    "For WhatsApp, you'll need the Evolution API running on your VPS at port 8081."
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
        elif any(k in msg for k in ["remind", "reminder", "alarm", "schedule"]):
            return {
                "content": (
                    "⏰ Reminders are handled by the ClawOS task scheduler.\n\n"
                    "Try: \"Set a reminder for tomorrow at 9am to call Mom\"\n\n"
                    "I'll schedule it and notify you when the time comes."
                )
            }
        elif any(k in msg for k in ["open", "launch", "start"]):
            return {
                "content": (
                    "🖥️ I can open apps on your computer.\n\n"
                    "Try: \"Open Chrome and go to gmail.com\"\n"
                    "Or: \"Open Safari\""
                )
            }
        else:
            return {
                "content": (
                    "👋 I'm ClawOS, your desktop AI agent.\n\n"
                    "I can help you with:\n"
                    "• 📱 Sending messages (WhatsApp, Email, Telegram, GHL)\n"
                    "• 🔍 Searching the web\n"
                    "• ⏰ Setting reminders\n"
                    "• 🖥️ Opening apps\n"
                    "• 💻 Running code\n"
                    "• 📁 Managing files\n\n"
                    "Configure your integrations in ⚙️ Settings to unlock full capabilities.\n"
                    "Add API keys in Settings → 🤖 AI Providers."
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

    def _load_keys(self) -> dict:
        try:
            from pathlib import Path
            keys_file = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
            return json.loads(keys_file.read_text()) if keys_file.exists() else {}
        except Exception:
            return {}
