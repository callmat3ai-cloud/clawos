# ClawOS — Desktop AI Agent

Voice-first AI desktop assistant with Composio-powered app integrations, persistent memory, multi-profile isolation, and a futuristic dark UI.

```
⚡ ClawOS v1.0
Desktop AI Agent — Voice · Composio · Memory · Profiles · Cron · Skills
```

---

## Features

- **🎤 Voice Input** — Speak naturally, get spoken responses
- **💬 Chat Interface** — Full conversation history with persistent memory
- **🛠️ 500+ App Integrations** — Gmail, Notion, GitHub, Slack, Linear, and more via Composio
- **🧠 Memory** — Remembers context across sessions, auto-extraction
- **👤 User Profiles** — Isolated work/personal/client environments
- **🤖 Agent Modes** — 5 personalities: Professional, Casual, Technical, Creative, Assistant
- **📅 Cron Jobs** — Natural language scheduling ("every morning at 9")
- **🧠 Skill Auto-Discovery** — Learns repeated workflows and creates reusable skills
- **🌙 Futuristic Dark UI** — Cyan/purple cyberpunk aesthetic

---

## Requirements

- macOS (Apple Silicon or Intel)
- Python 3.10+
- Gemini API key (free tier: 1,500 req/min at aistudio.google.com)
- Composio API key (free tier: 20,000 calls/mo at composio.dev)

---

## Install

### Quick Install (one command)

```bash
git clone https://github.com/callmat3ai-cloud/ClawOS.git
cd ClawOS
chmod +x install.sh && ./install.sh
```

### Manual Install

```bash
# 1. Clone
git clone https://github.com/callmat3ai-cloud/ClawOS.git
cd ClawOS

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. Create config
mkdir -p config
cat > config/api_keys.json << 'EOF'
{
  "gemini_api_key": "YOUR_GEMINI_KEY_HERE",
  "composio_api_key": "YOUR_COMPOSIO_KEY_HERE"
}
EOF

# 5. (Optional) Install Composio CLI for OAuth connections
pip install composio-cli
composio login
composio connect gmail github slack

# 6. Run
python main.py
```

---

## Get API Keys

### Gemini (free)
1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Create API key
3. Paste into `config/api_keys.json` under `gemini_api_key`

### Composio (free tier: 20k calls/month)
1. Go to [app.composio.dev/settings/api-keys](https://app.composio.dev/settings/api-keys)
2. Create API key
3. Paste into `config/api_keys.json` under `composio_api_key`

---

## Connect Apps (Composio)

Once you have a Composio API key:

```bash
source venv/bin/activate
composio login
composio connect gmail
composio connect github
composio connect slack
composio connect notion
composio connect linear
```

Available integrations: Gmail, Calendar, Drive, Notion, GitHub, Slack, Discord, Jira, Linear, HubSpot, Airtable, Twitter/X, LinkedIn, Instagram, YouTube, Spotify, Canva, and 500+ more.

---

## Project Structure

```
ClawOS/
├── main.py                     # App entry point (PyQt6)
├── install.sh                  # macOS install script
├── requirements.txt            # Python dependencies
├── config/
│   └── api_keys.json           # API keys (create this)
├── ui/
│   └── futuristic_ui.py        # PyQt6 UI — orb, chat, tools, profiles
├── agent/
│   ├── planner.py              # LLM task decomposition
│   ├── executor.py             # Step-by-step execution + retry
│   └── error_handler.py        # Auto-recovery
├── memory/
│   ├── memory_manager.py       # From Brahma (extraction + compression)
│   ├── profile_manager.py      # Profile isolation + session persistence
│   └── agent_profiles.py      # Agent personality profiles
├── integrations/
│   └── composio_mcp.py        # 500+ app integrations
├── scheduler/
│   └── cron_manager.py         # APScheduler cron jobs
├── skills/
│   └── skill_discovery.py      # Auto-learn workflows
└── actions/                    # 23 action modules (Brahma + cmd_control)
    ├── browser_control.py
    ├── computer_control.py
    ├── cmd_control.py
    ├── file_controller.py
    ├── office_builder.py
    └── ...
```

---

## Agent Modes

Switch between AI personalities from the sidebar:

| Mode | Emoji | Use case |
|------|-------|---------|
| Professional | 💼 | Formal, business, concise |
| Casual | 😎 | Friendly, conversational |
| Technical | ⚙️ | Code-heavy, architecture-minded |
| Creative | 🎨 | Brainstorming, design-focused |
| Assistant | 🤖 | Balanced, general-purpose |

---

## Roadmap

- [x] Composio MCP integration
- [x] Chat interface
- [x] Profile system (user + agent)
- [x] Memory persistence
- [x] Cron scheduler
- [x] Skill auto-discovery
- [x] Futuristic dark UI
- [ ] Voice pipeline — connect meeting_assistant.py
- [ ] macOS .app packaging (PyInstaller)
- [ ] mcporter for n8n/Zapier webhooks
- [ ] Skill marketplace sharing

---

## Troubleshooting

**"PyQt6 not found"**
```bash
pip install PyQt6
```

**"No module named 'google.genai'"**
```bash
pip install google-genai
```

**"No module named 'sounddevice'"**
```bash
pip install sounddevice pyaudio
```

**"Composio API key not working"**
```bash
composio login
composio check
```

---

## License

Proprietary — ClawOps Studio
