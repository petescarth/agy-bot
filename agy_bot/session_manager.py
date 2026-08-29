"""User session, workspace, and conversation management."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from agy_bot.config import config

logger = logging.getLogger(__name__)


@dataclass
class ConversationMetadata:
    conversation_id: str
    title: str
    created_at: str
    last_active: str
    turn_count: int = 1


@dataclass
class UserSession:
    user_id: int
    active_conversation_id: Optional[str] = None
    working_dir: str = field(default_factory=lambda: config.default_working_dir)
    model: str = field(default_factory=lambda: config.default_model)
    effort: str = field(default_factory=lambda: config.default_effort)
    mode: str = field(default_factory=lambda: config.default_mode)
    auto_approve: bool = field(default_factory=lambda: config.default_auto_approve)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_active: str = field(default_factory=lambda: datetime.now().isoformat())

    # In-memory execution state (not serialized to disk)
    current_task: Optional[asyncio.Task] = field(default=None, repr=False)
    current_process: Optional[asyncio.subprocess.Process] = field(default=None, repr=False)

    def is_running(self) -> bool:
        """Check if an agy task is currently executing for this user."""
        return self.current_task is not None and not self.current_task.done()


class SessionManager:
    """Manages active sessions, working directories, and conversation history."""

    def __init__(self, state_file: Optional[Path] = None):
        self.state_file = state_file or config.state_file
        self.sessions: Dict[int, UserSession] = {}
        self._load_state()

    def get_session(self, user_id: int) -> UserSession:
        """Get existing user session or create a new default session."""
        if user_id not in self.sessions:
            self.sessions[user_id] = UserSession(user_id=user_id)
            self._save_state()
        return self.sessions[user_id]

    def reset_conversation(self, user_id: int) -> str:
        """Clear active conversation ID to start a fresh agent session."""
        session = self.get_session(user_id)
        session.active_conversation_id = None
        session.last_active = datetime.now().isoformat()
        self._save_state()
        return "Started a new conversation session."

    def set_active_conversation(self, user_id: int, conv_id: str) -> None:
        """Set active conversation UUID for user."""
        session = self.get_session(user_id)
        session.active_conversation_id = conv_id
        session.last_active = datetime.now().isoformat()
        self._save_state()

    def set_working_dir(self, user_id: int, new_path: str) -> tuple[bool, str]:
        """Change the current working directory for this user."""
        session = self.get_session(user_id)
        expanded = os.path.abspath(os.path.expanduser(new_path))
        if not os.path.exists(expanded):
            return False, f"Directory '{expanded}' does not exist."
        if not os.path.isdir(expanded):
            return False, f"Path '{expanded}' is not a directory."

        session.working_dir = expanded
        session.last_active = datetime.now().isoformat()
        self._save_state()
        return True, expanded

    def set_model(self, user_id: int, model_name: str) -> bool:
        """Set active LLM model."""
        session = self.get_session(user_id)
        session.model = model_name
        session.last_active = datetime.now().isoformat()
        self._save_state()
        return True

    def set_effort(self, user_id: int, effort: str) -> bool:
        """Set reasoning effort (low, medium, high)."""
        if effort not in ("low", "medium", "high"):
            return False
        session = self.get_session(user_id)
        session.effort = effort
        session.last_active = datetime.now().isoformat()
        self._save_state()
        return True

    def set_mode(self, user_id: int, mode: str) -> bool:
        """Set agent mode (accept-edits, plan)."""
        if mode not in ("accept-edits", "plan"):
            return False
        session = self.get_session(user_id)
        session.mode = mode
        session.last_active = datetime.now().isoformat()
        self._save_state()
        return True

    def toggle_auto_approve(self, user_id: int) -> bool:
        """Toggle automatic tool approval."""
        session = self.get_session(user_id)
        session.auto_approve = not session.auto_approve
        session.last_active = datetime.now().isoformat()
        self._save_state()
        return session.auto_approve

    def list_saved_conversations(self, limit: int = 20) -> List[ConversationMetadata]:
        """Discover past conversations from the Antigravity brain storage."""
        results: List[ConversationMetadata] = []
        brain_path = config.brain_dir

        if not brain_path.exists() or not brain_path.is_dir():
            return results

        try:
            # List all UUID directories
            dirs = [d for d in brain_path.iterdir() if d.is_dir() and len(d.name) == 36 and "-" in d.name]
            # Sort by modification time (most recent first)
            dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)

            for conv_dir in dirs[:limit]:
                conv_id = conv_dir.name
                mtime = datetime.fromtimestamp(conv_dir.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                title = f"Conversation {conv_id[:8]}"
                turn_count = 1

                # Attempt to extract title from transcript.jsonl
                transcript_file = conv_dir / ".system_generated" / "logs" / "transcript.jsonl"
                if transcript_file.exists():
                    try:
                        with open(transcript_file, "r", encoding="utf-8") as f:
                            turns = 0
                            for line in f:
                                try:
                                    entry = json.loads(line)
                                    if entry.get("type") == "USER_INPUT":
                                        turns += 1
                                        if turns == 1:
                                            raw_content = entry.get("content", "")
                                            # Clean tags like <USER_REQUEST>
                                            clean = raw_content.replace("<USER_REQUEST>", "").replace("</USER_REQUEST>", "")
                                            # Strip XML metadata tags
                                            clean = clean.split("<ADDITIONAL_METADATA>")[0].strip()
                                            clean = clean.replace("\n", " ")
                                            if clean:
                                                title = clean[:50] + ("..." if len(clean) > 50 else "")
                                except Exception:
                                    continue
                            if turns > 0:
                                turn_count = turns
                    except Exception as err:
                        logger.debug("Failed reading transcript %s: %s", transcript_file, err)

                results.append(
                    ConversationMetadata(
                        conversation_id=conv_id,
                        title=title,
                        created_at=mtime,
                        last_active=mtime,
                        turn_count=turn_count,
                    )
                )
        except Exception as e:
            logger.error("Error scanning brain directory: %s", e)

        return results

    def _load_state(self) -> None:
        """Load persistent session configurations from disk."""
        if not self.state_file.exists():
            return
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for uid_str, sdata in data.items():
                    uid = int(uid_str)
                    self.sessions[uid] = UserSession(
                        user_id=uid,
                        active_conversation_id=sdata.get("active_conversation_id"),
                        working_dir=sdata.get("working_dir", config.default_working_dir),
                        model=sdata.get("model", config.default_model),
                        effort=sdata.get("effort", config.default_effort),
                        mode=sdata.get("mode", config.default_mode),
                        auto_approve=sdata.get("auto_approve", config.default_auto_approve),
                        created_at=sdata.get("created_at", datetime.now().isoformat()),
                        last_active=sdata.get("last_active", datetime.now().isoformat()),
                    )
        except Exception as e:
            logger.warning("Failed to load session state: %s", e)

    def _save_state(self) -> None:
        """Save persistent session configurations to disk."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            data: Dict[str, Any] = {}
            for uid, sess in self.sessions.items():
                data[str(uid)] = {
                    "user_id": sess.user_id,
                    "active_conversation_id": sess.active_conversation_id,
                    "working_dir": sess.working_dir,
                    "model": sess.model,
                    "effort": sess.effort,
                    "mode": sess.mode,
                    "auto_approve": sess.auto_approve,
                    "created_at": sess.created_at,
                    "last_active": sess.last_active,
                }
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning("Failed to save session state: %s", e)


# Global singleton instance
session_manager = SessionManager()
