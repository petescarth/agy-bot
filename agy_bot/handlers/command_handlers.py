"""Telegram slash command handlers for agy bot."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from agy_bot.config import config
from agy_bot.formatting import escape_html
from agy_bot.session_manager import session_manager

logger = logging.getLogger(__name__)


def is_authorized(user_id: int) -> bool:
    """Check if the telegram user is whitelisted."""
    return user_id in config.allowed_user_ids


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user = update.effective_user
    if not user or not is_authorized(user.id):
        if update.message:
            await update.message.reply_text("⛔ <b>Unauthorized.</b> Your Telegram ID is not on the whitelist.", parse_mode="HTML")
        return

    session = session_manager.get_session(user.id)
    model_name = config.available_models.get(session.model, session.model)

    welcome_text = (
        f"🤖 <b>Welcome to Antigravity CLI Controller!</b>\n\n"
        f"Control your <code>agy</code> agent directly from Telegram.\n\n"
        f"📁 <b>Workspace:</b> <code>{escape_html(session.working_dir)}</code>\n"
        f"🤖 <b>Model:</b> {escape_html(model_name)}\n"
        f"🧠 <b>Reasoning Effort:</b> <code>{escape_html(session.effort.upper())}</code>\n"
        f"🎯 <b>Mode:</b> <code>{escape_html(session.mode)}</code>\n\n"
        "💬 <i>Send any message to start prompting your agent, or use the menu below.</i>"
    )

    buttons = [
        [
            InlineKeyboardButton("🎛️ Dashboard", callback_data="show_status"),
            InlineKeyboardButton("🤖 Model", callback_data="menu_models"),
        ],
        [
            InlineKeyboardButton("✨ New Chat", callback_data="reset_conv"),
            InlineKeyboardButton("📜 Sessions", callback_data="page_conv:0"),
        ],
    ]

    if update.message:
        await update.message.reply_text(
            welcome_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
        )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command with full command reference."""
    user = update.effective_user
    if not user or not is_authorized(user.id):
        return

    help_text = (
        "📖 <b>Antigravity Bot Command Reference</b>\n\n"
        "<b>💬 Agent Interaction:</b>\n"
        "• Send any standard text message to prompt the agent.\n"
        "• Upload a document or image to analyze it in your workspace.\n"
        "• <code>/stop</code> or <code>/cancel</code> — Stop active execution.\n\n"
        "<b>🗂️ Session & Conversation:</b>\n"
        "• <code>/new</code> — Start a clean new conversation.\n"
        "• <code>/sessions</code> — Browse and resume past sessions.\n"
        "• <code>/resume &lt;id&gt;</code> — Resume a specific conversation ID.\n"
        "• <code>/status</code> — Open the live control dashboard.\n\n"
        "<b>📁 Workspace & Files:</b>\n"
        "• <code>/cd &lt;path&gt;</code> — Change agent working directory.\n"
        "• <code>/pwd</code> — Display current working directory.\n"
        "• <code>/ls [path]</code> — List files in the workspace.\n"
        "• <code>/git</code> — View git status and recent commits.\n\n"
        "<b>⚙️ Agent Settings:</b>\n"
        "• <code>/model</code> — Select LLM model.\n"
        "• <code>/effort [low|medium|high]</code> — Set reasoning effort.\n"
        "• <code>/mode [accept-edits|plan]</code> — Set execution mode.\n"
        "• <code>/perms</code> — Toggle auto-approve tool permissions.\n"
    )

    if update.message:
        await update.message.reply_text(help_text, parse_mode="HTML")


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command."""
    user = update.effective_user
    if not user or not is_authorized(user.id):
        return

    session = session_manager.get_session(user.id)
    model_name = config.available_models.get(session.model, session.model)

    conv_display = (
        f"<code>{session.active_conversation_id}</code>"
        if session.active_conversation_id
        else "<i>(None - will start new session)</i>"
    )
    perm_display = "⚡ Auto-Approve (Skip Prompts)" if session.auto_approve else "🔒 Standard Permissions"
    run_state = "🟡 Running" if session.is_running() else "🟢 Idle"

    status_text = (
        "🎛️ <b>Antigravity CLI Control Dashboard</b>\n\n"
        f"📊 <b>State:</b> {run_state}\n"
        f"📁 <b>Workspace:</b> <code>{escape_html(session.working_dir)}</code>\n"
        f"🤖 <b>Model:</b> {escape_html(model_name)}\n"
        f"🧠 <b>Effort:</b> <code>{escape_html(session.effort.upper())}</code>\n"
        f"🎯 <b>Mode:</b> <code>{escape_html(session.mode)}</code>\n"
        f"🛡️ <b>Permissions:</b> {perm_display}\n"
        f"🆔 <b>Active Conversation:</b>\n{conv_display}\n"
    )

    buttons = [
        [
            InlineKeyboardButton("🤖 Change Model", callback_data="menu_models"),
            InlineKeyboardButton("🧠 Reasoning Effort", callback_data="menu_effort"),
        ],
        [
            InlineKeyboardButton("🎯 Execution Mode", callback_data="menu_mode"),
            InlineKeyboardButton("🛡️ Toggle Auto-Approve", callback_data="toggle_perms"),
        ],
        [
            InlineKeyboardButton("✨ New Conversation", callback_data="reset_conv"),
            InlineKeyboardButton("📜 Browse Sessions", callback_data="page_conv:0"),
        ],
    ]

    if update.message:
        await update.message.reply_text(
            status_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
        )


async def new_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /new command to start a new conversation session."""
    user = update.effective_user
    if not user or not is_authorized(user.id):
        return

    session_manager.reset_conversation(user.id)
    session = session_manager.get_session(user.id)
    if update.message:
        await update.message.reply_text(
            "✨ <b>Started a new conversation session.</b>\n"
            f"📁 <b>Working Directory:</b> <code>{escape_html(session.working_dir)}</code>\n"
            "Your next prompt will initiate a fresh context.",
            parse_mode="HTML",
        )


