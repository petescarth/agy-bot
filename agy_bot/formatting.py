"""Message formatting, splitting, and rendering utilities for Telegram."""

from __future__ import annotations

import html
import re
from typing import List, Optional


def escape_html(text: str) -> str:
    """Safely escape text for Telegram HTML parse mode."""
    return html.escape(text, quote=False)


def format_tokens(count: int) -> str:
    """Format token count into human-readable representation."""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}k"
    return str(count)


def format_duration(seconds: float) -> str:
    """Format duration in seconds into a clean human-readable string."""
    if seconds < 1.0:
        return f"{int(seconds * 1000)}ms"
    if seconds < 60.0:
        return f"{seconds:.1f}s"
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}m {secs}s"


def format_tool_call_summary(tool_name: str, parameters: dict) -> str:
    """Format tool call arguments for concise progress display."""
    if not parameters:
        return tool_name

    # Check for common parameter patterns
    if "CommandLine" in parameters:
        cmd = str(parameters["CommandLine"]).strip().replace("\n", " ")
        if len(cmd) > 45:
            cmd = cmd[:42] + "..."
        return f"<code>run_command</code> <i>{escape_html(cmd)}</i>"
    if "AbsolutePath" in parameters:
        path = str(parameters["AbsolutePath"]).split("/")[-1]
        return f"<code>view_file</code> <i>{escape_html(path)}</i>"
    if "TargetFile" in parameters:
        path = str(parameters["TargetFile"]).split("/")[-1]
        return f"<code>edit_file</code> <i>{escape_html(path)}</i>"
    if "Query" in parameters:
        query = str(parameters["Query"])[:35]
        return f"<code>search</code> <i>{escape_html(query)}</i>"
    if "Prompt" in parameters:
        p = str(parameters["Prompt"])[:35]
        return f"<code>{escape_html(tool_name)}</code> <i>{escape_html(p)}</i>"

    # Fallback to tool name and first argument
    first_key = next(iter(parameters))
    first_val = str(parameters[first_key])[:30]
    return f"<code>{escape_html(tool_name)}</code> <i>({escape_html(first_key)}={escape_html(first_val)})</i>"


def split_text_smartly(text: str, max_chunk_size: int = 3900) -> List[str]:
    """
    Split a large text into chunks of at most `max_chunk_size`,
    preferring splits at paragraphs, newlines, or code block boundaries.
    """
    if len(text) <= max_chunk_size:
        return [text]

    chunks: List[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_chunk_size:
            chunks.append(remaining)
            break

        # Find best split point
        candidate = remaining[:max_chunk_size]

        # Prefer double newline (paragraph boundary)
        split_idx = candidate.rfind("\n\n")
        if split_idx == -1 or split_idx < max_chunk_size // 3:
            # Prefer single newline
            split_idx = candidate.rfind("\n")
        if split_idx == -1 or split_idx < max_chunk_size // 3:
            # Prefer space
            split_idx = candidate.rfind(" ")
        if split_idx == -1 or split_idx < max_chunk_size // 3:
            # Force split at max limit
            split_idx = max_chunk_size

        chunk = remaining[:split_idx].rstrip()
        remaining = remaining[split_idx:].lstrip("\r\n")

        if chunk:
            chunks.append(chunk)

    return chunks


def format_stats_footer(
    duration: float,
    usage: Optional[dict] = None,
    conversation_id: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """Format footer with duration, token counts, and session id."""
    parts = [f"⏱️ {format_duration(duration)}"]

    if usage:
        total = usage.get("total_tokens", 0)
        thinking = usage.get("thinking_tokens", 0)
        if total:
            parts.append(f"🪙 {format_tokens(total)} tokens")
        if thinking:
            parts.append(f"🧠 {format_tokens(thinking)} thinking")

    if model:
        short_model = model.replace("gemini-", "gemini-").replace("-high", "").replace("-medium", "")
        parts.append(f"🤖 {short_model}")

    if conversation_id:
        short_id = conversation_id.split("-")[0]
        parts.append(f"🆔 <code>{short_id}</code>")

    return " • ".join(parts)


def format_progress_message(
    current_action: str,
    tool_history: list[str],
    elapsed_seconds: float,
    partial_text: str = "",
    model: str = "",
) -> str:
    """Format an active progress status box for real-time Telegram updates."""
    lines = [
        f"⚡ <b>Antigravity Agent Working</b> ({format_duration(elapsed_seconds)})",
    ]
    if model:
        lines.append(f"🤖 <i>{escape_html(model)}</i>")

    lines.append("")
    lines.append(f"▶️ <b>Current:</b> {current_action}")

    if tool_history:
        recent = tool_history[-3:]  # Show last 3 tools
        lines.append("")
        lines.append("📜 <b>Recent actions:</b>")
        for act in recent:
            lines.append(f"  ✓ {act}")

    if partial_text:
        # Show small preview of response
        preview = partial_text.strip()
        if len(preview) > 300:
            preview = "..." + preview[-297:]
        lines.append("")
        lines.append(f"📝 <b>Preview:</b>\n<pre>{escape_html(preview)}</pre>")

    return "\n".join(lines)
