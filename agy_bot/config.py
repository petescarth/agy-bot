"""Configuration management for agy Telegram bot bridge."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Set

from dotenv import load_dotenv

# Load .env file from project root if present
load_dotenv()


def _get_env_list_ints(key: str, default: str = "") -> Set[int]:
    raw = os.getenv(key, default).strip()
    if not raw:
        return set()
    result = set()
    for item in raw.replace(";", ",").split(","):
        item = item.strip()
        if item.isdigit():
            result.add(int(item))
    return result


@dataclass
class Config:
    """Application configuration container."""

    # Telegram Credentials & Access Control
    telegram_bot_token: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    )
    allowed_user_ids: Set[int] = field(
        default_factory=lambda: _get_env_list_ints("ALLOWED_USER_IDS", os.getenv("ALLOWED_USER_ID", ""))
    )

    # agy CLI runtime configuration
    agy_bin: str = field(
        default_factory=lambda: os.getenv("AGY_BIN", shutil.which("agy") or "/home/pete/.local/bin/agy")
    )
    default_working_dir: str = field(
        default_factory=lambda: os.getenv("DEFAULT_WORKING_DIR", str(Path.cwd()))
    )
    default_model: str = field(
        default_factory=lambda: os.getenv("DEFAULT_MODEL", "gemini-3.7-flash-high")
    )
    default_effort: str = field(
        default_factory=lambda: os.getenv("DEFAULT_EFFORT", "high")  # low | medium | high
    )
    default_mode: str = field(
        default_factory=lambda: os.getenv("DEFAULT_MODE", "accept-edits")  # accept-edits | plan
    )
    default_auto_approve: bool = field(
        default_factory=lambda: os.getenv("DEFAULT_AUTO_APPROVE", "true").lower() in ("true", "1", "yes")
    )

    # UI & Streaming Behavior
    stream_update_interval: float = 1.5  # Seconds between live status message edits
    max_message_length: int = 3900      # Safe character threshold below Telegram's 4096 limit
    stream_live_preview: bool = field(
        default_factory=lambda: os.getenv("STREAM_LIVE_PREVIEW", "true").lower() in ("true", "1", "yes")
    )

    # File paths
    brain_dir: Path = field(
        default_factory=lambda: Path(os.path.expanduser("~/.gemini/antigravity-cli/brain"))
    )
    state_file: Path = field(
        default_factory=lambda: Path(os.path.expanduser("~/.gemini/antigravity-cli/agy_telegram_bot_state.json"))
    )

    # Supported model definitions
    available_models: dict[str, str] = field(
        default_factory=lambda: {
            "gemini-3.7-flash-high": "⚡ Gemini 3.7 Flash (High)",
            "gemini-3.7-flash-medium": "⚡ Gemini 3.7 Flash (Medium)",
            "gemini-3.7-flash-low": "⚡ Gemini 3.7 Flash (Low)",
            "gemini-3.1-pro-high": "🧠 Gemini 3.1 Pro (High)",
            "claude-sonnet-4-6": "🎭 Claude Sonnet 4.6 (Thinking)",
            "claude-opus-4-6-thinking": "👑 Claude Opus 4.6 (Thinking)",
            "gpt-oss-120b-medium": "🌐 GPT-OSS 120B (Medium)",
        }
    )

    def validate(self) -> list[str]:
        """Validate critical configuration settings and return list of errors."""
        errors: list[str] = []
        if not self.telegram_bot_token:
            errors.append("TELEGRAM_BOT_TOKEN is not set in environment or .env file.")
        if not self.allowed_user_ids:
            errors.append("ALLOWED_USER_IDS is empty! Set at least one Telegram user ID for security.")
        if not os.path.exists(self.agy_bin):
            errors.append(f"agy executable not found at '{self.agy_bin}'. Please install agy or set AGY_BIN.")
        return errors


# Global default configuration instance
config = Config()