async def sessions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /sessions command to list conversations."""
    user = update.effective_user
    if not user or not is_authorized(user.id):
        return

    all_convs = session_manager.list_saved_conversations(limit=50)
    session = session_manager.get_session(user.id)

    if not all_convs:
        if update.message:
            await update.message.reply_text("📜 No saved conversations found in Antigravity storage.")
        return

    page_size = 5
    page_items = all_convs[:page_size]
    total_pages = (len(all_convs) + page_size - 1) // page_size

    text_lines = [
        f"📜 <b>Saved Conversations (Page 1/{total_pages}):</b>\n",
    ]

    buttons = []
    for item in page_items:
        is_active = item.conversation_id == session.active_conversation_id
        tag = " 🌟 (Active)" if is_active else ""
        text_lines.append(
            f"• <b>{escape_html(item.title)}</b>{tag}\n"
            f"  📅 {item.last_active} | 💬 {item.turn_count} turns\n"
            f"  🆔 <code>{item.conversation_id}</code>\n"
        )
        btn_label = f"▶️ Resume: {item.title[:20]}"
        buttons.append([InlineKeyboardButton(btn_label, callback_data=f"resume_conv:{item.conversation_id}")])

    nav_row = [InlineKeyboardButton("🔙 Dashboard", callback_data="show_status")]
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data="page_conv:1"))
    buttons.append(nav_row)

    if update.message:
        await update.message.reply_text(
            "\n".join(text_lines),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
        )


async def resume_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /resume <id> command."""
    user = update.effective_user
    if not user or not is_authorized(user.id):
        return

    if not context.args:
        # If no ID given, delegate to sessions_cmd
        await sessions_cmd(update, context)
        return

    conv_id = context.args[0].strip()
    session_manager.set_active_conversation(user.id, conv_id)
    session = session_manager.get_session(user.id)

    if update.message:
        await update.message.reply_text(
            f"🔄 <b>Resumed Conversation:</b> <code>{conv_id}</code>\n"
            f"📁 <b>Workspace:</b> <code>{escape_html(session.working_dir)}</code>\n"
            "Send your next message to continue.",
            parse_mode="HTML",
        )


