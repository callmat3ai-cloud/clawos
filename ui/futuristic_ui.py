"""
ui/futuristic_ui.py — ClawOS Futuristic Dark UI

Voice orb + chat + Composio tools + profiles.
Dark theme with cyan/purple accents.
"""
from __future__ import annotations

import math
import sys
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QTimer,
    QPoint, QRect, QSize, pyqtProperty, pyqtSignal,
)
from PyQt6.QtGui import (
    QColor, QPainter, QPen, QBrush, QRadialGradient,
    QFont, QPalette, QIcon, QTextCursor,
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QListWidget, QListWidgetItem,
    QStackedWidget, QFrame, QSplitter, QScrollArea, QLineEdit,
    QComboBox, QProgressBar, QSystemTrayIcon, QMenu,
)

# ── Color Palette ─────────────────────────────────────────────
C = {
    "bg":          QColor("#020305"),
    "bg_2":        QColor("#0a0d14"),
    "bg_3":        QColor("#111827"),
    "bg_card":     QColor("#0d1117"),
    "border":      QColor("#1e293b"),
    "border_glow": QColor("#00f5ff"),
    "text":        QColor("#e2e8f0"),
    "text_muted":  QColor("#64748b"),
    "cyan":        QColor("#00f5ff"),
    "purple":      QColor("#bf5fff"),
    "green":       QColor("#10b981"),
    "red":         QColor("#ef4444"),
    "amber":       QColor("#f59e0b"),
}

# ── Stylesheet ────────────────────────────────────────────────
STYLESHEET = f"""
* {{
    background-color: {C['bg'].name()};
    color: {C['text'].name()};
    font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 13px;
    selection-background-color: {C['cyan'].name()};
    selection-color: {C['bg'].name()};
}}

QMainWindow {{
    background-color: {C['bg'].name()};
}}

QWidget {{
    background-color: transparent;
}}

QFrame[frameShape="4"] {{  /* HLine */
    background-color: {C['border'].name()};
    max-height: 1px;
    min-height: 1px;
}}

QFrame[frameShape="5"] {{  /* VLine */
    background-color: {C['border'].name()};
    max-width: 1px;
    min-width: 1px;
}}

QTextEdit {{
    background-color: {C['bg_2'].name()};
    border: 1px solid {C['border'].name()};
    border-radius: 8px;
    padding: 10px;
    font-size: 13px;
    color: {C['text'].name()};
}}

QTextEdit:focus {{
    border: 1px solid {C['cyan'].name()};
}}

QLineEdit {{
    background-color: {C['bg_2'].name()};
    border: 1px solid {C['border'].name()};
    border-radius: 20px;
    padding: 10px 16px;
    font-size: 13px;
    color: {C['text'].name()};
}}

QLineEdit:focus {{
    border: 1px solid {C['cyan'].name()};
}}

QPushButton {{
    background-color: {C['bg_3'].name()};
    border: 1px solid {C['border'].name()};
    border-radius: 8px;
    padding: 8px 16px;
    color: {C['text'].name()};
    font-weight: 600;
}}

QPushButton:hover {{
    background-color: {C['cyan'].name()};
    color: {C['bg'].name()};
    border-color: {C['cyan'].name()};
}}

QPushButton:pressed {{
    background-color: {C['purple'].name()};
}}

QPushButton#accentBtn {{
    background-color: {C['cyan'].name()};
    color: {C['bg'].name()};
    border: none;
    font-weight: 700;
}}

QPushButton#accentBtn:hover {{
    background-color: {C['purple'].name()};
}}

QPushButton#dangerBtn {{
    background-color: transparent;
    border: 1px solid {C['red'].name()};
    color: {C['red'].name()};
}}

QPushButton#dangerBtn:hover {{
    background-color: {C['red'].name()};
    color: white;
}}

QListWidget {{
    background-color: {C['bg_2'].name()};
    border: none;
    outline: none;
}}

QListWidget::item {{
    padding: 8px 12px;
    border-radius: 6px;
    margin: 2px 4px;
    color: {C['text'].name()};
}}

QListWidget::item:hover {{
    background-color: {C['bg_3'].name()};
}}

QListWidget::item:selected {{
    background-color: {C['cyan'].name()};
    color: {C['bg'].name()};
}}

QScrollBar:vertical {{
    background-color: {C['bg_2'].name()};
    width: 6px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background-color: {C['border'].name()};
    border-radius: 3px;
    min-height: 40px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {C['cyan'].name()};
}}

QComboBox {{
    background-color: {C['bg_2'].name()};
    border: 1px solid {C['border'].name()};
    border-radius: 6px;
    padding: 6px 10px;
    color: {C['text'].name()};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox QAbstractItemView {{
    background-color: {C['bg_3'].name()};
    selection-background-color: {C['cyan'].name()};
    selection-color: {C['bg'].name()};
}}

QLabel#sectionTitle {{
    color: {C['cyan'].name()};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}}

QLabel#tooltip {{
    color: {C['text_muted'].name()};
    font-size: 11px;
}}

QProgressBar {{
    background-color: {C['bg_2'].name()};
    border: none;
    border-radius: 4px;
    height: 4px;
    text-align: center;
}}

QProgressBar::chunk {{
    background-color: {C['cyan'].name()};
    border-radius: 4px;
}}
"""


