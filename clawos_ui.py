"""
ClawOS v2 — Desktop AI Agent UI
Dark/light themes, orb, streaming, approval mode, all integrations.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import psutil
from PyQt6.QtCore import (
    QEvent, QObject, QPoint, QRect, QSize, Qt, QTimer, QUrl,
    QSizeGripStyle, pyqtSignal, QRectF,
)
from PyQt6.QtGui import (
    QAction, QBrush, QColor, QConicalGradient, QFont, QFontDatabase,
    QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
    QRadialGradient, QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMenu, QMessageBox, QProgressBar,
    QPushButton, QRadioButton, QScrollArea, QSizePolicy, QSlider,
    QStackedWidget, QTextEdit, QVBoxLayout, QWidget, QCheckBox,
    QGroupBox, QTabWidget, QToolButton, QScrollBar,
    QGraphicsDropShadowEffect,
)

log = logging.getLogger("clawos_ui")

# ── Paths ──────────────────────────────────────────────────────────────

def _base_dir() -> Path:
    import sys
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
API_KEYS_FILE = CONFIG_DIR / "api_keys.json"
SETTINGS_FILE = CONFIG_DIR / "app_settings_v2.json"
APPROVAL_FILE = CONFIG_DIR / "approval_config.json"


# ── Color Palettes ─────────────────────────────────────────────────────

class C:
    """Theme-aware color class. Call C.refresh() after theme switch."""

    DARK = {
        "BG": "#0a0a12",
        "BG2": "#12121c",
        "BG3": "#1a1a2e",
        "PANEL": "#0e0e1a",
        "PANEL2": "#16162a",
        "BORDER": "#2a2a3e",
        "BORDER_B": "#3a3a5a",
        "TEXT": "#e8eaed",
        "TEXT_MED": "#a0a8b8",
        "TEXT_MUTED": "#606878",
        "ACC": "#e63946",
        "ACC_DIM": "#ff6b75",
        "ACC_GHO": "#3d0f14",
        "GREEN": "#22c55e",
        "GREEN_DIM": "#4ade80",
        "RED": "#e63946",
        "ORANGE": "#f97316",
        "BLUE": "#3b82f6",
        "PURPLE": "#a855f7",
        "CYAN": "#06b6d4",
        "MUTED_C": "#6b7280",
        "BAR_BG": "#1e1e32",
        "SCROLL_BG": "#16162a",
    }

    LIGHT = {
        "BG": "#f0f2f8",
        "BG2": "#ffffff",
        "BG3": "#e8ebf2",
        "PANEL": "#ffffff",
        "PANEL2": "#f8f9fc",
        "BORDER": "#d1d5e0",
        "BORDER_B": "#b0b8cc",
        "TEXT": "#1a1a2e",
        "TEXT_MED": "#4a5568",
        "TEXT_MUTED": "#8a96a8",
        "ACC": "#e63946",
        "ACC_DIM": "#ef4444",
        "ACC_GHO": "#fee2e2",
        "GREEN": "#16a34a",
        "GREEN_DIM": "#22c55e",
        "RED": "#dc2626",
        "ORANGE": "#ea580c",
        "BLUE": "#2563eb",
        "PURPLE": "#9333ea",
        "CYAN": "#0891b2",
        "MUTED_C": "#9ca3af",
        "BAR_BG": "#e8ebf2",
        "SCROLL_BG": "#f0f2f8",
    }

    _theme = "dark"
    _cache = {}

    @classmethod
    def get(cls, key: str) -> str:
        return cls._cache.get(key, cls.DARK.get(key, "#000000"))

    @classmethod
    def refresh(cls):
        palette = cls.DARK if cls._theme == "dark" else cls.LIGHT
        cls._cache = dict(palette)


def qcolor(hex_str: str, alpha: int = 255) -> QColor:
    c = QColor(hex_str)
    c.setAlpha(alpha)
    return c


def _load_keys() -> dict:
    try:
        return json.loads(API_KEYS_FILE.read_text()) if API_KEYS_FILE.exists() else {}
    except Exception:
        return {}


def _save_keys(data: dict):
    API_KEYS_FILE.write_text(json.dumps(data, indent=2))


def _load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text()) if SETTINGS_FILE.exists() else {}
    except Exception:
        return {}


def _save_settings(data: dict):
    SETTINGS_FILE.write_text(json.dumps(data, indent=2))


def _load_approval() -> dict:
    try:
        return json.loads(APPROVAL_FILE.read_text()) if APPROVAL_FILE.exists() else {}
    except Exception:
        return {}


def _save_approval(data: dict):
    APPROVAL_FILE.write_text(json.dumps(data, indent=2))


# ── Streaming Chat Bubble ──────────────────────────────────────────────

class ChatBubble(QFrame):
    def __init__(self, role: str, text: str, timestamp: str = "", parent=None):
        super().__init__(parent)
        self.role = role
        self._text = text
        self._displayed = ""
        self._full_text = text
        self._streaming_done = role != "assistant" or not text

        is_user = role == "user"
        bg = C.get("BG3") if is_user else C.get("PANEL2")
        border = C.get("ACC_GHO") if is_user else C.get("BORDER")
        align = Qt.AlignmentFlag.AlignRight if is_user else Qt.AlignmentFlag.AlignLeft
        text_color = C.get("TEXT")

        self.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 12px;
                padding: 10px 14px;
                margin: 4px 0px;
            }}
        """)
        self.setMaximumWidth(680)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(2)

        header = QHBoxLayout()
        header.setSpacing(6)

        role_lbl = QLabel("You" if is_user else "🟣 ClawOS")
        role_lbl.setStyleSheet(f"color: {C.get('ACC') if not is_user else C.get('BLUE')}; font-size: 11px; font-weight: 700;")
        header.addWidget(role_lbl)
        header.addStretch()

        if timestamp:
            ts_lbl = QLabel(timestamp)
            ts_lbl.setStyleSheet(f"color: {C.get('TEXT_MUTED')}; font-size: 10px;")
            header.addWidget(ts_lbl)

        lay.addLayout(header)

        self.content_lbl = QLabel(text)
        self.content_lbl.setWordWrap(True)
        self.content_lbl.setTextFormat(Qt.TextFormat.PlainText)
        self.content_lbl.setStyleSheet(f"""
            color: {text_color};
            font-size: 13px;
            line-height: 1.5;
            background: transparent;
            border: none;
        """)
        self.content_lbl.setOpenExternalLinks(True)
        lay.addWidget(self.content_lbl)

        if not self._streaming_done:
            self._stream_timer = QTimer(self)
            self._stream_timer.timeout.connect(self._stream_step)
            self._stream_timer.start(8)

    def _stream_step(self):
        if len(self._displayed) < len(self._full_text):
            chunk = min(3, len(self._full_text) - len(self._displayed))
            self._displayed += self._full_text[len(self._displayed):len(self._displayed) + chunk]
            self.content_lbl.setText(self._displayed)
        else:
            self._stream_timer.stop()
            self._streaming_done = True

    def append(self, token: str):
        if self._streaming_done:
            return
        self._full_text += token
        self._displayed = self._full_text
        self.content_lbl.setText(self._full_text)
        self._streaming_done = True
        if hasattr(self, "_stream_timer"):
            self._stream_timer.stop()


# ── Approval Dialog ────────────────────────────────────────────────────

