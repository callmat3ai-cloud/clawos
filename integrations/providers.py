"""
integrations/providers.py — ClawOS AI Provider System

All providers Hermes has + more. Each provider has:
- Name, logo emoji, API base URL
- Chat completions endpoint
- Required auth header
- Model list with pricing info
"""
from __future__ import annotations

import os
import json
import requests
from pathlib import Path
from typing import Optional


def _get_base_dir() -> Path:
    import sys
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _get_base_dir()
API_KEYS_PATH = BASE_DIR / "config" / "api_keys.json"


def _load_keys() -> dict:
    try:
        with open(API_KEYS_PATH, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# PROVIDER REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

PROVIDERS = {
    # OpenAI (https://platform.openai.com)
    "openai": {
        "name": "OpenAI",
        "emoji": "🤖",
        "api_base": "https://api.openai.com/v1",
        "auth_header": "Bearer",
        "env_key": "OPENAI_API_KEY",
        "models": [
            {"id": "gpt-4o", "name": "GPT-4o", "context": 128000, "input": 5.0, "output": 15.0},
            {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "context": 128000, "input": 0.15, "output": 0.60},
            {"id": "gpt-4.5-preview", "name": "GPT-4.5", "context": 128000, "input": 75.0, "output": 150.0},
            {"id": "o1-preview", "name": "o1 Preview", "context": 128000, "input": 15.0, "output": 60.0},
            {"id": "o1-mini", "name": "o1 Mini", "context": 65536, "input": 3.0, "output": 12.0},
        ],
    },

    # Anthropic (https://console.anthropic.com)
    "anthropic": {
        "name": "Anthropic",
        "emoji": "🧠",
        "api_base": "https://api.anthropic.com/v1",
        "auth_header": "x-api-key",
        "env_key": "ANTHROPIC_API_KEY",
        "models": [
            {"id": "claude-opus-4-5", "name": "Claude Opus 4.5", "context": 200000, "input": 3.0, "output": 15.0},
            {"id": "claude-sonnet-4-5", "name": "Claude Sonnet 4.5", "context": 200000, "input": 3.0, "output": 15.0},
            {"id": "claude-3-5-haiku", "name": "Claude 3.5 Haiku", "context": 200000, "input": 0.8, "output": 4.0},
            {"id": "claude-3-opus", "name": "Claude 3 Opus", "context": 200000, "input": 15.0, "output": 75.0},
            {"id": "claude-3-sonnet", "name": "Claude 3 Sonnet", "context": 200000, "input": 3.0, "output": 15.0},
        ],
    },

    # Gemini (https://aistudio.google.com)
    "gemini": {
        "name": "Google Gemini",
        "emoji": "✨",
        "api_base": "https://generativelanguage.googleapis.com/v1beta",
        "auth_header": "Bearer",
        "env_key": "GEMINI_API_KEY",
        "models": [
            {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro", "context": 2000000, "input": 1.25, "output": 10.0},
            {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "context": 1000000, "input": 0.075, "output": 0.30},
            {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash", "context": 1000000, "input": 0.10, "output": 0.40},
            {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro", "context": 2000000, "input": 1.25, "output": 10.0},
            {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash", "context": 1000000, "input": 0.075, "output": 0.30},
        ],
    },

    # OpenRouter (https://openrouter.ai)
    "openrouter": {
        "name": "OpenRouter",
        "emoji": "🌐",
        "api_base": "https://openrouter.ai/api/v1",
        "auth_header": "Bearer",
        "env_key": "OPENROUTER_API_KEY",
        "models": [
            {"id": "openai/gpt-4o", "name": "GPT-4o", "context": 128000, "input": 2.5, "output": 10.0},
            {"id": "anthropic/claude-opus-4-5", "name": "Claude Opus 4.5", "context": 200000, "input": 15.0, "output": 75.0},
            {"id": "google/gemini-2.5-pro", "name": "Gemini 2.5 Pro", "context": 2000000, "input": 2.5, "output": 10.0},
            {"id": "meta-llama/llama-3.3-70b", "name": "Llama 3.3 70B", "context": 128000, "input": 0.65, "output": 2.75},
            {"id": "deepseek/deepseek-chat-v3", "name": "DeepSeek V3", "context": 64000, "input": 0.27, "output": 1.10},
            {"id": "mistralai/mistral-nemo", "name": "Mistral Nemo", "context": 128000, "input": 0.15, "output": 0.15},
            {"id": "qwen/qwen-2.5-72b", "name": "Qwen 2.5 72B", "context": 32000, "input": 0.27, "output": 0.27},
        ],
    },

    # Groq (https://console.groq.com)
    "groq": {
        "name": "Groq",
        "emoji": "⚡",
        "api_base": "https://api.groq.com/openai/v1",
        "auth_header": "Bearer",
        "env_key": "GROQ_API_KEY",
        "models": [
            {"id": "llama-3.3-70b", "name": "Llama 3.3 70B", "context": 128000, "input": 0.59, "output": 2.40},
            {"id": "llama-3.1-8b", "name": "Llama 3.1 8B", "context": 128000, "input": 0.05, "output": 0.08},
            {"id": "mixtral-8x7b", "name": "Mixtral 8x7B", "context": 32000, "input": 0.24, "output": 0.24},
            {"id": "gemma2-9b", "name": "Gemma 2 9B", "context": 8192, "input": 0.20, "output": 0.20},
        ],
    },

    # Mistral (https://console.mistral.ai)
    "mistral": {
        "name": "Mistral",
        "emoji": "🌊",
        "api_base": "https://api.mistral.ai/v1",
        "auth_header": "Bearer",
        "env_key": "MISTRAL_API_KEY",
        "models": [
            {"id": "mistral-nemo", "name": "Mistral Nemo", "context": 128000, "input": 0.15, "output": 0.15},
            {"id": "mistral-small", "name": "Mistral Small", "context": 128000, "input": 0.30, "output": 0.90},
            {"id": "codestral", "name": "Codestral", "context": 32000, "input": 0.30, "output": 0.90},
            {"id": "open-mistral-7b", "name": "Mistral 7B", "context": 32000, "input": 0.25, "output": 0.25},
        ],
    },

    # Perplexity (https://console.perplexity.ai)
    "perplexity": {
        "name": "Perplexity",
        "emoji": "🔍",
        "api_base": "https://api.perplexity.ai",
        "auth_header": "Bearer",
        "env_key": "PERPLEXITY_API_KEY",
        "models": [
            {"id": "sonar-pro", "name": "Sonar Pro", "context": 128000, "input": 3.0, "output": 15.0},
            {"id": "sonar", "name": "Sonar", "context": 127000, "input": 0.0, "output": 1.0},
            {"id": "sonar-reasoning-pro", "name": "Sonar Reasoning Pro", "context": 128000, "input": 5.0, "output": 20.0},
            {"id": "sonar-reasoning", "name": "Sonar Reasoning", "context": 128000, "input": 1.0, "output": 5.0},
        ],
    },

    # Cohere (https://dashboard.cohere.com)
    "cohere": {
        "name": "Cohere",
        "emoji": "🧩",
        "api_base": "https://api.cohere.ai/v2",
        "auth_header": "Bearer",
        "env_key": "COHERE_API_KEY",
        "models": [
            {"id": "command-a-plus", "name": "Command A+", "context": 200000, "input": 3.0, "output": 15.0},
            {"id": "command-r-plus", "name": "Command R+", "context": 128000, "input": 3.0, "output": 15.0},
            {"id": "command-r", "name": "Command R", "context": 128000, "input": 0.50, "output": 1.50},
            {"id": "command", "name": "Command", "context": 4096, "input": 0.30, "output": 0.30},
        ],
    },

    # Together AI (https://together.ai)
    "together": {
        "name": "Together AI",
        "emoji": "🚀",
        "api_base": "https://api.together.xyz/v1",
        "auth_header": "Bearer",
        "env_key": "TOGETHER_API_KEY",
        "models": [
            {"id": "meta-llama/Llama-3.3-70B-Instruct", "name": "Llama 3.3 70B", "context": 128000, "input": 0.88, "output": 0.88},
            {"id": "deepseek-ai/DeepSeek-V3", "name": "DeepSeek V3", "context": 64000, "input": 0.27, "output": 1.10},
            {"id": "Qwen/Qwen2.5-72B-Instruct", "name": "Qwen 2.5 72B", "context": 32000, "input": 0.27, "output": 0.27},
            {"id": "mistralai/Mixtral-8x22B-Instruct-v0.1", "name": "Mixtral 8x22B", "context": 64000, "input": 0.65, "output": 2.40},
        ],
    },

    # DeepSeek (https://platform.deepseek.com)
    "deepseek": {
        "name": "DeepSeek",
        "emoji": "🔮",
        "api_base": "https://api.deepseek.com/v1",
        "auth_header": "Bearer",
        "env_key": "DEEPSEEK_API_KEY",
        "models": [
            {"id": "deepseek-chat", "name": "DeepSeek Chat V3", "context": 64000, "input": 0.27, "output": 1.10},
            {"id": "deepseek-coder", "name": "DeepSeek Coder", "context": 64000, "input": 0.14, "output": 0.28},
            {"id": "deepseek-reasoner", "name": "DeepSeek Reasoner", "context": 64000, "input": 0.55, "output": 2.19},
        ],
    },

    # Grok / xAI (https://console.x.ai)
    "xai": {
        "name": "xAI (Grok)",
        "emoji": "🤖",
        "api_base": "https://api.x.ai/v1",
        "auth_header": "Bearer",
        "env_key": "XAI_API_KEY",
        "models": [
            {"id": "grok-3", "name": "Grok 3", "context": 131072, "input": 5.0, "output": 15.0},
            {"id": "grok-2-1212", "name": "Grok 2", "context": 131072, "input": 2.0, "output": 10.0},
            {"id": "grok-beta", "name": "Grok Beta", "context": 131072, "input": 5.0, "output": 15.0},
        ],
    },

    # Ollama (local)
    "ollama": {
        "name": "Ollama (Local)",
        "emoji": "🏠",
        "api_base": "http://localhost:11434/v1",
        "auth_header": "Bearer",
        "env_key": "OLLAMA_API_KEY",
        "models": [
            {"id": "llama3.3:70b", "name": "Llama 3.3 70B", "context": 128000, "input": 0.0, "output": 0.0},
            {"id": "llama3.2:3b", "name": "Llama 3.2 3B", "context": 32000, "input": 0.0, "output": 0.0},
            {"id": "qwen2.5:72b", "name": "Qwen 2.5 72B", "context": 32000, "input": 0.0, "output": 0.0},
            {"id": "codestral:22b", "name": "Codestral 22B", "context": 32000, "input": 0.0, "output": 0.0},
            {"id": "mistral-nemo:12b", "name": "Mistral Nemo 12B", "context": 128000, "input": 0.0, "output": 0.0},
            {"id": "gemma2:27b", "name": "Gemma 2 27B", "context": 8192, "input": 0.0, "output": 0.0},
        ],
    },
}


def get_provider(name: str) -> Optional[dict]:
    return PROVIDERS.get(name)


def get_all_providers() -> list[dict]:
    """Return list of all provider configs."""
    return [{"id": k, **v} for k, v in PROVIDERS.items()]


def get_api_key_for_provider(provider: str) -> str:
    """Get API key for a provider from config file."""
    keys = _load_keys()
    config_key_map = {
        "openai": "openai_api_key",
        "anthropic": "anthropic_api_key",
        "gemini": "gemini_api_key",
        "openrouter": "openrouter_api_key",
        "groq": "groq_api_key",
        "mistral": "mistral_api_key",
        "perplexity": "perplexity_api_key",
        "cohere": "cohere_api_key",
        "together": "together_api_key",
        "deepseek": "deepseek_api_key",
        "xai": "xai_api_key",
        "ollama": "ollama_api_key",
    }
    key_name = config_key_map.get(provider, f"{provider}_api_key")
    return keys.get(key_name, os.environ.get(PROVIDERS.get(provider, {}).get("env_key", ""), ""))


def is_provider_configured(provider: str) -> bool:
    """Check if a provider has a valid API key."""
    return bool(get_api_key_for_provider(provider).strip())


def chat_completion(
    provider: str,
    model: str,
    messages: list[dict],
    api_key: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """
    Send a chat completion request to any supported provider.
    Returns the assistant's response text.
    Raises Exception on error.
    """
    p = PROVIDERS.get(provider)
    if not p:
        raise ValueError(f"Unknown provider: {provider}")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Build payload based on provider
    if provider == "anthropic":
        # Anthropic uses messages format + system
        system = ""
        msgs = messages
        for m in messages:
            if m.get("role") == "system":
                system = m.get("content", "")
        msgs = [m for m in messages if m.get("role") != "system"]
        payload = {
            "model": model,
            "messages": msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            payload["system"] = system
        endpoint = f"{p['api_base']}/messages"
        headers["anthropic-version"] = "2023-06-01"
        headers["anthropic-dangerous-direct-browser-access"] = "true"
        response = requests.post(endpoint, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        return data["content"][0]["text"]

    elif provider in ("gemini",):
        # Gemini uses contents format
        contents = []
        for m in messages:
            role = "model" if m.get("role") == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        endpoint = f"{p['api_base']}/models/{model}:generateContent?key={api_key}"
        headers.pop("Authorization", None)
        response = requests.post(endpoint, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    elif provider == "ollama":
        # Ollama uses OpenAI-compatible format but no auth
        headers.pop("Authorization", None)
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        response = requests.post(
            f"{p['api_base']}/chat",
            headers=headers,
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["message"]["content"]

    else:
        # OpenAI-compatible providers
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        endpoint = f"{p['api_base']}/chat/completions"
        response = requests.post(endpoint, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