# ── Voice Orb Widget ──────────────────────────────────────────

class VoiceOrb(QWidget):
    """
    Animated voice orb — pulsing cyan glow when listening,
    purple glow when processing, static when idle.
    """

    clicked = pyqtSignal()  # Add the missing signal

    def __init__(self, parent=None, size: int = 120):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._state = "idle"    # idle | listening | processing | speaking
        self._phase = 0.0
        self._glow_intensity = 0.0
        self._target_glow = 0.3

        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick)
        self._anim_timer.start(16)  # ~60fps

    def set_state(self, state: str):
        self._state = state
        targets = {"idle": 0.3, "listening": 1.0, "processing": 0.8, "speaking": 0.6}
        self._target_glow = targets.get(state, 0.3)
        self.update()

    def _tick(self):
        self._phase += 0.04
        diff = self._target_glow - self._glow_intensity
        self._glow_intensity += diff * 0.08
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2
        base_r = min(w, h) // 2 - 8
        phase = self._phase
        gi = self._glow_intensity

        # Outer glow ring
        glow_r = base_r + 10 + 8 * math.sin(phase * 2) * gi
        grad = QRadialGradient(cx, cy, glow_r)
        color = self._state_color()
        grad.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), int(80 * gi)))
        grad.setColorAt(0.6, QColor(color.red(), color.green(), color.blue(), int(30 * gi)))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPoint(cx, cy), int(glow_r), int(glow_r))

        # Inner ring
        ring_r = base_r - 4
        painter.setPen(QPen(color, 2))
        painter.setBrush(QBrush(QColor(0, 0, 0, 0)))
        painter.drawEllipse(QPoint(cx, cy), ring_r, ring_r)

        # Inner fill
        fill_r = base_r - 12
        grad2 = QRadialGradient(cx - fill_r//3, cy - fill_r//3, fill_r)
        grad2.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), int(60 * gi)))
        grad2.setColorAt(1.0, QColor(2, 3, 5, 200))
        painter.setBrush(QBrush(grad2))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPoint(cx, cy), fill_r, fill_r)

        # Center dot
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        dot_r = max(4, int(8 * gi))
        painter.drawEllipse(QPoint(cx, cy), dot_r, dot_r)

    def _state_color(self) -> QColor:
        return {
            "idle":      QColor("#334155"),
            "listening": C["cyan"],
            "processing": C["purple"],
            "speaking":  C["green"],
        }.get(self._state, C["text_muted"])

    def mousePressEvent(self, event):
        self.clicked.emit()  # type: ignore[attr-defined]
        super().mousePressEvent(event)

    def sizeHint(self):
        return QSize(120, 120)


# ── Chat Message Widget ────────��───────────────────────────────