async def cd_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /cd <path> command."""
    user = update.effective_user
    if not user or not is_authorized(user.id):
        return

    if not context.args:
        session = session_manager.get_session(user.id)
        if update.message:
            await update.message.reply_text(
                f"📁 <b>Current Directory:</b> <code>{escape_html(session.working_dir)}</code>\n\n"
                "Usage: <code>/cd /path/to/project</code>",
                parse_mode="HTML",
            )
        return

    target_path = " ".join(context.args)
    # Handle relative paths based on current user session cwd
    session = session_manager.get_session(user.id)
    if not os.path.isabs(os.path.expanduser(target_path)):
        target_path = os.path.join(session.working_dir, target_path)

    ok, result = session_manager.set_working_dir(user.id, target_path)
    if update.message:
        if ok:
            await update.message.reply_text(
                f"📁 <b>Workspace changed:</b>\n<code>{escape_html(result)}</code>",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(f"❌ {escape_html(result)}", parse_mode="HTML")


async def pwd_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /pwd command."""
    user = update.effective_user
    if not user or not is_authorized(user.id):
        return

    session = session_manager.get_session(user.id)
    if update.message:
        await update.message.reply_text(
            f"📁 <b>Current Workspace:</b>\n<code>{escape_html(session.working_dir)}</code>",
            parse_mode="HTML",
        )


