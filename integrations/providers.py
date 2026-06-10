"""
integrations/providers.py — ClawOS LLM Provider System

Supports:
- Built-in providers with per-model pricing (OpenAI, Anthropic, Gemini, etc.)
- Custom providers (any OpenAI-compatible endpoint — like Hermes custom_providers)
- Per-provider base_url override (e.g. codemax.pro as Anthropic backend)
- Default model selection per provider
- Streaming via SSE
- API key per provider from config

Reference: Hermes config.yaml — model.provider / model.base_url / model.default pattern
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger("providers")


def _base_dir() -> Path:
    import sys
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
KEYS_FILE = CONFIG_DIR / "api_keys.json"
SETTINGS_FILE = CONFIG_DIR / "app_settings_v2.json"


def _load_keys() -> dict:
    try:
        return json.loads(KEYS_FILE.read_text())
    except FileNotFoundError:
        return {}


def _load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text())
    except FileNotFoundError:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# BUILT-IN PROVIDER REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

PROVIDERS = {
    # ── OpenAI ──────────────────────────────────────────────────────────────
    "openai": {
        "name": "OpenAI",
        "emoji": "🤖",
        "api_base": "https://api.openai.com/v1",
        "auth_header": "Bearer",
        "env_key": "OPENAI_API_KEY",
        "default_model": "gpt-4o",
        "supports_streaming": True,
        "supports_vision": True,
        "models": [
            {"id": "gpt-4o",          "name": "GPT-4o",            "context": 128000, "input": 2.50,  "output": 10.00},
            {"id": "gpt-4o-mini",     "name": "GPT-4o Mini",        "context": 128000, "input": 0.15,   "output": 0.60},
            {"id": "gpt-4.5-preview",  "name": "GPT-4.5 Preview",    "context": 128000, "input": 75.00,  "output": 150.00},
            {"id": "o1-preview",       "name": "o1 Preview",         "context": 128000, "input": 15.00,  "output": 60.00},
            {"id": "o1-mini",         "name": "o1 Mini",           "context": 65536,  "input": 3.00,   "output": 12.00},
        ],
    },

    # ── Anthropic ───────────────────────────────────────────────────────────
    "anthropic": {
        "name": "Anthropic",
        "emoji": "🧠",
        "api_base": "https://api.anthropic.com/v1",
        "auth_header": "x-api-key",
        "env_key": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-6",
        "supports_streaming": True,
        "supports_vision": True,
        "models": [
            {"id": "claude-opus-4-7",    "name": "Claude Opus 4.7",    "context": 200000, "input": 3.00,  "output": 15.00},
            {"id": "claude-sonnet-4-6",  "name": "Claude Sonnet 4.6",  "context": 200000, "input": 3.00,  "output": 15.00},
            {"id": "claude-3-5-haiku",   "name": "Claude 3.5 Haiku",   "context": 200000, "input": 0.80,  "output": 4.00},
            {"id": "claude-3-opus",      "name": "Claude 3 Opus",      "context": 200000, "input": 15.00, "output": 75.00},
            {"id": "claude-3-sonnet",    "name": "Claude 3 Sonnet",    "context": 200000, "input": 3.00,  "output": 15.00},
        ],
    },

    # ── Google Gemini ──────────────────────────────────────────────────────
    "gemini": {
        "name": "Google Gemini",
        "emoji": "✨",
        "api_base": "https://generativelanguage.googleapis.com/v1beta",
        "auth_header": "Bearer",   # key goes in URL param
        "env_key": "GEMINI_API_KEY",
        "default_model": "gemini-2.0-flash",
        "supports_streaming": True,
        "supports_vision": True,
        "models": [
            {"id": "gemini-2.5-pro",    "name": "Gemini 2.5 Pro",    "context": 2000000, "input": 1.25,  "output": 10.00},
            {"id": "gemini-2.5-flash",  "name": "Gemini 2.5 Flash",  "context": 1000000, "input": 0.075, "output": 0.30},
            {"id": "gemini-2.0-flash",  "name": "Gemini 2.0 Flash",  "context": 1000000, "input": 0.10,  "output": 0.40},
            {"id": "gemini-1.5-pro",    "name": "Gemini 1.5 Pro",    "context": 2000000, "input": 1.25,  "output": 10.00},
            {"id": "gemini-1.5-flash",  "name": "Gemini 1.5 Flash",  "context": 1000000, "input": 0.075, "output": 0.30},
        ],
    },

    # ── Groq ───────────────────────────────────────────────────────────────
    "groq": {
        "name": "Groq",
        "emoji": "⚡",
        "api_base": "https://api.groq.com/openai/v1",
        "auth_header": "Bearer",
        "env_key": "GROQ_API_KEY",
        "default_model": "llama-3.3-70b-versatile",
        "supports_streaming": True,
        "supports_vision": False,
        "models": [
            {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B", "context": 128000, "input": 0.59, "output": 2.40},
            {"id": "llama-3.1-8b-instant",    "name": "Llama 3.1 8B",  "context": 128000, "input": 0.05, "output": 0.08},
            {"id": "mixtral-8x7b-32768",      "name": "Mixtral 8x7B",  "context": 32000,  "input": 0.24, "output": 0.24},
            {"id": "gemma2-9b-it",            "name": "Gemma 2 9B",    "context": 8192,   "input": 0.20, "output": 0.20},
        ],
    },

    # ── OpenRouter ────────────────────────────────────────────────────────
    "openrouter": {
        "name": "OpenRouter",
        "emoji": "🌐",
        "api_base": "https://openrouter.ai/api/v1",
        "auth_header": "Bearer",
        "env_key": "OPENROUTER_API_KEY",
        "default_model": "anthropic/claude-sonnet-4-6",
        "supports_streaming": True,
        "supports_vision": True,
        "models": [
            {"id": "anthropic/claude-sonnet-4-6",  "name": "Claude Sonnet 4.6",  "context": 200000, "input": 3.00,  "output": 15.00},
            {"id": "openai/gpt-4o",               "name": "GPT-4o",              "context": 128000, "input": 2.50,  "output": 10.00},
            {"id": "google/gemini-2.5-pro",       "name": "Gemini 2.5 Pro",     "context": 2000000,"input": 2.50,  "output": 10.00},
            {"id": "meta-llama/llama-3.3-70b",    "name": "Llama 3.3 70B",     "context": 128000, "input": 0.65,  "output": 2.75},
            {"id": "deepseek/deepseek-chat-v3",    "name": "DeepSeek V3",        "context": 64000,  "input": 0.27,  "output": 1.10},
        ],
    },

    # ── Perplexity ────────────────────────────────────────────────────────
    "perplexity": {
        "name": "Perplexity",
        "emoji": "🔍",
        "api_base": "https://api.perplexity.ai",
        "auth_header": "Bearer",
        "env_key": "PERPLEXITY_API_KEY",
        "default_model": "sonar-pro",
        "supports_streaming": True,
        "supports_vision": True,
        "models": [
            {"id": "sonar-pro",             "name": "Sonar Pro",           "context": 128000, "input": 3.00,  "output": 15.00},
            {"id": "sonar",                 "name": "Sonar",                 "context": 127000, "input": 0.00,  "output": 1.00},
            {"id": "sonar-reasoning-pro",   "name": "Sonar Reasoning Pro",  "context": 128000, "input": 5.00,  "output": 20.00},
            {"id": "sonar-reasoning",       "name": "Sonar Reasoning",      "context": 128000, "input": 1.00,  "output": 5.00},
        ],
    },

    # ── DeepSeek ──────────────────────────────────────────────────────────
    "deepseek": {
        "name": "DeepSeek",
        "emoji": "🔮",
        "api_base": "https://api.deepseek.com/v1",
        "auth_header": "Bearer",
        "env_key": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-chat",
        "supports_streaming": True,
        "supports_vision": False,
        "models": [
            {"id": "deepseek-chat",    "name": "DeepSeek Chat V3",  "context": 64000, "input": 0.27, "output": 1.10},
            {"id": "deepseek-coder",  "name": "DeepSeek Coder",    "context": 64000, "input": 0.14, "output": 0.28},
            {"id": "deepseek-reasoner","name": "DeepSeek Reasoner", "context": 64000, "input": 0.55, "output": 2.19},
        ],
    },

    # ── Grok / xAI ────────────────────────────────────────────────────────
    "xai": {
        "name": "xAI (Grok)",
        "emoji": "🤖",
        "api_base": "https://api.x.ai/v1",
        "auth_header": "Bearer",
        "env_key": "XAI_API_KEY",
        "default_model": "grok-3",
        "supports_streaming": True,
        "supports_vision": True,
        "models": [
            {"id": "grok-3",       "name": "Grok 3",      "context": 131072, "input": 5.00, "output": 15.00},
            {"id": "grok-2-1212",  "name": "Grok 2",      "context": 131072, "input": 2.00, "output": 10.00},
            {"id": "grok-beta",     "name": "Grok Beta",   "context": 131072, "input": 5.00, "output": 15.00},
        ],
    },

    # ── Ollama (Local) ────────────────────────────────────────────────────
    "ollama": {
        "name": "Ollama (Local)",
        "emoji": "🏠",
        "api_base": "http://localhost:11434/v1",
        "auth_header": "Bearer",
        "env_key": "OLLAMA_API_KEY",
        "default_model": "llama3.3:70b",
        "supports_streaming": True,
        "supports_vision": False,
        "models": [
            {"id": "llama3.3:70b",     "name": "Llama 3.3 70B",    "context": 128000, "input": 0.00, "output": 0.00},
            {"id": "llama3.2:3b",      "name": "Llama 3.2 3B",     "context": 32000,  "input": 0.00, "output": 0.00},
            {"id": "qwen2.5:72b",      "name": "Qwen 2.5 72B",     "context": 32000,  "input": 0.00, "output": 0.00},
            {"id": "codestral:22b",    "name": "Codestral 22B",    "context": 32000,  "input": 0.00, "output": 0.00},
            {"id": "mistral-nemo:12b", "name": "Mistral Nemo 12B", "context": 128000, "input": 0.00, "output": 0.00},
            {"id": "gemma2:27b",       "name": "Gemma 2 27B",       "context": 8192,   "input": 0.00, "output": 0.00},
            {"id": "deepseek-coder-v2","name": "DeepSeek Coder V2", "context": 32000,  "input": 0.00, "output": 0.00},
            {"id": "nomic-embed-text",  "name": "Nomic Embed Text",  "context": 8192,   "input": 0.00, "output": 0.00},
        ],
    },

    # ── Mistral ──────────────────────────────────────────────────────────
    "mistral": {
        "name": "Mistral",
        "emoji": "🌊",
        "api_base": "https://api.mistral.ai/v1",
        "auth_header": "Bearer",
        "env_key": "MISTRAL_API_KEY",
        "default_model": "mistral-nemo",
        "supports_streaming": True,
        "supports_vision": False,
        "models": [
            {"id": "mistral-nemo",     "name": "Mistral Nemo",    "context": 128000, "input": 0.15, "output": 0.15},
            {"id": "mistral-small",    "name": "Mistral Small",   "context": 128000, "input": 0.30, "output": 0.90},
            {"id": "codestral",        "name": "Codestral",       "context": 32000,  "input": 0.30, "output": 0.90},
            {"id": "open-mistral-7b",  "name": "Mistral 7B",      "context": 32000,  "input": 0.25, "output": 0.25},
        ],
    },

    # ── Together AI ───────────────────────────────────────────────────────
    "together": {
        "name": "Together AI",
        "emoji": "🚀",
        "api_base": "https://api.together.xyz/v1",
        "auth_header": "Bearer",
        "env_key": "TOGETHER_API_KEY",
        "default_model": "meta-llama/Llama-3.3-70B-Instruct",
        "supports_streaming": True,
        "supports_vision": False,
        "models": [
            {"id": "meta-llama/Llama-3.3-70B-Instruct",     "name": "Llama 3.3 70B",   "context": 128000, "input": 0.88, "output": 0.88},
            {"id": "deepseek-ai/DeepSeek-V3",                 "name": "DeepSeek V3",      "context": 64000,  "input": 0.27, "output": 1.10},
            {"id": "Qwen/Qwen2.5-72B-Instruct",               "name": "Qwen 2.5 72B",    "context": 32000,  "input": 0.27, "output": 0.27},
            {"id": "mistralai/Mixtral-8x22B-Instruct-v0.1",  "name": "Mixtral 8x22B",    "context": 64000,  "input": 0.65, "output": 2.40},
        ],
    },

    # ── Cohere ─────────────────────────────────────────────────────────────
    "cohere": {
        "name": "Cohere",
        "emoji": "🧩",
        "api_base": "https://api.cohere.ai/v2",
        "auth_header": "Bearer",
        "env_key": "COHERE_API_KEY",
        "default_model": "command-r-plus",
        "supports_streaming": True,
        "supports_vision": False,
        "models": [
            {"id": "command-a-plus",  "name": "Command A+",  "context": 200000, "input": 3.00, "output": 15.00},
            {"id": "command-r-plus",  "name": "Command R+",  "context": 128000, "input": 3.00, "output": 15.00},
            {"id": "command-r",        "name": "Command R",   "context": 128000, "input": 0.50, "output": 1.50},
        ],
    },

    # ── CodeMax (ClawOps) ─────────────────────────────────────────────────
    # Points to codemax.pro — OpenAI-compatible with Claude models
    "codemax": {
        "name": "CodeMax",
        "emoji": "⚡",
        "api_base": "https://api.codemax.pro/v1",
        "auth_header": "Bearer",
        "env_key": "CODEMAX_API_KEY",
        "default_model": "claude-sonnet-4-6",
        "supports_streaming": True,
        "supports_vision": True,
        "models": [
            {"id": "claude-opus-4-7",    "name": "Claude Opus 4.7",   "context": 200000, "input": 3.00,  "output": 15.00},
            {"id": "claude-sonnet-4-6",  "name": "Claude Sonnet 4.6",  "context": 200000, "input": 3.00,  "output": 15.00},
            {"id": "claude-3-5-haiku",   "name": "Claude 3.5 Haiku",   "context": 200000, "input": 0.80,  "output": 4.00},
            {"id": "gpt-4o",            "name": "GPT-4o",             "context": 128000, "input": 2.50,  "output": 10.00},
            {"id": "gpt-4o-mini",        "name": "GPT-4o Mini",        "context": 128000, "input": 0.15,  "output": 0.60},
        ],
    },

    # ── Nous Research ─────────────────────────────────────────────────────
    "nous": {
        "name": "Nous Portal",
        "emoji": "🌀",
        "api_base": "https://api.nousresearch.com/v1",
        "auth_header": "Bearer",
        "env_key": "NOUS_API_KEY",
        "default_model": "claude-sonnet-4-6",
        "supports_streaming": True,
        "supports_vision": True,
        "models": [
            {"id": "claude-sonnet-4-6",  "name": "Claude Sonnet 4.6",  "context": 200000, "input": 3.00, "output": 15.00},
            {"id": "claude-opus-4-7",    "name": "Claude Opus 4.7",    "context": 200000, "input": 3.00, "output": 15.00},
        ],
    },

    # ── NVIDIA NIM ────────────────────────────────────────────────────────
    "nvidia": {
        "name": "NVIDIA NIM",
        "emoji": "🎮",
        "api_base": "https://integrate.api.nvidia.com/v1",
        "auth_header": "Bearer",
        "env_key": "NVIDIA_API_KEY",
        "default_model": "moonshotai/kimi-k2-thinking",
        "supports_streaming": True,
        "supports_vision": False,
        "models": [
            {"id": "moonshotai/kimi-k2-thinking",  "name": "Kimi K2 Thinking", "context": 32000, "input": 0.00, "output": 0.00},
            {"id": "nvidia/llama-3.3-nemotron",   "name": "Llama 3.3 Nemotron","context": 128000,"input": 0.00, "output": 0.00},
            {"id": "meta/llama-3.1-405b-instruct", "name": "Llama 3.1 405B",   "context": 128000,"input": 0.00, "output": 0.00},
        ],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM PROVIDERS  (like Hermes custom_providers)
# User can add any OpenAI-compatible endpoint with their own models
# ─────────────────────────────────────────────────────────────────────────────

def get_custom_providers() -> dict:
    """Load custom providers from settings."""
    settings = _load_settings()
    return settings.get("custom_providers", {})


def add_custom_provider(name: str, api_base: str, api_key: str, default_model: str = "", models: list = None) -> bool:
    """Add a custom provider at runtime. Saves to settings."""
    settings = _load_settings()
    if "custom_providers" not in settings:
        settings["custom_providers"] = {}

    custom = {
        "name": name,
        "emoji": "🔧",
        "api_base": api_base.rstrip("/"),
        "auth_header": "Bearer",
        "env_key": f"CUSTOM_{name.upper().replace(' ', '_')}_API_KEY",
        "default_model": default_model,
        "supports_streaming": True,
        "supports_vision": False,
        "custom": True,
        "models": models or [{"id": default_model or "model", "name": name, "context": 128000, "input": 0, "output": 0}],
    }

    settings["custom_providers"][name.lower().replace(" ", "_")] = custom
    _save_settings(settings)
    log.info(f"Custom provider added: {name}")
    return True


def get_all_providers() -> dict:
    """Return all providers including custom ones."""
    all_providers = dict(PROVIDERS)
    all_providers.update(get_custom_providers())
    return all_providers


# ─────────────────────────────────────────────────────────────────────────────
# API KEY MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

# Map provider name → config key for API key lookup
_KEY_MAP = {
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "gemini": "gemini_api_key",
    "groq": "groq_api_key",
    "openrouter": "openrouter_api_key",
    "perplexity": "perplexity_api_key",
    "deepseek": "deepseek_api_key",
    "xai": "xai_api_key",
    "ollama": "ollama_api_key",
    "mistral": "mistral_api_key",
    "together": "together_api_key",
    "cohere": "cohere_api_key",
    "codemax": "codemax_api_key",
    "nous": "nous_api_key",
    "nvidia": "nvidia_api_key",
}


def get_api_key(provider: str) -> str:
    """Get API key for a provider — config file first, then env var."""
    keys = _load_keys()
    config_key = _KEY_MAP.get(provider, f"{provider}_api_key")

    key = keys.get(config_key, "")
    if key:
        return key

    # Fall back to env var
    env_key = PROVIDERS.get(provider, {}).get("env_key", "")
    if env_key:
        return os.environ.get(env_key, "")

    return ""


def get_base_url(provider: str) -> str:
    """Get base URL for a provider — allows override via settings."""
    settings = _load_settings()

    # Check settings for per-provider override
    base_urls = settings.get("provider_base_urls", {})
    if provider in base_urls:
        return base_urls[provider]

    # Check custom_providers
    custom = get_custom_providers()
    if provider in custom:
        return custom[provider].get("api_base", PROVIDERS.get(provider, {}).get("api_base", ""))

    return PROVIDERS.get(provider, {}).get("api_base", "")


def get_default_model(provider: str) -> str:
    """Get default model for a provider."""
    # Check custom providers first
    custom = get_custom_providers()
    if provider in custom:
        return custom[provider].get("default_model", "")

    return PROVIDERS.get(provider, {}).get("default_model", "")


def is_provider_configured(provider: str) -> bool:
    """Check if a provider has a valid API key and base URL."""
    return bool(get_api_key(provider) and get_base_url(provider))


def get_configured_providers() -> list[str]:
    """Return list of providers that have API keys configured."""
    configured = []
    for provider in get_all_providers():
        if is_provider_configured(provider):
            configured.append(provider)
    return configured


# ─────────────────────────────────────────────────────────────────────────────
# CHAT COMPLETION
# ─────────────────────────────────────────────────────────────────────────────

def build_headers(provider: str, api_key: str) -> dict:
    """Build request headers for a provider."""
    p = get_all_providers().get(provider, {})
    auth = p.get("auth_header", "Bearer")

    headers = {
        "Content-Type": "application/json",
    }

    if auth == "x-api-key":
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
        headers["anthropic-dangerous-direct-browser-access"] = "true"
    else:
        headers["Authorization"] = f"{auth} {api_key}"

    return headers


def build_payload(provider: str, model: str, messages: list, temperature: float, max_tokens: int, system: str = "") -> dict:
    """Build request payload for a provider."""
    if provider == "anthropic":
        msgs = [m for m in messages if m.get("role") != "system"]
        payload = {
            "model": model,
            "messages": msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            payload["system"] = system
        return payload

    elif provider == "gemini":
        contents = []
        for m in messages:
            if m.get("role") == "system":
                continue
            role = "model" if m.get("role") == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})
        return {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

    else:
        # OpenAI-compatible
        msgs = messages
        if system:
            msgs = [{"role": "system", "content": system}] + [m for m in messages if m.get("role") != "system"]

        payload = {
            "model": model,
            "messages": msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        return payload


def get_endpoint(provider: str, model: str) -> str:
    """Get the full API endpoint URL."""
    base = get_base_url(provider)

    if provider == "anthropic":
        return f"{base}/messages"

    elif provider == "gemini":
        return f"{base}/models/{model}:generateContent?key={get_api_key(provider)}"

    else:
        return f"{base}/chat/completions"


def chat_completion(
    provider: str,
    model: str,
    messages: list,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    system: str = "",
    api_key: str = "",
) -> str:
    """
    Send a chat completion request. Returns response text.
    Raises Exception on error.
    """
    if not api_key:
        api_key = get_api_key(provider)
    if not api_key:
        raise ValueError(f"No API key for provider '{provider}'. Add it in Settings → API Keys.")

    all_providers = get_all_providers()
    if provider not in all_providers:
        raise ValueError(f"Unknown provider: '{provider}'. Available: {', '.join(all_providers.keys())}")

    import requests

    headers = build_headers(provider, api_key)
    payload = build_payload(provider, model, messages, temperature, max_tokens, system)
    endpoint = get_endpoint(provider, model)

    try:
        if provider == "gemini":
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=60)
        else:
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=60)

        resp.raise_for_status()
        data = resp.json()

        if provider == "anthropic":
            return data["content"][0]["text"]
        elif provider == "gemini":
            return data["candidates"][0]["content"]["parts"][0]["text"]
        else:
            return data["choices"][0]["message"]["content"]

    except requests.HTTPError as e:
        status = e.response.status_code
        try:
            err_body = e.response.json().get("error", {})
            message = err_body.get("message", str(e))
        except Exception:
            message = str(e)

        if status == 401:
            raise Exception(f"🔑 Auth error for {provider}. Check your API key in Settings.")
        elif status == 429:
            raise Exception(f"⏳ Rate limit hit for {provider}. Try again in a moment.")
        elif status == 400:
            raise Exception(f"❌ Bad request to {provider}: {message}")
        else:
            raise Exception(f"❌ {provider} error ({status}): {message}")

    except Exception as e:
        raise Exception(f"❌ {provider} request failed: {str(e)}")


def chat_completion_streaming(
    provider: str,
    model: str,
    messages: list,
    on_token: Callable[[str], None],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    system: str = "",
    api_key: str = "",
) -> str:
    """
    Streaming chat completion. Calls on_token(callback) for each token.
    Returns full assembled response.
    """
    if not api_key:
        api_key = get_api_key(provider)
    if not api_key:
        raise ValueError(f"No API key for provider '{provider}'.")

    all_providers = get_all_providers()
    if provider not in all_providers:
        raise ValueError(f"Unknown provider: '{provider}'")

    p = all_providers[provider]
    if not p.get("supports_streaming", False):
        # Fall back to non-streaming
        text = chat_completion(provider, model, messages, temperature, max_tokens, system, api_key)
        on_token(text)
        return text

    import requests

    headers = build_headers(provider, api_key)
    payload = build_payload(provider, model, messages, temperature, max_tokens, system)

    # Enable streaming
    if provider == "anthropic":
        payload["stream"] = True
    else:
        payload["stream"] = True

    endpoint = get_endpoint(provider, model)

    full_text = []
    try:
        with requests.post(endpoint, headers=headers, json=payload, stream=True, timeout=120) as resp:
            resp.raise_for_status()

            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.strip():
                    continue
                if line.startswith("data: "):
                    line = line[6:]
                if line == "[DONE]":
                    break

                try:
                    import json as json_lib
                    chunk = json_lib.loads(line)
                except Exception:
                    continue

                token = ""
                if provider == "anthropic":
                    token = chunk.get("completion", "")
                    if chunk.get("type") == "content_block_delta":
                        delta = chunk.get("delta", {})
                        if delta.get("type") == "text_delta":
                            token = delta.get("text", "")
                elif provider == "gemini":
                    parts = chunk.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0]
                    token = parts.get("text", "")
                else:
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    token = delta.get("content", "")

                if token:
                    full_text.append(token)
                    on_token(token)

    except Exception as e:
        raise Exception(f"Streaming error ({provider}): {str(e)}")

    return "".join(full_text)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _save_settings(data: dict):
    SETTINGS_FILE.write_text(json.dumps(data, indent=2))


def list_provider_models(provider: str) -> list[dict]:
    """List models for a provider."""
    # Check custom first
    custom = get_custom_providers()
    if provider in custom:
        return custom[provider].get("models", [])

    p = PROVIDERS.get(provider, {})
    return p.get("models", [])


def estimate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD for a model call."""
    models = list_provider_models(provider)
    for m in models:
        if m["id"] == model:
            input_cost = (input_tokens / 1_000_000) * m.get("input", 0)
            output_cost = (output_tokens / 1_000_000) * m.get("output", 0)
            return round(input_cost + output_cost, 6)
    return 0.0