class ChatBubble(QWidget):
    """Single chat message bubble."""

    def __init__(self, role: str, content: str, timestamp: str = ""):
        super().__init__()
        self.role = role
        self.content = content

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)

        bubble = QFrame()
        bubble.setObjectName("bubble")
        b_layout = QVBoxLayout(bubble)
        b_layout.setContentsMargins(12, 10, 12, 10)

        # Header
        header = QHBoxLayout()
        sender = QLabel("You" if role == "user" else "ClawOS")
        sender.setStyleSheet(f"color: {C['cyan'].name()}; font-weight: 700; font-size: 11px;")
        if timestamp:
            ts = QLabel(timestamp[:10])
            ts.setStyleSheet(f"color: {C['text_muted'].name()}; font-size: 10px;")
            header.addWidget(ts)
        header.addStretch()
        header.addWidget(sender)
        b_layout.addLayout(header)

        # Content
        msg = QLabel(content)
        msg.setWordWrap(True)
        msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        msg.setStyleSheet(f"""
            color: {C['text'].name()};
            font-size: 13px;
            line-height: 1.5;
            background-color: transparent;
        """)
        b_layout.addWidget(msg)

        # Style based on role
        if role == "user":
            bubble.setStyleSheet(f"""
                QFrame#bubble {{
                    background-color: {C['bg_3'].name()};
                    border: 1px solid {C['border'].name()};
                    border-radius: 12px 12px 4px 12px;
                }}
            """)
            layout.addStretch()
            layout.addWidget(bubble)
        else:
            bubble.setStyleSheet(f"""
                QFrame#bubble {{
                    background-color: {C['bg_card'].name()};
                    border: 1px solid {C['cyan'].name()};
                    border-radius: 12px 12px 12px 4px;
                }}
            """)
            layout.addWidget(bubble)
            layout.addStretch()


# ── Composio Tool Item ────────────────────────────────────────

class ToolItem(QWidget):
    """Single tool in the tools sidebar."""

    def __init__(self, name: str, description: str, category: str):
        super().__init__()
        self.tool_name = name
        self.category = category

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        icon = QLabel(name.split(".")[0].upper()[:2])
        icon.setFixedSize(28, 28)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(f"""
            background-color: {C['cyan'].name()};
            color: {C['bg'].name()};
            border-radius: 6px;
            font-weight: 700;
            font-size: 9px;
        """)
        layout.addWidget(icon)

        info = QVBoxLayout()
        n = QLabel(name.split(".")[-1])
        n.setStyleSheet(f"color: {C['text'].name()}; font-weight: 600; font-size: 12px;")
        d = QLabel(description[:40])
        d.setStyleSheet(f"color: {C['text_muted'].name()}; font-size: 10px;")
        info.addWidget(n)
        info.addWidget(d)
        layout.addLayout(info)


# ── Main Window ───────────────────────────────────────────────