async def ls_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ls [path] command."""
    user = update.effective_user
    if not user or not is_authorized(user.id):
        return

    session = session_manager.get_session(user.id)
    target_dir = session.working_dir
    if context.args:
        custom_dir = " ".join(context.args)
        if not os.path.isabs(os.path.expanduser(custom_dir)):
            custom_dir = os.path.join(session.working_dir, custom_dir)
        target_dir = os.path.abspath(os.path.expanduser(custom_dir))

    if not os.path.exists(target_dir) or not os.path.isdir(target_dir):
        if update.message:
            await update.message.reply_text(f"❌ Directory not found: <code>{escape_html(target_dir)}</code>", parse_mode="HTML")
        return

    try:
        entries = sorted(os.scandir(target_dir), key=lambda e: (not e.is_dir(), e.name.lower()))
        lines = [f"📂 <b>Contents of</b> <code>{escape_html(target_dir)}</code>:\n"]

        count = 0
        for entry in entries:
            if entry.name.startswith(".git"):
                continue
            count += 1
            if count > 40:
                lines.append(f"<i>... and {len(entries) - 40} more items</i>")
                break
            icon = "📁" if entry.is_dir() else "📄"
            lines.append(f"{icon} <code>{escape_html(entry.name)}</code>")

        if count == 0:
            lines.append("<i>(Directory is empty)</i>")

        if update.message:
            await update.message.reply_text("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        if update.message:
            await update.message.reply_text(f"❌ Error listing directory: {escape_html(str(e))}", parse_mode="HTML")


async def git_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /git command to show workspace git status."""
    user = update.effective_user
    if not user or not is_authorized(user.id):
        return

    session = session_manager.get_session(user.id)
    cwd = session.working_dir

    try:
        res = subprocess.run(
            ["git", "status", "-s", "-b"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode != 0:
            if update.message:
                await update.message.reply_text(f"ℹ️ Not a git repository in <code>{escape_html(cwd)}</code>", parse_mode="HTML")
            return

        status_out = res.stdout.strip()
        if not status_out:
            status_out = "Working tree clean."

        # Get last commit
        log_res = subprocess.run(
            ["git", "log", "-1", "--oneline"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        last_commit = log_res.stdout.strip()

        msg = (
            f"🌿 <b>Git Status</b> (<code>{escape_html(cwd)}</code>):\n"
            f"<code>{escape_html(status_out)}</code>\n\n"
            f"📌 <b>Last Commit:</b> <code>{escape_html(last_commit)}</code>"
        )
        if update.message:
            await update.message.reply_text(msg, parse_mode="HTML")
    except Exception as e:
        if update.message:
            await update.message.reply_text(f"❌ Error checking git: {escape_html(str(e))}", parse_mode="HTML")


async def model_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /model command to show model selector."""
    user = update.effective_user
    if not user or not is_authorized(user.id):
        return

    session = session_manager.get_session(user.id)
    buttons = []
    for model_id, label in config.available_models.items():
        check = "✓ " if session.model == model_id else ""
        buttons.append([InlineKeyboardButton(f"{check}{label}", callback_data=f"set_model:{model_id}")])

    if update.message:
        await update.message.reply_text(
            "🤖 <b>Select Agent Model:</b>",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
        )


async def effort_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /effort [low|medium|high] command."""
    user = update.effective_user
    if not user or not is_authorized(user.id):
        return

    if context.args:
        val = context.args[0].lower().strip()
        if val in ("low", "medium", "high"):
            session_manager.set_effort(user.id, val)
            if update.message:
                await update.message.reply_text(f"🧠 Reasoning effort set to <b>{val.upper()}</b>", parse_mode="HTML")
            return

    session = session_manager.get_session(user.id)
    efforts = [
        ("low", "🌱 Low Effort (Faster, less reasoning)"),
        ("medium", "⚖️ Medium Effort (Balanced)"),
        ("high", "🧠 High Effort (Deep reasoning)"),
    ]
    buttons = []
    for val, label in efforts:
        check = "✓ " if session.effort == val else ""
        buttons.append([InlineKeyboardButton(f"{check}{label}", callback_data=f"set_effort:{val}")])

    if update.message:
        await update.message.reply_text(
            "🧠 <b>Select Reasoning Effort:</b>",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
        )


async def mode_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /mode [accept-edits|plan] command."""
    user = update.effective_user
    if not user or not is_authorized(user.id):
        return

    if context.args:
        val = context.args[0].lower().strip()
        if val in ("accept-edits", "plan"):
            session_manager.set_mode(user.id, val)
            if update.message:
                await update.message.reply_text(f"🎯 Execution mode set to <b>{val}</b>", parse_mode="HTML")
            return

    session = session_manager.get_session(user.id)
    modes = [
        ("accept-edits", "✏️ Accept Edits (Allows file edits & tool commands)"),
        ("plan", "📋 Plan Mode (Read-only analysis & planning)"),
    ]
    buttons = []
    for m_val, m_label in modes:
        check = "✓ " if session.mode == m_val else ""
        buttons.append([InlineKeyboardButton(f"{check}{m_label}", callback_data=f"set_mode:{m_val}")])

    if update.message:
        await update.message.reply_text(
            "🎯 <b>Select Execution Mode:</b>",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
        )


async def perms_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /perms command to toggle auto tool approval."""
    user = update.effective_user
    if not user or not is_authorized(user.id):
        return

    new_val = session_manager.toggle_auto_approve(user.id)
    state_str = "Auto-Approve Enabled (Skip Prompts)" if new_val else "Standard Tool Confirmation"
    if update.message:
        await update.message.reply_text(f"🛡️ Tool Permissions: <b>{state_str}</b>", parse_mode="HTML")


async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stop or /cancel command to interrupt running agent."""
    user = update.effective_user
    if not user or not is_authorized(user.id):
        return

    session = session_manager.get_session(user.id)
    if session.is_running() and session.current_task:
        session.current_task.cancel()
        if update.message:
            await update.message.reply_text("🛑 <b>Sent cancellation signal to running agent.</b>", parse_mode="HTML")
    else:
        if update.message:
            await update.message.reply_text("ℹ️ No active agent task is currently running.")