class ApprovalDialog(QDialog):
    def __init__(self, action: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⏸ Approval Required")
        self.setModal(True)
        self.setMinimumWidth(480)

        palette = {
            "BG": C.get("BG2"),
            "TEXT": C.get("TEXT"),
            "BORDER": C.get("BORDER"),
            "ACC": C.get("ACC"),
            "GREEN": C.get("GREEN"),
        }
        self.setStyleSheet(f"""
            QDialog {{ background: {palette['BG']}; border: 1px solid {palette['BORDER']}; border-radius: 12px; }}
        """)

        lay = QVBoxLayout(self)
        lay.setSpacing(16)
        lay.setContentsMargins(24, 24, 24, 24)

        title = QLabel("🔒 Approval Required")
        title.setStyleSheet(f"color: {palette['ACC']}; font-size: 16px; font-weight: 800;")
        lay.addWidget(title)

        desc = QLabel(f"Brahma wants to perform this action:")
        desc.setStyleSheet(f"color: {palette['TEXT']}; font-size: 13px;")
        lay.addWidget(desc)

        action_box = QTextEdit()
        action_box.setText(action)
        action_box.setReadOnly(True)
        action_box.setStyleSheet(f"""
            QTextEdit {{
                background: {C.get('BG3')};
                color: {palette['TEXT']};
                border: 1px solid {palette['BORDER']};
                border-radius: 8px;
                padding: 10px;
                font-size: 12px;
            }}
        """)
        action_box.setMaximumHeight(120)
        lay.addWidget(action_box)

        btns = QDialogButtonBox()
        btns.setStyleSheet(f"""
            QPushButton {{
                padding: 8px 20px;
                border-radius: 8px;
                font-weight: 700;
                font-size: 13px;
            }}
        """)
        approve = QPushButton("✅ Approve")
        approve.setStyleSheet(f"""
            QPushButton {{
                background: {palette['GREEN']};
                color: #fff;
                padding: 8px 20px;
                border-radius: 8px;
                font-weight: 700;
            }}
            QPushButton:hover {{ opacity: 0.85; }}
        """)
        reject = QPushButton("❌ Reject")
        reject.setStyleSheet(f"""
            QPushButton {{
                background: {C.get('BG3')};
                color: {palette['TEXT']};
                border: 1px solid {palette['BORDER']};
                padding: 8px 20px;
                border-radius: 8px;
            }}
        """)
        btns.addButton(approve, QDialogButtonBox.ButtonRole.AcceptRole)
        btns.addButton(reject, QDialogButtonBox.ButtonRole.RejectRole)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def get_result(self) -> bool:
        return self.exec() == QDialog.DialogCode.Accepted


# ── Settings Modal ────────────────────────────────────────────────────

class SettingsModal(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ ClawOS Settings")
        self.setModal(True)
        self.setMinimumSize(900, 600)
        self.resize(960, 680)
        self.setStyleSheet(f"""
            QDialog {{ background: {C.get('BG')}; border: 1px solid {C.get('BORDER')}; border-radius: 14px; }}
        """)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar nav
        self.nav = QListWidget()
        self.nav.setMaximumWidth(180)
        self.nav.setSpacing(0)
        self.nav.setStyleSheet(f"""
            QListWidget {{
                background: {C.get('BG2')};
                border: none;
                border-right: 1px solid {C.get('BORDER')};
                padding: 12px 0;
            }}
            QListWidget::item {{
                padding: 10px 16px;
                color: {C.get('TEXT_MED')};
                font-size: 13px;
                border-radius: 6px;
                margin: 2px 8px;
            }}
            QListWidget::item:selected, QListWidget::item:hover {{
                background: {C.get('BG3')};
                color: {C.get('TEXT')};
            }}
            QListWidget::item:selected {{
                color: {C.get('ACC')};
                font-weight: 700;
            }}
        """)
        pages = [
            "🤖  AI Providers",
            "🔒  Safety",
            "🔊  Voice",
            "🧠  Memory",
            "📱  Messaging",
            "🔌  MCP Servers",
            "⚙️  Advanced",
        ]
        for p in pages:
            self.nav.addItem(p)
        self.nav.currentRowChanged.connect(self._on_nav)
        root.addWidget(self.nav)

        # Content area
        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)

        self._build_providers_page()
        self._build_safety_page()
        self._build_voice_page()
        self._build_memory_page()
        self._build_messaging_page()
        self._build_mcp_page()
        self._build_advanced_page()

        self.nav.setCurrentRow(0)

    def _on_nav(self, row: int):
        self.pages.setCurrentIndex(row)

    def _section_title(self, icon: str, title: str, subtitle: str) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 8)
        v.setSpacing(2)
        t = QLabel(f"{icon}  {title}")
        t.setStyleSheet(f"color: {C.get('TEXT')}; font-size: 16px; font-weight: 800;")
        s = QLabel(subtitle)
        s.setStyleSheet(f"color: {C.get('TEXT_MUTED')}; font-size: 12px;")
        v.addWidget(t)
        v.addWidget(s)
        return w

    def _toggle_row(self, label: str, desc: str, default=False) -> tuple[QWidget, QCheckBox]:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 4, 0, 4)
        lay = QVBoxLayout()
        lay.setSpacing(1)
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {C.get('TEXT')}; font-size: 13px; font-weight: 600;")
        dsc = QLabel(desc)
        dsc.setStyleSheet(f"color: {C.get('TEXT_MUTED')}; font-size: 11px;")
        lay.addWidget(lbl)
        lay.addWidget(dsc)
        h.addLayout(lay, 1)
        cb = QCheckBox()
        cb.setChecked(default)
        cb.setStyleSheet(f"""
            QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 4px; border: 2px solid {C.get('BORDER_B')}; }}
            QCheckBox::indicator:checked {{ background: {C.get('ACC')}; border-color: {C.get('ACC')}; }}
        """)
        h.addWidget(cb)
        return w, cb

    def _slider_row(self, label: str, min_v: int, max_v: int, default: int, suffix: str = "") -> tuple[QWidget, QSlider, QLabel]:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 4, 0, 4)
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {C.get('TEXT')}; font-size: 13px; font-weight: 600; min-width: 200px;")
        h.addWidget(lbl)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(min_v)
        slider.setMaximum(max_v)
        slider.setValue(default)
        slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{ height: 4px; background: {C.get('BORDER')}; border-radius: 2px; }}
            QSlider::handle:horizontal {{ background: {C.get('ACC')}; width: 14px; height: 14px; border-radius: 7px; margin: -5px 0; }}
            QSlider::sub-page:horizontal {{ background: {C.get('ACC')}; border-radius: 2px; }}
        """)
        h.addWidget(slider, 1)
        val_lbl = QLabel(f"{default}{suffix}")
        val_lbl.setStyleSheet(f"color: {C.get('ACC')}; font-size: 12px; font-weight: 700; min-width: 50px;")
        slider.valueChanged.connect(lambda v: val_lbl.setText(f"{v}{suffix}"))
        h.addWidget(val_lbl)
        return w, slider, val_lbl

    def _input_row(self, label: str, placeholder: str = "", is_password: bool = False, default: str = "") -> tuple[QWidget, QLineEdit]:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 4, 0, 4)
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {C.get('TEXT')}; font-size: 13px; font-weight: 600; min-width: 160px;")
        h.addWidget(lbl)
        inp = QLineEdit()
        inp.setPlaceholderText(placeholder)
        inp.setText(default)
        inp.setEchoMode(QLineEdit.EchoMode.Password if is_password else QLineEdit.EchoMode.Normal)
        inp.setStyleSheet(f"""
            QLineEdit {{
                background: {C.get('BG3')};
                color: {C.get('TEXT')};
                border: 1px solid {C.get('BORDER')};
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 12px;
            }}
            QLineEdit:focus {{ border-color: {C.get('ACC')}; }}
        """)
        h.addWidget(inp, 1)
        return w, inp

    def _save_btn(self, on_save: Callable) -> QPushButton:
        btn = QPushButton("💾 Save Settings")
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.get('ACC')};
                color: #fff;
                padding: 10px 24px;
                border-radius: 10px;
                font-weight: 700;
                font-size: 14px;
            }}
            QPushButton:hover {{ opacity: 0.85; }}
        """)
        btn.clicked.connect(on_save)
        return btn

    def _card(self, children: list) -> QFrame:
        f = QFrame()
        f.setStyleSheet(f"""
            QFrame {{
                background: {C.get('BG2')};
                border: 1px solid {C.get('BORDER')};
                border-radius: 12px;
                padding: 14px;
            }}
        """)
        v = QVBoxLayout(f)
        v.setSpacing(8)
        for c in children:
            v.addWidget(c)
        return f

    def _spacer(self, height=12) -> QWidget:
        w = QWidget()
        w.setFixedHeight(height)
        return w

    # ── AI Providers Page ──────────────────────────────────────────────

    def _build_providers_page(self):
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setStyleSheet(f"QScrollArea {{ border: none; background: {C.get('BG')}; }}")
        sw = QWidget()
        v = QVBoxLayout(sw)
        v.setContentsMargins(24, 20, 24, 40)
        v.setSpacing(16)

        v.addWidget(self._section_title("🤖", "AI Providers", "Configure your model providers and API keys"))
        v.addWidget(self._spacer(8))

        providers = [
            ("openai", "OpenAI", "🤖", "sk-..."),
            ("anthropic", "Anthropic", "🧠", "sk-ant-..."),
            ("gemini", "Google Gemini", "✨", "AIza..."),
            ("openrouter", "OpenRouter", "🌐", "sk-or-..."),
            ("deepseek", "DeepSeek", "🔮", "sk-..."),
            ("groq", "Groq", "⚡", "gsk_..."),
            ("mistral", "Mistral", "🌊", "..."),
            ("xai", "xAI (Grok)", "🤖", "xai-..."),
            ("ollama", "Ollama Local", "🏠", "localhost:11434"),
        ]

        self._provider_widgets = {}
        keys = _load_keys()

        for pid, name, emoji, ph in providers:
            key_val = keys.get(f"{pid}_api_key", "")
            model_val = keys.get(f"{pid}_model", "")
            card = self._card([
                self._provider_row(pid, name, emoji, ph, key_val, model_val)
            ])
            v.addWidget(card)

        v.addWidget(self._save_btn(self._save_providers))
        v.addStretch()
        page.setWidget(sw)
        self.pages.addWidget(page)

    def _provider_row(self, pid: str, name: str, emoji: str, placeholder: str, key_val: str, model_val: str) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(4, 4, 4, 4)
        h.setSpacing(12)

        emoji_lbl = QLabel(f"<span style='font-size:22px'>{emoji}</span>")
        h.addWidget(emoji_lbl)

        v = QVBoxLayout()
        v.setSpacing(4)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(f"color: {C.get('TEXT')}; font-size: 14px; font-weight: 700;")
        v.addWidget(name_lbl)

        inp_key = QLineEdit()
        inp_key.setPlaceholderText(f"API Key ({placeholder})")
        inp_key.setText(key_val)
        inp_key.setEchoMode(QLineEdit.EchoMode.Password)
        inp_key.setStyleSheet(f"""
            QLineEdit {{
                background: {C.get('BG3')};
                color: {C.get('TEXT')};
                border: 1px solid {C.get('BORDER')};
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
            }}
        """)

        status = QLabel("✅ Connected" if key_val else "⚠️  Not configured")
        status.setStyleSheet(f"color: {'#22c55e' if key_val else C.get('TEXT_MUTED')}; font-size: 11px; font-weight: 600;")
        inp_key.textChanged.connect(lambda t, s=status: s.setText("✅ Connected" if t else "⚠️  Not configured"))
        v.addWidget(inp_key)
        v.addWidget(status)
        h.addLayout(v, 1)
        self._provider_widgets[pid] = {"key_input": inp_key}
        return w

    def _save_providers(self):
        keys = _load_keys()
        for pid, w in self._provider_widgets.items():
            keys[f"{pid}_api_key"] = w["key_input"].text().strip()
        _save_keys(keys)
        self._show_toast("✅ Provider settings saved!")

    # ── Safety Page ───────────────────────────────────────────────────

    def _build_safety_page(self):
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setStyleSheet(f"QScrollArea {{ border: none; background: {C.get('BG')}; }}")
        sw = QWidget()
        v = QVBoxLayout(sw)
        v.setContentsMargins(24, 20, 24, 40)
        v.setSpacing(16)

        v.addWidget(self._section_title("🔒", "Safety & Trust", "Control what ClawOS can do without your approval"))
        v.addWidget(self._spacer(8))

        approval = _load_approval()

        # Approval Mode
        mode_card = self._card([])
        mode_v = QVBoxLayout(mode_card)
        mode_v.setSpacing(10)

        h_mode = QHBoxLayout()
        lbl = QLabel("🔐 Approval Mode")
        lbl.setStyleSheet(f"color: {C.get('TEXT')}; font-size: 14px; font-weight: 700;")
        h_mode.addWidget(lbl)
        h_mode.addStretch()
        mode_combo = QComboBox()
        mode_combo.addItems(["Off", "Manual", "Auto"])
        mode_map = {"manual": 1, "auto": 2, "off": 0}
        mode_combo.setCurrentIndex(mode_map.get(approval.get("approval_mode", "manual"), 1))
        mode_combo.setStyleSheet(f"""
            QComboBox {{
                background: {C.get('BG3')};
                color: {C.get('TEXT')};
                border: 1px solid {C.get('BORDER')};
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
            }}
        """)
        h_mode.addWidget(mode_combo)
        mode_v.addLayout(h_mode)

        mode_desc = QLabel("Manual: confirm each action. Auto: skip trusted actions. Off: no confirmation.")
        mode_desc.setStyleSheet(f"color: {C.get('TEXT_MUTED')}; font-size: 11px;")
        mode_v.addWidget(mode_desc)

        _, timeout_slider, timeout_lbl = self._slider_row("Timeout (seconds):", 15, 180, approval.get("timeout_seconds", 60), "s")
        mode_v.addWidget(timeout_slider)
        self._safety_timeout = timeout_slider
        self._safety_mode_combo = mode_combo

        v.addWidget(mode_card)

        # Secret Redaction
        redact_card = self._card([])
        redact_v = QVBoxLayout(redact_card)
        w_redact, cb_redact = self._toggle_row(
            "🔒 Secret Redaction",
            "Automatically hide API keys, tokens, and passwords in responses and logs",
            approval.get("redact_secrets", True)
        )
        self._redact_cb = cb_redact
        redact_v.addWidget(w_redact)
        v.addWidget(redact_card)

        # Tool Allowlist
        allow_card = self._card([])
        allow_v = QVBoxLayout(allow_card)
        allow_h = QHBoxLayout()
        allow_h.setSpacing(8)
        allow_title = QLabel("🛡️ Command Allowlist")
        allow_title.setStyleSheet(f"color: {C.get('TEXT')}; font-size: 14px; font-weight: 700;")
        allow_h.addWidget(allow_title)
        allow_h.addStretch()
        allow_v.addLayout(allow_h)

        tools_list = [
            ("web_search", "Web Search"),
            ("file_controller", "File Controller"),
            ("browser_control", "Browser Control"),
            ("send_message", "Send Message"),
            ("reminder", "Reminders"),
            ("weather_report", "Weather"),
            ("youtube_video", "YouTube"),
            ("open_app", "Open App"),
            ("screen_process", "Screen Analysis"),
            ("computer_control", "Computer Control"),
            ("code_helper", "Code Helper"),
            ("composio_*", "Composio Tools"),
        ]

        self._tool_cbs = {}
        allowed = approval.get("allowed_tools", [])
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, (tid, tname) in enumerate(tools_list):
            cb = QCheckBox(tname)
            cb.setChecked(tid in allowed or tid.replace("*", "") + "_" in str(allowed) or "composio" in tid)
            cb.setStyleSheet(f"color: {C.get('TEXT_MED')}; font-size: 12px;")
            grid.addWidget(cb, i // 2, i % 2)
            self._tool_cbs[tid] = cb
        allow_v.addLayout(grid)
        v.addWidget(allow_card)

        v.addWidget(self._save_btn(self._save_safety))
        v.addStretch()
        page.setWidget(sw)
        self.pages.addWidget(page)

    def _save_safety(self):
        mode_map = {0: "off", 1: "manual", 2: "auto"}
        data = {
            "approval_mode": mode_map.get(self._safety_mode_combo.currentIndex(), "manual"),
            "timeout_seconds": self._safety_timeout.value(),
            "redact_secrets": self._redact_cb.isChecked(),
            "allowed_tools": [tid for tid, cb in self._tool_cbs.items() if cb.isChecked()],
        }
        _save_approval(data)
        self._show_toast("✅ Safety settings saved!")

    # ── Voice Page ───────────────────────────────────────────────────

    def _build_voice_page(self):
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setStyleSheet(f"QScrollArea {{ border: none; background: {C.get('BG')}; }}")
        sw = QWidget()
        v = QVBoxLayout(sw)
        v.setContentsMargins(24, 20, 24, 40)
        v.setSpacing(16)

        v.addWidget(self._section_title("🔊", "Voice Settings", "Configure text-to-speech and speech-to-text engines"))
        v.addWidget(self._spacer(8))

        settings = _load_settings()

        tts_card = self._card([])
        tts_v = QVBoxLayout(tts_card)
        tts_v.setSpacing(10)
        tts_h = QHBoxLayout()
        lbl = QLabel("🎤 TTS Engine")
        lbl.setStyleSheet(f"color: {C.get('TEXT')}; font-size: 14px; font-weight: 700;")
        tts_h.addWidget(lbl)
        tts_h.addStretch()
        self._tts_combo = QComboBox()
        self._tts_combo.addItems(["Edge TTS (Free)", "ElevenLabs", "Kokoro (Local)", "System Default"])
        current_tts = settings.get("tts_engine", "Edge TTS (Free)")
        idx = self._tts_combo.findText(current_tts)
        if idx >= 0:
            self._tts_combo.setCurrentIndex(idx)
        self._tts_combo.setStyleSheet(f"""
            QComboBox {{
                background: {C.get('BG3')};
                color: {C.get('TEXT')};
                border: 1px solid {C.get('BORDER')};
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                min-width: 160px;
            }}
        """)
        tts_h.addWidget(self._tts_combo)
        tts_v.addLayout(tts_h)

        stt_h = QHBoxLayout()
        lbl2 = QLabel("🎙️ STT Engine")
        lbl2.setStyleSheet(f"color: {C.get('TEXT')}; font-size: 14px; font-weight: 700;")
        stt_h.addWidget(lbl2)
        stt_h.addStretch()
        self._stt_combo = QComboBox()
        self._stt_combo.addItems(["Local Whisper", "Deepgram", "AssemblyAI", "System Default"])
        current_stt = settings.get("stt_engine", "Local Whisper")
        idx2 = self._stt_combo.findText(current_stt)
        if idx2 >= 0:
            self._stt_combo.setCurrentIndex(idx2)
        self._stt_combo.setStyleSheet(f"""
            QComboBox {{
                background: {C.get('BG3')};
                color: {C.get('TEXT')};
                border: 1px solid {C.get('BORDER')};
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                min-width: 160px;
            }}
        """)
        stt_h.addWidget(self._stt_combo)
        tts_v.addLayout(stt_h)

        w_autoplay, cb_autoplay = self._toggle_row(
            "Auto-play voice responses",
            "Automatically speak AI responses when enabled",
            settings.get("voice_auto_play", True)
        )
        self._autoplay_cb = cb_autoplay
        tts_v.addWidget(w_autoplay)
        v.addWidget(tts_card)

        v.addWidget(self._save_btn(self._save_voice))
        v.addStretch()
        page.setWidget(sw)
        self.pages.addWidget(page)

    def _save_voice(self):
        data = _load_settings()
        data["tts_engine"] = self._tts_combo.currentText()
        data["stt_engine"] = self._stt_combo.currentText()
        data["voice_auto_play"] = self._autoplay_cb.isChecked()
        _save_settings(data)
        self._show_toast("✅ Voice settings saved!")

    # ── Memory Page ────────────────────────────────────────────────────

    def _build_memory_page(self):
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setStyleSheet(f"QScrollArea {{ border: none; background: {C.get('BG')}; }}")
        sw = QWidget()
        v = QVBoxLayout(sw)
        v.setContentsMargins(24, 20, 24, 40)
        v.setSpacing(16)

        v.addWidget(self._section_title("🧠", "Memory & Context", "Control how ClawOS remembers things"))
        v.addWidget(self._spacer(8))

        settings = _load_settings()

        _, budget_slider, budget_lbl = self._slider_row("Memory Budget:", 500, 5000, settings.get("memory_budget", 2200), " chars")
        self._budget_slider = budget_slider
        budget_card = self._card([budget_slider, budget_lbl])
        budget_card.layout().setSpacing(8)
        v.addWidget(budget_card)

        _, compress_slider, compress_lbl = self._slider_row(
            "Compression Threshold:", 0.1, 0.9, settings.get("compression_threshold", 0.5), ""
        )
        self._compress_slider = compress_slider
        w_compress, cb_compress = self._toggle_row(
            "🗜️ Auto-Compression",
            "Automatically compress old conversation history to save tokens",
            settings.get("auto_compression", True)
        )
        self._auto_compress_cb = cb_compress
        v.addWidget(w_compress)
        v.addWidget(compress_slider)

        _, protected_slider, protected_lbl = self._slider_row("Protected Recent Messages:", 5, 50, settings.get("protected_recent", 20), " msgs")
        self._protected_slider = protected_slider

        checkpoint_card = self._card([])
        cv = QVBoxLayout(checkpoint_card)
        w_cp, cb_cp = self._toggle_row(
            "💾 File Checkpoints",
            "Save snapshots before major actions — restore if something goes wrong",
            settings.get("file_checkpoints", False)
        )
        self._checkpoint_cb = cb_cp
        cv.addWidget(w_cp)
        _, cp_max_slider, cp_max_lbl = self._slider_row("Max checkpoints:", 3, 20, settings.get("max_checkpoints", 10), "")
        self._cp_max_slider = cp_max_slider
        cv.addWidget(cp_max_slider)
        v.addWidget(checkpoint_card)

        v.addWidget(self._save_btn(self._save_memory))
        v.addStretch()
        page.setWidget(sw)
        self.pages.addWidget(page)

    def _save_memory(self):
        data = _load_settings()
        data["memory_budget"] = self._budget_slider.value()
        data["auto_compression"] = self._auto_compress_cb.isChecked()
        data["compression_threshold"] = self._compress_slider.value()
        data["protected_recent"] = self._protected_slider.value()
        data["file_checkpoints"] = self._checkpoint_cb.isChecked()
        data["max_checkpoints"] = self._cp_max_slider.value()
        _save_settings(data)
        self._show_toast("✅ Memory settings saved!")

    # ── Messaging Page ────────────────────────────────────────────────

    def _build_messaging_page(self):
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setStyleSheet(f"QScrollArea {{ border: none; background: {C.get('BG')}; }}")
        sw = QWidget()
        v = QVBoxLayout(sw)
        v.setContentsMargins(24, 20, 24, 40)
        v.setSpacing(16)

        v.addWidget(self._section_title("📱", "Messaging", "Connect WhatsApp, Email, Telegram and more"))
        v.addWidget(self._spacer(8))

        keys = _load_keys()
        settings = _load_settings()

        # WhatsApp
        wa_card = self._card([])
        wa_v = QVBoxLayout(wa_card)
        wa_v.setSpacing(10)
        wa_title = QLabel("📱 WhatsApp (Evolution API)")
        wa_title.setStyleSheet(f"color: {C.get('TEXT')}; font-size: 14px; font-weight: 700;")
        wa_v.addWidget(wa_title)

        w_url, inp_url = self._input_row("API URL:", "https://your-vps:8081", False, keys.get("evolution_api_url", "http://161.97.173.78.nip.io:8081"))
        wa_v.addWidget(w_url)
        w_key, inp_key = self._input_row("API Key:", "Your Evolution API key", True, keys.get("evolution_api_key", ""))
        wa_v.addWidget(w_key)
        w_inst, inp_inst = self._input_row("Instance Name:", "pulkit-wa-final", False, keys.get("evolution_instance", ""))
        wa_v.addWidget(w_inst)

        self._wa_fields = {"url": inp_url, "key": inp_key, "instance": inp_inst}

        wa_test_btn = QPushButton("🧪 Test Connection")
        wa_test_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.get('BG3')};
                color: {C.get('TEXT')};
                border: 1px solid {C.get('BORDER')};
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 700;
            }}
            QPushButton:hover {{ border-color: {C.get('ACC')}; color: {C.get('ACC')}; }}
        """)
        wa_test_btn.clicked.connect(self._test_wa)
        wa_v.addWidget(wa_test_btn)
        self._wa_status = QLabel("Not tested")
        self._wa_status.setStyleSheet(f"color: {C.get('TEXT_MUTED')}; font-size: 11px;")
        wa_v.addWidget(self._wa_status)
        v.addWidget(wa_card)

        # Email
        email_card = self._card([])
        ev = QVBoxLayout(email_card)
        ev.setSpacing(10)
        em_title = QLabel("📧 Email (SMTP/IMAP)")
        em_title.setStyleSheet(f"color: {C.get('TEXT')}; font-size: 14px; font-weight: 700;")
        ev.addWidget(em_title)
        w_em_host, inp_em = self._input_row("SMTP Host:", "smtp.gmail.com", False, keys.get("smtp_host", ""))
        ev.addWidget(w_em_host)
        w_em_user, inp_eu = self._input_row("Email:", "you@gmail.com", False, keys.get("smtp_user", ""))
        ev.addWidget(w_em_user)
        w_em_pass, inp_ep = self._input_row("App Password:", "xxxx xxxx xxxx xxxx", True, keys.get("smtp_pass", ""))
        ev.addWidget(w_em_pass)
        self._email_fields = {"host": inp_em, "user": inp_eu, "pass": inp_ep}
        v.addWidget(email_card)

        # Telegram
        tg_card = self._card([])
        tg_v = QVBoxLayout(tg_card)
        tg_v.setSpacing(10)
        tg_title = QLabel("✈️ Telegram")
        tg_title.setStyleSheet(f"color: {C.get('TEXT')}; font-size: 14px; font-weight: 700;")
        tg_v.addWidget(tg_title)
        w_tg, inp_tg = self._input_row("Bot Token:", "123456:ABC-...", True, keys.get("telegram_bot_token", ""))
        tg_v.addWidget(w_tg)
        self._tg_fields = {"token": inp_tg}
        v.addWidget(tg_card)

        # GHL
        ghl_card = self._card([])
        gv = QVBoxLayout(ghl_card)
        gv.setSpacing(10)
        ghl_title = QLabel("📞 GoHighLevel (GHL)")
        ghl_title.setStyleSheet(f"color: {C.get('TEXT')}; font-size: 14px; font-weight: 700;")
        gv.addWidget(ghl_title)
        w_loc, inp_loc = self._input_row("Location ID:", "jXjJWNqCoYxnd4outLz1", False, keys.get("ghl_location_id", ""))
        gv.addWidget(w_loc)
        self._ghl_fields = {"location_id": inp_loc}
        v.addWidget(ghl_card)

        v.addWidget(self._save_btn(self._save_messaging))
        v.addStretch()
        page.setWidget(sw)
        self.pages.addWidget(page)

    def _test_wa(self):
        try:
            import requests
            url = self._wa_fields["url"].text().strip()
            key = self._wa_fields["key"].text().strip()
            instance = self._wa_fields["instance"].text().strip()
            resp = requests.get(f"{url}/instance/connectionState/{instance}", headers={"apiKey": key}, timeout=5)
            if resp.status_code == 200:
                self._wa_status.setText("✅ Connected!")
                self._wa_status.setStyleSheet("color: #22c55e; font-size: 11px;")
            else:
                self._wa_status.setText(f"⚠️ Status: {resp.status_code}")
                self._wa_status.setStyleSheet(f"color: {C.get('ORANGE')}; font-size: 11px;")
        except Exception as e:
            self._wa_status.setText(f"❌ Error: {str(e)[:60]}")
            self._wa_status.setStyleSheet(f"color: {C.get('RED')}; font-size: 11px;")

    def _save_messaging(self):
        keys = _load_keys()
        keys["evolution_api_url"] = self._wa_fields["url"].text().strip()
        keys["evolution_api_key"] = self._wa_fields["key"].text().strip()
        keys["evolution_instance"] = self._wa_fields["instance"].text().strip()
        keys["smtp_host"] = self._email_fields["host"].text().strip()
        keys["smtp_user"] = self._email_fields["user"].text().strip()
        keys["smtp_pass"] = self._email_fields["pass"].text().strip()
        keys["telegram_bot_token"] = self._tg_fields["token"].text().strip()
        keys["ghl_location_id"] = self._ghl_fields["location_id"].text().strip()
        _save_keys(keys)
        self._show_toast("✅ Messaging settings saved!")

    # ── MCP Page ──────────────────────────────────────────────────────

    def _build_mcp_page(self):
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setStyleSheet(f"QScrollArea {{ border: none; background: {C.get('BG')}; }}")
        sw = QWidget()
        v = QVBoxLayout(sw)
        v.setContentsMargins(24, 20, 24, 40)
        v.setSpacing(16)

        v.addWidget(self._section_title("🔌", "MCP Servers", "Connect external AI tools and services"))
        v.addWidget(self._spacer(8))

        settings = _load_settings()
        servers = settings.get("mcp_servers", [
            {"name": "Composio", "url": "https://backend.composio.dev/v3/mcp/...", "key": "...", "enabled": True},
        ])

        self._mcp_rows = []
        self._mcp_container = QVBoxLayout()

        for srv in servers:
            row = self._mcp_row(srv)
            self._mcp_container.addWidget(row)

        v.addLayout(self._mcp_container)

        add_btn = QPushButton("➕ Add MCP Server")
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.get('BG3')};
                color: {C.get('TEXT')};
                border: 1px dashed {C.get('BORDER_B')};
                border-radius: 10px;
                padding: 10px;
                font-size: 13px;
            }}
            QPushButton:hover {{ border-color: {C.get('ACC')}; color: {C.get('ACC')}; }}
        """)
        add_btn.clicked.connect(self._add_mcp_server)
        v.addWidget(add_btn)

        v.addWidget(self._save_btn(self._save_mcp))
        v.addStretch()
        page.setWidget(sw)
        self.pages.addWidget(page)

    def _mcp_row(self, srv: dict) -> QFrame:
        f = self._card([])
        h = QHBoxLayout(f)
        h.setSpacing(8)

        name_inp = QLineEdit()
        name_inp.setText(srv.get("name", ""))
        name_inp.setPlaceholderText("Server name")
        name_inp.setStyleSheet(f"background: {C.get('BG3')}; color: {C.get('TEXT')}; border: 1px solid {C.get('BORDER')}; border-radius: 6px; padding: 6px; font-size: 12px;")

        url_inp = QLineEdit()
        url_inp.setText(srv.get("url", ""))
        url_inp.setPlaceholderText("MCP server URL")
        url_inp.setStyleSheet(f"background: {C.get('BG3')}; color: {C.get('TEXT')}; border: 1px solid {C.get('BORDER')}; border-radius: 6px; padding: 6px; font-size: 12px;")

        key_inp = QLineEdit()
        key_inp.setText(srv.get("key", ""))
        key_inp.setPlaceholderText("API key")
        key_inp.setEchoMode(QLineEdit.EchoMode.Password)
        key_inp.setStyleSheet(f"background: {C.get('BG3')}; color: {C.get('TEXT')}; border: 1px solid {C.get('BORDER')}; border-radius: 6px; padding: 6px; font-size: 12px;")

        del_btn = QPushButton("🗑️")
        del_btn.setFixedWidth(36)
        del_btn.setStyleSheet(f"background: transparent; color: {C.get('RED')}; border: 1px solid {C.get('BORDER')}; border-radius: 6px; padding: 4px;")
        del_btn.clicked.connect(lambda: self._delete_mcp_row(f))

        h.addWidget(name_inp, 1)
        h.addWidget(url_inp, 2)
        h.addWidget(key_inp, 2)
        h.addWidget(del_btn)

        self._mcp_rows.append({"frame": f, "name": name_inp, "url": url_inp, "key": key_inp})
        return f

    def _add_mcp_server(self):
        row = self._mcp_row({})
        self._mcp_container.addWidget(row)

    def _delete_mcp_row(self, frame: QFrame):
        frame.deleteLater()
        self._mcp_rows = [r for r in self._mcp_rows if r["frame"] != frame]

    def _save_mcp(self):
        data = _load_settings()
        servers = []
        for r in self._mcp_rows:
            servers.append({
                "name": r["name"].text().strip(),
                "url": r["url"].text().strip(),
                "key": r["key"].text().strip(),
                "enabled": True,
            })
        data["mcp_servers"] = servers
        _save_settings(data)
        self._show_toast("✅ MCP servers saved!")

    # ── Advanced Page ────────────────────────────────────────────────

    def _build_advanced_page(self):
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setStyleSheet(f"QScrollArea {{ border: none; background: {C.get('BG')}; }}")
        sw = QWidget()
        v = QVBoxLayout(sw)
        v.setContentsMargins(24, 20, 24, 40)
        v.setSpacing(16)

        v.addWidget(self._section_title("⚙️", "Advanced", "Fine-tune ClawOS behavior"))
        v.addWidget(self._spacer(8))

        settings = _load_settings()
        approval = _load_approval()

        # Streaming
        stream_card = self._card([])
        sv = QVBoxLayout(stream_card)
        w_stream, cb_stream = self._toggle_row(
            "📡 Text Streaming",
            "Show AI responses as they are generated — character by character",
            approval.get("streaming_enabled", True)
        )
        self._stream_cb = cb_stream
        sv.addWidget(w_stream)
        v.addWidget(stream_card)

        # Subagents
        sub_card = self._card([])
        subv = QVBoxLayout(sub_card)
        subv.setSpacing(10)
        sub_title = QLabel("🔀 Subagent Orchestration")
        sub_title.setStyleSheet(f"color: {C.get('TEXT')}; font-size: 14px; font-weight: 700;")
        subv.addWidget(sub_title)

        _, sub_par, sub_par_lbl = self._slider_row("Max Parallel Subagents:", 1, 5, approval.get("subagent_max_parallel", 3), "")
        _, sub_turn, sub_turn_lbl = self._slider_row("Max Turns per Subagent:", 10, 100, approval.get("subagent_turn_limit", 50), " turns")
        _, sub_tout, sub_tout_lbl = self._slider_row("Subagent Timeout:", 120, 900, approval.get("subagent_timeout", 600), "s")
        self._sub_par = sub_par
        self._sub_turn = sub_turn
        self._sub_tout = sub_tout
        subv.addWidget(sub_par)
        subv.addWidget(sub_turn)
        subv.addWidget(sub_tout)
        v.addWidget(sub_card)

        # Tool enforcement
        enforce_card = self._card([])
        env = QVBoxLayout(enforce_card)
        env.setSpacing(10)
        enforce_h = QHBoxLayout()
        enforce_lbl = QLabel("🎯 Tool-Use Enforcement")
        enforce_lbl.setStyleSheet(f"color: {C.get('TEXT')}; font-size: 14px; font-weight: 700;")
        enforce_h.addWidget(enforce_lbl)
        enforce_h.addStretch()
        self._enforce_combo = QComboBox()
        self._enforce_combo.addItems(["Auto (Recommended)", "Strict", "Off"])
        enforce_map = {"auto": 0, "strict": 1, "off": 2}
        self._enforce_combo.setCurrentIndex(enforce_map.get(approval.get("tool_enforcement", "auto"), 0))
        self._enforce_combo.setStyleSheet(f"background: {C.get('BG3')}; color: {C.get('TEXT')}; border: 1px solid {C.get('BORDER')}; border-radius: 6px; padding: 6px 12px; font-size: 12px;")
        enforce_h.addWidget(self._enforce_combo)
        env.addLayout(enforce_h)
        enforce_desc = QLabel("Auto: agent picks tools. Strict: only allowlisted tools. Off: no restrictions.")
        enforce_desc.setStyleSheet(f"color: {C.get('TEXT_MUTED')}; font-size: 11px;")
        env.addWidget(enforce_desc)
        v.addWidget(enforce_card)

        # Max steps
        _, step_slider, step_lbl = self._slider_row("Max Agent Steps:", 10, 200, approval.get("max_agent_steps", 90), " steps")
        self._step_slider = step_slider
        v.addWidget(step_slider)

        v.addWidget(self._save_btn(self._save_advanced))
        v.addStretch()
        page.setWidget(sw)
        self.pages.addWidget(page)

    def _save_advanced(self):
        approval = _load_approval()
        approval["streaming_enabled"] = self._stream_cb.isChecked()
        approval["subagent_max_parallel"] = self._sub_par.value()
        approval["subagent_turn_limit"] = self._sub_turn.value()
        approval["subagent_timeout"] = self._sub_tout.value()
        approval["tool_enforcement"] = ["auto", "strict", "off"][self._enforce_combo.currentIndex()]
        approval["max_agent_steps"] = self._step_slider.value()
        _save_approval(approval)
        self._show_toast("✅ Advanced settings saved!")

    def _show_toast(self, msg: str):
        from PyQt6.QtWidgets import QLabel, QTimer
        # Simple approach: flash a label in the settings
        for w in self.pages.currentWidget().findChildren(QLabel):
            if "toast" in w.objectName():
                w.setText(msg)
                w.show()
                QTimer.singleShot(2000, w.hide)
                return
        # Fallback: use a message box briefly
        box = QMessageBox(self)
        box.setText(msg)
        box.setStyleSheet(f"QLabel {{ color: {C.get('GREEN')}; font-size: 13px; }} QMessageBox {{ background: {C.get('BG2')}; border: 1px solid {C.get('BORDER')}; }}")
        box.setStandardButtons(QMessageBox.StandardButton.NoButton)
        box.show()
        QTimer.singleShot(1500, box.close)