class ClawOSWindow(QMainWindow):
    """Main ClawOS desktop window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ClawOS")
        self.setMinimumSize(1000, 680)
        self.setStyleSheet(STYLESHEET)

        self._profile_manager = None
        self._cron_manager = None
        self._composio = None
        self._current_session_id = None
        self._voice_listening = False

        self._init_ui()
        self._start_new_session()
        self._setup_tray()
        self._load_composio_tools()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar ────────────────────────────────────────────
        sidebar = QFrame()
        sidebar.setFixedWidth(260)
        sidebar.setStyleSheet(f"background-color: {C['bg_2'].name()}; border-right: 1px solid {C['border'].name()};")
        side_layout = QVBoxLayout(sidebar)

        # Logo
        logo = QLabel("⚡ CLAWOS")
        logo.setStyleSheet(f"""
            color: {C['cyan'].name()};
            font-size: 18px;
            font-weight: 800;
            letter-spacing: 3px;
            padding: 16px;
        """)
        side_layout.addWidget(logo)

        # Profile selector
        self.profile_box = QComboBox()
        self.profile_box.setStyleSheet(f"""
            QComboBox {{
                background-color: {C['bg_3'].name()};
                border: 1px solid {C['border'].name()};
                border-radius: 6px;
                padding: 8px 12px;
                margin: 0 12px;
                color: {C['text'].name()};
            }}
        """)
        self._load_profiles()
        self.profile_box.currentTextChanged.connect(self._on_profile_changed)
        side_layout.addWidget(self.profile_box)

        # Agent profile selector
        agent_label = QLabel("🤖 AGENT MODE")
        agent_label.setObjectName("sectionTitle")
        agent_label.setContentsMargins(12, 8, 0, 2)
        side_layout.addWidget(agent_label)

        self.agent_box = QComboBox()
        self.agent_box.setStyleSheet(f"""
            QComboBox {{
                background-color: {C['bg_3'].name()};
                border: 1px solid {C['border'].name()};
                border-radius: 6px;
                padding: 6px 12px;
                margin: 0 12px;
                color: {C['cyan'].name()};
                font-weight: 600;
            }}
        """)
        self._load_agent_profiles()
        self.agent_box.currentIndexChanged.connect(self._on_agent_changed)
        side_layout.addWidget(self.agent_box)

        # Nav
        nav_label = QLabel("NAVIGATION")
        nav_label.setObjectName("sectionTitle")
        nav_label.setContentsMargins(12, 12, 0, 0)
        side_layout.addWidget(nav_label)

        self.nav_list = QListWidget()
        for item in ["💬 Chat", "⚙️ Settings", "🛠️ Tools", "📅 Cron Jobs", "🧠 Skills"]:
            self.nav_list.addItem(item)
        self.nav_list.setFixedHeight(160)
        self.nav_list.currentRowChanged.connect(self._on_nav_changed)
        side_layout.addWidget(self.nav_list)

        # Sessions
        side_layout.addSpacing(8)
        sessions_label = QLabel("SESSIONS")
        sessions_label.setObjectName("sectionTitle")
        sessions_label.setContentsMargins(12, 0, 0, 0)
        side_layout.addWidget(sessions_label)

        self.sessions_list = QListWidget()
        self.sessions_list.setStyleSheet(f"""
            QListWidget {{
                background-color: transparent;
                border: none;
            }}
            QListWidget::item {{
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 12px;
            }}
        """)
        self._load_sessions()
        side_layout.addWidget(self.sessions_list)

        side_layout.addStretch()

        # Version
        ver = QLabel("ClawOS v1.0.0")
        ver.setStyleSheet(f"color: {C['text_muted'].name()}; font-size: 10px; padding: 12px;")
        side_layout.addWidget(ver)

        # ── Main Area ──────────────────────────────────────────
        main_area = QStackedWidget()
        self.main_area = main_area

        # Pages
        self.chat_page = self._build_chat_page()
        self.settings_page = self._build_settings_page()
        self.tools_page = self._build_tools_page()
        self.cron_page = self._build_cron_page()
        self.skills_page = self._build_skills_page()

        main_area.addWidget(self.chat_page)    # 0
        main_area.addWidget(self.settings_page) # 1
        main_area.addWidget(self.tools_page)    # 2
        main_area.addWidget(self.cron_page)     # 3
        main_area.addWidget(self.skills_page)   # 4

        root.addWidget(sidebar)
        root.addWidget(main_area, 1)

    def _build_chat_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        # Chat area
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {C['bg'].name()};
                border: none;
            }}
        """)
        self.chat_container = QWidget()
        self.chat_container.setStyleSheet(f"background-color: {C['bg'].name()};")
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.addStretch()
        self.chat_scroll.setWidget(self.chat_container)
        layout.addWidget(self.chat_scroll, 1)

        # Input area
        input_frame = QFrame()
        input_frame.setStyleSheet(f"""
            background-color: {C['bg_2'].name()};
            border-top: 1px solid {C['border'].name()};
            padding: 12px;
        """)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(16, 12, 16, 12)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type a message or click the orb to speak...")
        self.input_field.setMinimumHeight(40)
        self.input_field.returnPressed.connect(self._send_text_message)
        input_layout.addWidget(self.input_field, 1)

        self.send_btn = QPushButton("➤")
        self.send_btn.setFixedSize(40, 40)
        self.send_btn.setObjectName("accentBtn")
        self.send_btn.clicked.connect(self._send_text_message)
        input_layout.addWidget(self.send_btn)

        # Voice orb (small, in input bar)
        self.voice_orb = VoiceOrb(size=44)
        self.voice_orb.clicked.connect(self._toggle_voice)
        input_layout.addSpacing(8)
        input_layout.addWidget(self.voice_orb)

        layout.addWidget(input_frame)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("⚙️ Settings")
        title.setStyleSheet(f"color: {C['cyan'].name()}; font-size: 20px; font-weight: 800;")
        layout.addWidget(title)
        layout.addSpacing(4)
        desc = QLabel("Configure API keys and integrations")
        desc.setStyleSheet(f"color: {C['text_muted'].name()}; font-size: 12px;")
        layout.addWidget(desc)
        layout.addSpacing(20)

        # Composio key
        comp_label = QLabel("Composio API Key")
        comp_label.setStyleSheet(f"color: {C['text'].name()}; font-weight: 600;")
        layout.addWidget(comp_label)

        comp_row = QHBoxLayout()
        self.composio_key_input = QLineEdit()
        self.composio_key_input.setPlaceholderText("Enter Composio API key...")
        self.composio_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._load_composio_key()
        comp_row.addWidget(self.composio_key_input)

        save_comp = QPushButton("Save")
        save_comp.setObjectName("accentBtn")
        save_comp.clicked.connect(self._save_composio_key)
        comp_row.addWidget(save_comp)
        layout.addLayout(comp_row)

        comp_help = QLabel("Get your free key at composio.dev — 20k tool calls/mo free")
        comp_help.setObjectName("tooltip")
        layout.addWidget(comp_help)

        layout.addSpacing(24)

        # Model preference
        model_label = QLabel("AI Model")
        model_label.setStyleSheet(f"color: {C['text'].name()}; font-weight: 600;")
        layout.addWidget(model_label)

        self.model_box = QComboBox()
        for m in ["gemini-2.5-flash", "gemini-2.5-pro", "openrouter/auto"]:
            self.model_box.addItem(m)
        layout.addWidget(self.model_box)

        layout.addStretch()
        return page

    def _build_tools_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("🛠️ Composio Tools")
        title.setStyleSheet(f"color: {C['cyan'].name()}; font-size: 20px; font-weight: 800;")
        layout.addWidget(title)

        self.tools_status = QLabel("Connect Composio to see 500+ available tools")
        self.tools_status.setObjectName("tooltip")
        layout.addWidget(self.tools_status)
        layout.addSpacing(12)

        self.tools_list = QListWidget()
        layout.addWidget(self.tools_list)
        return page

    def _build_cron_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("📅 Scheduled Tasks")
        title.setStyleSheet(f"color: {C['cyan'].name()}; font-size: 20px; font-weight: 800;")
        layout.addWidget(title)
        desc = QLabel("Natural language scheduling — 'every morning at 9'")
        desc.setObjectName("tooltip")
        layout.addWidget(desc)
        layout.addSpacing(12)

        # Add job form
        form = QHBoxLayout()
        self.cron_input = QLineEdit()
        self.cron_input.setPlaceholderText("every morning at 9 | every 30 minutes | every weekday at 6pm")
        self.cron_action_input = QLineEdit()
        self.cron_action_input.setPlaceholderText("What should it do?")
        form.addWidget(self.cron_input, 1)
        form.addWidget(self.cron_action_input, 1)

        add_cron_btn = QPushButton("+ Schedule")
        add_cron_btn.setObjectName("accentBtn")
        add_cron_btn.clicked.connect(self._add_cron_job)
        form.addWidget(add_cron_btn)
        layout.addLayout(form)

        layout.addSpacing(12)
        self.cron_list = QListWidget()
        layout.addWidget(self.cron_list)
        return page

    def _build_skills_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("🧠 Skills")
        title.setStyleSheet(f"color: {C['purple'].name()}; font-size: 20px; font-weight: 800;")
        layout.addWidget(title)
        desc = QLabel("Auto-discovered skills from your usage patterns")
        desc.setObjectName("tooltip")
        layout.addWidget(desc)
        layout.addSpacing(12)

        self.skills_list = QListWidget()
        layout.addWidget(self.skills_list)
        return page

    # ── Tray ──────────────────────────────────────────────────

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(self)
        tray.setToolTip("ClawOS — Desktop AI Agent")
        menu = QMenu()
        menu.addAction("Show ClawOS").triggered.connect(self.show)
        menu.addAction("Quit").triggered.connect(QApplication.quit)
        tray.setContextMenu(menu)
        tray.show()

    # ── Actions ───────────────────────────────────────────────

    def _load_profiles(self):
        try:
            from memory.profile_manager import list_profiles, get_active_profile
            profiles = list_profiles()
            active = get_active_profile()
            self.profile_box.clear()
            for p in profiles:
                self.profile_box.addItem(p["name"], p["id"])
            idx = self.profile_box.findData(active)
            if idx >= 0:
                self.profile_box.setCurrentIndex(idx)
        except Exception as e:
            print(f"[UI] Profile load error: {e}")

    def _on_profile_changed(self, name: str):
        pid = self.profile_box.currentData()
        if pid:
            from memory.profile_manager import set_active_profile
            set_active_profile(pid)
            self._start_new_session()
            self._load_sessions()

    def _load_agent_profiles(self):
        """Load and display agent profiles in the dropdown."""
        try:
            from memory.agent_profiles import list_agent_profiles, get_active_agent
            agents = list_agent_profiles()
            active = get_active_agent()
            self.agent_box.clear()
            for a in agents:
                label = f"{a['emoji']} {a['name']}"
                self.agent_box.addItem(label, a["id"])
            idx = self.agent_box.findData(active)
            if idx >= 0:
                self.agent_box.setCurrentIndex(idx)
        except Exception as e:
            print(f"[UI] Agent profile load error: {e}")

    def _on_agent_changed(self, index: int):
        """Switch agent profile when user picks a different one."""
        if index < 0:
            return
        agent_id = self.agent_box.currentData()
        if agent_id:
            try:
                from memory.agent_profiles import set_active_agent, get_system_prompt_for_agent
                set_active_agent(agent_id)
                prompt = get_system_prompt_for_agent(agent_id)
                # Update window title with agent mode
                agent_label = self.agent_box.currentText()
                self.statusBar().showMessage(f"Switched to {agent_label}", 3000)
            except Exception as e:
                print(f"[UI] Agent switch error: {e}")

    def _load_sessions(self):
        try:
            from memory.profile_manager import get_sessions
            sessions = get_sessions()
            self.sessions_list.clear()
            for s in sessions:
                item = QListWidgetItem(f"💬 {s['title'] or 'New Chat'}")
                item.setData(Qt.ItemDataRole.UserRole, s["id"])
                self.sessions_list.addItem(item)
        except Exception:
            pass

    def _start_new_session(self, title: str = "New Chat") -> str:
        try:
            from memory.profile_manager import create_session
            sid = create_session(title)
            self._current_session_id = sid
            return sid
        except Exception:
            import uuid
            sid = uuid.uuid4().hex[:12]
            self._current_session_id = sid
            return sid

    def _load_composio_key(self):
        try:
            from integrations.composio_mcp import get_api_key
            key = get_api_key()
            if key:
                self.composio_key_input.setText(key)
        except Exception:
            pass

    def _save_composio_key(self):
        key = self.composio_key_input.text().strip()
        if not key:
            return
        try:
            from memory.profile_manager import _base_dir
            import json
            config_file = _base_dir() / "config" / "api_keys.json"
            config_file.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            if config_file.exists():
                data = json.loads(config_file.read_text(encoding="utf-8"))
            data["composio_api_key"] = key
            config_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

            # Reload Composio
            global _composio
            _composio = None
            from integrations.composio_mcp import get_composio
            get_composio()
            self._load_composio_tools()
        except Exception as e:
            print(f"[UI] Composio save error: {e}")

    def _load_composio_tools(self):
        try:
            from integrations.composio_mcp import get_composio
            composio = get_composio()
            if composio.connected:
                tools = composio.list_tools()
                self.tools_list.clear()
                cats: dict[str, list] = {}
                for t in tools:
                    cat = t.get("category", "Other")
                    cats.setdefault(cat, []).append(t)
                for cat, items in sorted(cats.items()):
                    self.tools_list.addItem(f"── {cat} ({len(items)}) ──")
                    for item in items:
                        self.tools_list.addItem(f"  {item['name']}: {item.get('description', '')}")
                self.tools_status.setText(f"✅ {len(tools)} tools available")
        except Exception as e:
            self.tools_status.setText(f"⚠️ Error loading tools: {e}")

    def _on_nav_changed(self, index: int):
        self.main_area.setCurrentIndex(index)

    def _send_text_message(self):
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()
        self._add_message("user", text)
        self._process_user_message(text)

    def _toggle_voice(self):
        self._voice_listening = not self._voice_listening
        self.voice_orb.set_state("listening" if self._voice_listening else "idle")
        if self._voice_listening:
            self._start_voice_listening()
        else:
            self._stop_voice_listening()

    def _start_voice_listening(self):
        # TODO: connect to Brahma's meeting_assistant.py voice pipeline
        self.statusBar().showMessage("🎤 Voice listening started...", 2000)

    def _stop_voice_listening(self):
        # TODO: stop voice recording
        self.statusBar().showMessage("🎤 Voice listening stopped", 2000)

    def _process_user_message(self, text: str):
        """Send user message to executor and display response."""
        if not text.strip():
            return

        # Show thinking state
        self.voice_orb.set_state("processing")

        # Process in a background thread to avoid blocking UI
        from PyQt6.QtCore import QThread
        class ProcessThread(QThread):
            def __init__(self, window, text):
                super().__init__()
                self.window = window
                self.text = text
                self.result = None
                self.error = None

            def run(self):
                try:
                    from agent.executor import AgentExecutor
                    from memory.profile_manager import format_memory_for_prompt
                    from memory.agent_profiles import get_active_agent
                    from integrations.composio_mcp import get_composio, is_configured as _comp_config

                    ctx = format_memory_for_prompt(limit=20)
                    cc = get_composio().get_tools_for_prompt() if _comp_config() else ""
                    agent_id = get_active_agent()

                    executor = AgentExecutor()
                    result = executor.execute(
                        goal=self.text,
                        memory_context=ctx,
                        composio_context=cc,
                        agent_profile_id=agent_id,
                    )
                    self.result = result
                except Exception as e:
                    self.error = str(e)

        def on_done(thread: ProcessThread):
            self.voice_orb.set_state("idle")
            if thread.error:
                self._add_message("assistant", f"⚠️ Error: {thread.error[:200]}")
            elif thread.result:
                r = thread.result
                # Save messages
                if self._current_session_id:
                    try:
                        from memory.profile_manager import save_message
                        save_message(self._current_session_id, "user", text)
                        save_message(self._current_session_id, "assistant", r.text)
                    except Exception:
                        pass
                # Record action sequence for skill discovery
                try:
                    from skills.skill_discovery import record_action_sequence
                    if r.actions_used:
                        record_action_sequence(r.actions_used, text[:100])
                except Exception:
                    pass
                # Display
                self._add_message("assistant", r.text or "Done.")
                if r.action_results:
                    for ar in r.action_results:
                        self._add_message("assistant", f"🔧 {ar}")
            thread.deleteLater()

        thread = ProcessThread(self, text)
        thread.finished.connect(lambda: on_done(thread))
        thread.start()

    def _add_message(self, role: str, content: str):
        from datetime import datetime as dt
        ts = dt.now().strftime("%H:%M")
        bubble = ChatBubble(role, content, ts)
        # Insert before the stretch
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble)
        # Scroll to bottom
        QTimer.singleShot(50, lambda: self.chat_scroll.verticalScrollBar().setValue(
            self.chat_scroll.verticalScrollBar().maximum()
        ))
        # Save to DB
        if self._current_session_id:
            try:
                from memory.profile_manager import save_message
                save_message(self._current_session_id, role, content)
            except Exception:
                pass

    def _add_cron_job(self):
        cron_text = self.cron_input.text().strip()
        action = self.cron_action_input.text().strip()
        if not cron_text or not action:
            return
        try:
            from scheduler.cron_manager import get_cron_manager
            result = get_cron_manager().schedule_job(
                name=action[:40],
                natural_cron=cron_text,
                action=action,
            )
            self.cron_input.clear()
            self.cron_action_input.clear()
            self._load_cron_jobs()
        except Exception as e:
            print(f"[UI] Cron error: {e}")

    def _load_cron_jobs(self):
        try:
            from scheduler.cron_manager import get_cron_manager
            jobs = get_cron_manager().list_jobs()
            self.cron_list.clear()
            for j in jobs:
                status = "✅" if j["enabled"] else "⏸️"
                self.cron_list.addItem(f"{status} {j['name']} ({j['cron_expr']})")
        except Exception:
            pass