# ── Main Window ──────────────────────────────────────────────────────

class ClawOSWindow(QMainWindow):
    """Main ClawOS v2 window."""

    # Signals
    streaming_token = pyqtSignal(str)
    response_complete = pyqtSignal()
    approval_request = pyqtSignal(str)
    state_change = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ClawOS — Desktop AI Agent")
        self.setMinimumSize(1100, 700)
        self.resize(1400, 800)

        C.refresh()
        self._theme = "dark"
        self._streaming_enabled = True
        self._processing = False
        self._orb_state = "idle"
        self._settings_modal: Optional[SettingsModal] = None

        # Load settings
        self._settings = _load_settings()
        self._approval = _load_approval()
        self._streaming_enabled = self._approval.get("streaming_enabled", True)

        # Central widget
        central = QWidget()
        central.setStyleSheet(f"background: {C.get('BG')};")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Build panels
        self._top_bar = self._build_top_bar()
        self._left_panel = self._build_left_panel()
        self._center_panel = self._build_center_panel()
        self._right_panel = self._build_right_panel()

        root.addWidget(self._top_bar)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._left_panel, 0)
        body.addWidget(self._center_panel, 1)
        body.addWidget(self._right_panel, 0)
        root.addLayout(body, 1)

        # Connections
        self.streaming_token.connect(self._on_streaming_token)
        self.response_complete.connect(self._on_response_complete)
        self.approval_request.connect(self._on_approval_request)
        self.state_change.connect(self._on_state_change)

        # Orb animation timer
        self._orb_ticker = 0
        self._orb_timer = QTimer(self)
        self._orb_timer.timeout.connect(self._tick_orb)
        self._orb_timer.start(30)

        # System metrics timer
        self._metric_timer = QTimer(self)
        self._metric_timer.timeout.connect(self._update_metrics)
        self._metric_timer.start(2000)
        self._update_metrics()

        # Status check timer
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_status_indicators)
        self._status_timer.start(10000)
        self._update_status_indicators()

    # ── Top Bar ──────────────────────────────────────────────────────

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(56)
        bar.setStyleSheet(f"background: {C.get('BG2')}; border-bottom: 1px solid {C.get('BORDER')};")
        h = QHBoxLayout(bar)
        h.setContentsMargins(16, 0, 16, 0)
        h.setSpacing(12)

        # Brand
        brand = QLabel("🟣  ClawOS")
        brand.setStyleSheet(f"color: {C.get('ACC')}; font-size: 16px; font-weight: 800; letter-spacing: 0.5px;")
        h.addWidget(brand)

        version = QLabel("v2.0")
        version.setStyleSheet(f"color: {C.get('TEXT_MUTED')}; font-size: 10px; padding: 2px 6px; background: {C.get('BG3')}; border-radius: 4px;")
        h.addWidget(version)
        h.addSpacing(16)

        # Status indicators
        self._status_indicators = QHBoxLayout()
        self._status_indicators.setSpacing(8)
        self._status_labels = {}

        services = [
            ("whatsapp", "📱 WhatsApp"),
            ("gmail", "📧 Email"),
            ("ghl", "📞 GHL"),
            ("composio", "🔌 Composio"),
            ("telegram", "✈️ Telegram"),
            ("mcp", "🛠️ MCP"),
        ]
        for sid, label in services:
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {C.get('RED')}; font-size: 8px;")
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {C.get('TEXT_MUTED')}; font-size: 11px;")
            container = QWidget()
            container.setStyleSheet(f"background: {C.get('BG3')}; border-radius: 6px; padding: 4px 8px;")
            ch = QHBoxLayout(container)
            ch.setContentsMargins(4, 2, 4, 2)
            ch.setSpacing(4)
            ch.addWidget(dot)
            ch.addWidget(lbl)
            ch.addStretch()
            self._status_labels[sid] = {"dot": dot, "lbl": lbl}
            self._status_indicators.addWidget(container)

        h.addLayout(self._status_indicators)
        h.addStretch()

        # Theme toggle
        self._theme_btn = QPushButton("🌙")
        self._theme_btn.setFixedSize(36, 36)
        self._theme_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.get('BG3')};
                border: 1px solid {C.get('BORDER')};
                border-radius: 8px;
                font-size: 16px;
            }}
            QPushButton:hover {{ border-color: {C.get('ACC')}; }}
        """)
        self._theme_btn.clicked.connect(self._toggle_theme)
        h.addWidget(self._theme_btn)

        # Settings
        settings_btn = QPushButton("⚙️")
        settings_btn.setFixedSize(36, 36)
        settings_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.get('BG3')};
                border: 1px solid {C.get('BORDER')};
                border-radius: 8px;
                font-size: 16px;
            }}
            QPushButton:hover {{ border-color: {C.get('ACC')}; }}
        """)
        settings_btn.clicked.connect(self._show_settings)
        h.addWidget(settings_btn)

        return bar

    # ── Left Panel ──────────────────────────────────────────────────

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(220)
        panel.setStyleSheet(f"background: {C.get('BG2')}; border-right: 1px solid {C.get('BORDER')};")
        v = QVBoxLayout(panel)
        v.setContentsMargins(8, 12, 8, 12)
        v.setSpacing(8)

        # System metrics
        metrics_lbl = QLabel("📊 SYSTEM")
        metrics_lbl.setStyleSheet(f"color: {C.get('TEXT_MUTED')}; font-size: 10px; font-weight: 700; letter-spacing: 1px;")
        v.addWidget(metrics_lbl)

        self._cpu_bar = self._make_metric_bar("CPU")
        self._mem_bar = self._make_metric_bar("RAM")
        self._gpu_bar = self._make_metric_bar("GPU")
        self._net_bar = self._make_metric_bar("NET")
        v.addWidget(self._cpu_bar)
        v.addWidget(self._mem_bar)
        v.addWidget(self._gpu_bar)
        v.addWidget(self._net_bar)

        v.addWidget(self._make_section_label("⚡ QUICK ACTIONS"))
        v.addLayout(self._quick_actions())

        v.addStretch()

        # Orb state indicator
        self._orb_state_lbl = QLabel("● Idle")
        self._orb_state_lbl.setStyleSheet(f"color: {C.get('GREEN')}; font-size: 11px; font-weight: 600;")
        v.addWidget(self._orb_state_lbl)

        return panel

    def _make_metric_bar(self, label: str) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 2, 0, 2)
        v.setSpacing(2)
        h = QHBoxLayout()
        h.setSpacing(4)
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {C.get('TEXT_MUTED')}; font-size: 10px; min-width: 32px;")
        h.addWidget(lbl)
        bar_bg = QProgressBar()
        bar_bg.setFixedHeight(4)
        bar_bg.setTextVisible(False)
        bar_bg.setStyleSheet(f"""
            QProgressBar {{
                background: {C.get('BAR_BG')};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background: {C.get('ACC')};
                border-radius: 2px;
            }}
        """)
        h.addWidget(bar_bg, 1)
        self_val = QLabel("0%")
        self_val.setStyleSheet(f"color: {C.get('TEXT_MUTED')}; font-size: 9px; min-width: 28px;")
        h.addWidget(self_val)
        v.addLayout(h)
        bar_bg._val_label = self_val
        return bar_bg

    def _make_section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {C.get('TEXT_MUTED')}; font-size: 10px; font-weight: 700; letter-spacing: 1px; padding-top: 8px;")
        return lbl

    def _quick_actions(self) -> QVBoxLayout:
        v = QVBoxLayout()
        v.setSpacing(4)
        actions = [
            ("🔍", "Web Search", self._quick_search),
            ("📧", "Send Email", self._quick_email),
            ("📱", "WhatsApp", self._quick_whatsapp),
            ("📅", "Set Reminder", self._quick_reminder),
            ("🖥️", "Open App", self._quick_open_app),
            ("📊", "Summarize", self._quick_summarize),
        ]
        for icon, name, cb in actions:
            btn = QPushButton(f"{icon}  {name}")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C.get('BG3')};
                    color: {C.get('TEXT_MED')};
                    border: 1px solid {C.get('BORDER')};
                    border-radius: 8px;
                    padding: 8px 12px;
                    text-align: left;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    border-color: {C.get('ACC')};
                    color: {C.get('TEXT')};
                }}
            """)
            btn.clicked.connect(cb)
            v.addWidget(btn)
        return v

    def _quick_search(self):
        self._center_input.setFocus()
        self._center_input.setPlaceholderText("What do you want to search?")

    def _quick_email(self):
        self._center_input.setText("Send an email to...")

    def _quick_whatsapp(self):
        self._center_input.setText("Send a WhatsApp message to...")

    def _quick_reminder(self):
        self._center_input.setText("Set a reminder for...")

    def _quick_open_app(self):
        self._center_input.setText("Open...")

    def _quick_summarize(self):
        self._center_input.setText("Summarize this conversation")

    # ── Center Panel (Chat) ─────────────────────────────────────────

    def _build_center_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f"background: {C.get('BG')};")
        v = QVBoxLayout(panel)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # Message area
        self._chat_scroll = QScrollArea()
        self._chat_scroll.setWidgetResizable(True)
        self._chat_scroll.setStyleSheet(f"""
            QScrollArea {{
                background: {C.get('BG')};
                border: none;
            }}
            QScrollBar:vertical {{
                background: {C.get('SCROLL_BG')};
                width: 6px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {C.get('BORDER_B')};
                border-radius: 3px;
            }}
        """)
        self._chat_container = QWidget()
        self._chat_container.setStyleSheet(f"background: {C.get('BG')};")
        self._chat_layout = QVBoxLayout(self._chat_container)
        self._chat_layout.setContentsMargins(16, 16, 16, 8)
        self._chat_layout.setSpacing(4)
        self._chat_layout.addStretch()

        # Welcome message
        self._add_welcome()

        self._chat_scroll.setWidget(self._chat_container)
        v.addWidget(self._chat_scroll, 1)

        # Input bar
        input_frame = QWidget()
        input_frame.setStyleSheet(f"background: {C.get('BG2')}; border-top: 1px solid {C.get('BORDER')};")
        ih = QHBoxLayout(input_frame)
        ih.setContentsMargins(16, 12, 16, 12)
        ih.setSpacing(10)

        # Orb button
        self._orb_btn = QPushButton("🔮")
        self._orb_btn.setFixedSize(44, 44)
        self._orb_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.get('BG3')};
                border: 2px solid {C.get('ACC')};
                border-radius: 22px;
                font-size: 18px;
            }}
            QPushButton:hover {{
                background: {C.get('ACC_GHO')};
            }}
        """)
        self._orb_btn.clicked.connect(self._toggle_voice)
        ih.addWidget(self._orb_btn)

        # Text input
        self._center_input = QLineEdit()
        self._center_input.setPlaceholderText("Ask ClawOS anything... or click 🔮 to speak")
        self._center_input.setMinimumHeight(44)
        self._center_input.returnPressed.connect(self._send_message)
        self._center_input.setStyleSheet(f"""
            QLineEdit {{
                background: {C.get('BG3')};
                color: {C.get('TEXT')};
                border: 1px solid {C.get('BORDER')};
                border-radius: 22px;
                padding: 0px 16px;
                font-size: 14px;
            }}
            QLineEdit:focus {{
                border-color: {C.get('ACC')};
            }}
            QLineEdit::placeholder {{
                color: {C.get('TEXT_MUTED')};
            }}
        """)
        ih.addWidget(self._center_input, 1)

        # Streaming toggle
        self._stream_toggle = QPushButton("📡")
        self._stream_toggle.setFixedSize(40, 40)
        self._stream_toggle.setCheckable(True)
        self._stream_toggle.setChecked(self._streaming_enabled)
        self._stream_toggle.setStyleSheet(f"""
            QPushButton {{
                background: {'#1a3a2a' if self._streaming_enabled else C.get('BG3')};
                border: 1px solid {'#22c55e' if self._streaming_enabled else C.get('BORDER')};
                border-radius: 8px;
                font-size: 16px;
            }}
            QPushButton:hover {{ border-color: {C.get('ACC')}; }}
        """)
        self._stream_toggle.clicked.connect(self._toggle_streaming)
        ih.addWidget(self._stream_toggle)

        # Send button
        send_btn = QPushButton("➤")
        send_btn.setFixedSize(44, 44)
        send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.get('ACC')};
                color: #fff;
                border: none;
                border-radius: 22px;
                font-size: 18px;
            }}
            QPushButton:hover {{ opacity: 0.85; }}
        """)
        send_btn.clicked.connect(self._send_message)
        ih.addWidget(send_btn)

        v.addWidget(input_frame)
        return panel

    def _add_welcome(self):
        welcome = QLabel()
        welcome.setWordWrap(True)
        welcome.setStyleSheet(f"color: {C.get('TEXT_MUTED')}; font-size: 14px; line-height: 1.6; padding: 20px;")
        welcome.setText(
            f"<span style='font-size:28px'>🟣</span><br>"
            f"<b style='color:{C.get('TEXT')};font-size:18px'>Welcome to ClawOS</b><br><br>"
            f"I'm your desktop AI agent. I can search the web, send messages, manage your calendar, "
            f"control your computer, and connect to WhatsApp, Email, Telegram, and more.<br><br>"
            f"<span style='color:{C.get('TEXT_MED')}'>Try saying:</span><br>"
            f"• \"Search for the latest AI news\"<br>"
            f"• \"Send a WhatsApp message to John\"<br>"
            f"• \"Set a reminder for 3pm\"<br>"
            f"• \"Open Chrome and search for...\""
        )
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, welcome)

    # ── Right Panel ──────────────────────────────────────────────────

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(260)
        panel.setStyleSheet(f"background: {C.get('BG2')}; border-left: 1px solid {C.get('BORDER')};")
        v = QVBoxLayout(panel)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(12)

        # Connected apps
        v.addWidget(self._make_section_label("📱 CONNECTED APPS"))
        apps = [
            ("WhatsApp", "📱", self._check_whatsapp),
            ("Gmail", "📧", self._check_gmail),
            ("GHL", "📞", self._check_ghl),
            ("Telegram", "✈️", self._check_telegram),
        ]
        self._app_rows = {}
        for name, icon, checker in apps:
            row = self._app_status_row(name, icon)
            v.addWidget(row)
            self._app_rows[name] = row

        v.addSpacing(8)
        v.addWidget(self._make_section_label("🧠 AGENT STATUS"))

        # Current state
        self._agent_state = QLabel("● Listening")
        self._agent_state.setStyleSheet(f"color: {C.get('GREEN')}; font-size: 12px; font-weight: 600; padding: 6px 10px; background: {C.get('BG3')}; border-radius: 8px;")
        v.addWidget(self._agent_state)

        # Session info
        session_info = QLabel(f"Session: {datetime.now().strftime('%H:%M')}")
        session_info.setStyleSheet(f"color: {C.get('TEXT_MUTED')}; font-size: 11px;")
        v.addWidget(session_info)

        v.addStretch()

        # Activity log
        v.addWidget(self._make_section_label("📋 ACTIVITY LOG"))
        self._activity_log = QListWidget()
        self._activity_log.setStyleSheet(f"""
            QListWidget {{
                background: {C.get('BG3')};
                color: {C.get('TEXT_MUTED')};
                border: 1px solid {C.get('BORDER')};
                border-radius: 8px;
                font-size: 11px;
                padding: 4px;
            }}
        """)
        self._activity_log.setMaximumHeight(120)
        v.addWidget(self._activity_log)

        return panel

    def _app_status_row(self, name: str, icon: str) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 3, 0, 3)
        h.setSpacing(8)
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {C.get('RED')}; font-size: 10px;")
        lbl = QLabel(f"{icon}  {name}")
        lbl.setStyleSheet(f"color: {C.get('TEXT_MED')}; font-size: 12px;")
        h.addWidget(dot)
        h.addWidget(lbl)
        h.addStretch()
        status = QLabel("Not set")
        status.setStyleSheet(f"color: {C.get('TEXT_MUTED')}; font-size: 10px;")
        h.addWidget(status)
        w._dot = dot
        w._status = status
        return w

    def _check_whatsapp(self):
        pass

    def _check_gmail(self):
        pass

    def _check_ghl(self):
        pass

    def _check_telegram(self):
        pass

    # ── Settings Modal ───────────────────────────────────────────────

    def _show_settings(self):
        if self._settings_modal is None:
            self._settings_modal = SettingsModal(self)
        C.refresh()
        self._settings_modal.show()
        self._settings_modal.raise_()
        self._settings_modal.activateWindow()

    # ── Theme Toggle ─────────────────────────────────────────────────

    def _toggle_theme(self):
        self._theme = "light" if self._theme == "dark" else "dark"
        C._theme = self._theme
        C.refresh()
        self._apply_theme()
        self._theme_btn.setText("☀️" if self._theme == "light" else "🌙")
        if self._settings_modal is not None:
            self._settings_modal.close()
            self._settings_modal = None

    def _apply_theme(self):
        bg = C.get("BG")
        bg2 = C.get("BG2")
        text = C.get("TEXT")
        border = C.get("BORDER")
        acc = C.get("ACC")

        self.setStyleSheet(f"QMainWindow {{ background: {bg}; }}")
        self._top_bar.setStyleSheet(f"background: {bg2}; border-bottom: 1px solid {border};")
        self._left_panel.setStyleSheet(f"background: {bg2}; border-right: 1px solid {border};")
        self._right_panel.setStyleSheet(f"background: {bg2}; border-left: 1px solid {border};")
        self._center_panel.setStyleSheet(f"background: {bg};")
        self._chat_container.setStyleSheet(f"background: {bg};")

        self._center_input.setStyleSheet(f"""
            QLineEdit {{
                background: {C.get('BG3')};
                color: {text};
                border: 1px solid {border};
                border-radius: 22px;
                padding: 0px 16px;
                font-size: 14px;
            }}
            QLineEdit:focus {{ border-color: {acc}; }}
            QLineEdit::placeholder {{ color: {C.get('TEXT_MUTED')}; }}
        """)

    # ── Chat ────────────────────────────────────────────────────────

    def _send_message(self):
        text = self._center_input.text().strip()
        if not text:
            return
        self._center_input.clear()
        self._add_message("user", text)
        self._process_message(text)

    def _add_message(self, role: str, text: str):
        ts = datetime.now().strftime("%H:%M")
        bubble = ChatBubble(role, text, ts)
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, bubble)
        QTimer.singleShot(50, lambda: self._chat_scroll.verticalScrollBar().setValue(
            self._chat_scroll.verticalScrollBar().maximum()
        ))

    def _process_message(self, text: str):
        """Send to executor, stream response back."""
        if self._processing:
            self._add_message("assistant", "⏳ Still working on your previous request...")
            return

        self._processing = True
        self._set_orb_state("processing")

        # Create assistant bubble for streaming
        assistant_bubble = ChatBubble("assistant", "", "")
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, assistant_bubble)
        self._current_bubble = assistant_bubble

        def run():
            try:
                from agent.streaming_executor import StreamingExecutor
                approval = _load_approval()
                executor = StreamingExecutor(approval)

                def on_token(token: str):
                    if self._streaming_enabled:
                        self.streaming_token.emit(token)
                    else:
                        self.streaming_token.emit(token)

                def on_complete(text: str):
                    self.response_complete.emit()

                def on_approval(action: str):
                    self.approval_request.emit(action)

                result = executor.execute(
                    goal=text,
                    on_token=on_token,
                    on_complete=on_complete,
                    on_approval=on_approval,
                )

                if not self._streaming_enabled:
                    self._on_response_complete(result)

            except ImportError:
                # Fallback if streaming_executor doesn't exist yet
                try:
                    from agent.planner import create_plan
                    from integrations.composio_mcp import get_composio, is_configured
                    from memory.profile_manager import format_memory_for_prompt

                    ctx = format_memory_for_prompt(limit=20)
                    cc = get_composio().get_tools_for_prompt() if is_configured() else ""

                    plan = create_plan(text, context=ctx, composio_context=cc)
                    steps = plan.get("steps", [])

                    if steps:
                        response = f"📋 **Plan created** ({len(steps)} steps):\n\n"
                        for s in steps:
                            response += f"• [{s.get('step', '?')}] {s.get('description', '')}\n"
                    else:
                        response = "I'm not sure how to help with that. Could you rephrase?"

                    for ch in response:
                        if self._streaming_enabled:
                            self.streaming_token.emit(ch)
                        else:
                            self.streaming_token.emit(response)
                            break
                    self.response_complete.emit()

                except Exception as e:
                    self.streaming_token.emit(f"⚠️ Error: {str(e)[:100]}")
                    self.response_complete.emit()

            except Exception as e:
                self.streaming_token.emit(f"⚠️ Error: {str(e)[:100]}")
                self.response_complete.emit()

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    def _on_streaming_token(self, token: str):
        if hasattr(self, "_current_bubble") and self._current_bubble:
            self._current_bubble.append(token)
            QTimer.singleShot(10, lambda: self._chat_scroll.verticalScrollBar().setValue(
                self._chat_scroll.verticalScrollBar().maximum()
            ))

    def _on_response_complete(self, text: str = ""):
        self._processing = False
        self._set_orb_state("idle")
        if hasattr(self, "_current_bubble"):
            self._current_bubble._streaming_done = True
            if hasattr(self._current_bubble, "_stream_timer"):
                self._current_bubble._stream_timer.stop()
            self._current_bubble = None
        self._log_activity(f"Response complete")

    def _on_approval_request(self, action: str):
        dialog = ApprovalDialog(action, self)
        result = dialog.get_result()
        # Pass result back to executor via approval state
        self._last_approval_result = result

    def _on_state_change(self, state: str):
        self._set_orb_state(state)

    def _set_orb_state(self, state: str):
        self._orb_state = state
        colors = {
            "idle": C.get("ACC"),
            "listening": C.get("CYAN"),
            "processing": C.get("PURPLE"),
            "speaking": C.get("GREEN"),
        }
        color = colors.get(state, C.get("ACC"))
        self._orb_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.get('BG3')};
                border: 2px solid {color};
                border-radius: 22px;
                font-size: 18px;
            }}
            QPushButton:hover {{
                background: {C.get('ACC_GHO')};
            }}
        """)
        labels = {
            "idle": "● Idle",
            "listening": "● Listening",
            "processing": "● Processing...",
            "speaking": "● Speaking",
        }
        self._orb_state_lbl.setText(labels.get(state, "● Idle"))
        self._orb_state_lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 600;")

    def _toggle_streaming(self):
        self._streaming_enabled = not self._streaming_enabled
        self._approval["streaming_enabled"] = self._streaming_enabled
        _save_approval(self._approval)
        bg_on = "#1a3a2a"
        border_on = "#22c55e"
        self._stream_toggle.setStyleSheet(f"""
            QPushButton {{
                background: {bg_on if self._streaming_enabled else C.get('BG3')};
                border: 1px solid {border_on if self._streaming_enabled else C.get('BORDER')};
                border-radius: 8px;
                font-size: 16px;
            }}
        """)

    def _toggle_voice(self):
        if self._orb_state == "listening":
            self._set_orb_state("idle")
        else:
            self._set_orb_state("listening")
            self._center_input.setFocus()

    def _tick_orb(self):
        self._orb_ticker += 1
        if self._orb_state == "processing" and self._orb_ticker % 4 == 0:
            # Pulse animation during processing
            scale = 1.0 + 0.08 * ((self._orb_ticker // 4) % 2)
            self._orb_btn.setFixedSize(int(44 * scale), int(44 * scale))

    # ── System Metrics ───────────────────────────────────────────────

    def _update_metrics(self):
        try:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory().percent

            for bar, val in [(self._cpu_bar, cpu), (self._mem_bar, mem)]:
                bar.setValue(int(val))
                if hasattr(bar, "_val_label"):
                    bar._val_label.setText(f"{val:.0f}%")

            # GPU
            try:
                import subprocess
                r = subprocess.run(
                    ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0:
                    gpu = float(r.stdout.strip().split("\n")[0])
                    self._gpu_bar.setValue(int(gpu))
                    self._gpu_bar._val_label.setText(f"{gpu:.0f}%")
            except Exception:
                self._gpu_bar._val_label.setText("N/A")

            # Network
            net = psutil.net_io_counters()
            net_mb = (net.bytes_sent + net.bytes_recv) / (1024 * 1024)
            net_pct = min(100, int(net_mb))
            self._net_bar.setValue(net_pct)
            self._net_bar._val_label.setText(f"{net_mb:.0f}MB")

        except Exception:
            pass

    # ── Status Indicators ───────────────────────────────────────────

    def _update_status_indicators(self):
        keys = _load_keys()
        settings = _load_settings()

        checks = {
            "whatsapp": keys.get("evolution_api_key") and keys.get("evolution_instance"),
            "gmail": keys.get("smtp_user") and keys.get("smtp_pass"),
            "ghl": keys.get("ghl_location_id"),
            "composio": bool(keys.get("composio_api_key")),
            "telegram": bool(keys.get("telegram_bot_token")),
            "mcp": bool(settings.get("mcp_servers")),
        }

        green = C.get("GREEN")
        red = C.get("RED")

        for sid, is_connected in checks.items():
            if sid in self._status_labels:
                dot = self._status_labels[sid]["dot"]
                lbl = self._status_labels[sid]["lbl"]
                color = green if is_connected else red
                dot.setStyleSheet(f"color: {color}; font-size: 8px;")
                lbl.setStyleSheet(f"color: {color if is_connected else C.get('TEXT_MUTED')}; font-size: 11px;")

    # ── Activity Log ────────────────────────────────────────────────

    def _log_activity(self, text: str):
        ts = datetime.now().strftime("%H:%M")
        item = QListWidgetItem(f"{ts}  {text}")
        item.setStyleSheet(f"color: {C.get('TEXT_MUTED')}; font-size: 11px; padding: 2px;")
        self._activity_log.insertItem(0, item)
        if self._activity_log.count() > 20:
            self._activity_log.takeItem(self._activity_log.count() - 1)
