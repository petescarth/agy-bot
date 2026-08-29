"""Inline keyboard callback query handlers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from agy_bot.config import config
from agy_bot.formatting import escape_html
from agy_bot.session_manager import session_manager

logger = logging.getLogger(__name__)


def is_authorized(user_id: int) -> bool:
    return user_id in config.allowed_user_ids


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Central router for all inline button callback queries."""
    query = update.callback_query
    if not query:
        return

    user = update.effective_user
    if not user or not is_authorized(user.id):
        await query.answer("⛔ Unauthorized access.", show_alert=True)
        return

    data = query.data or ""
    session = session_manager.get_session(user.id)

    logger.debug("Received callback query '%s' from user %s", data, user.id)

    # 1. Cancel running agent execution
    if data == "cancel_run":
        if session.is_running() and session.current_task:
            session.current_task.cancel()
            await query.answer("🛑 Sent cancellation signal to agent.")
            try:
                await query.edit_message_text(
                    "🛑 <b>Agent execution cancelled by user.</b>",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        else:
            await query.answer("No active task running.", show_alert=False)

    # 2. Reset conversation
    elif data == "reset_conv":
        session_manager.reset_conversation(user.id)
        await query.answer("✨ Started new conversation!")
        await query.edit_message_text(
            "✨ <b>Conversation reset.</b> Next message will start a fresh agent session.\n"
            f"📁 <b>Working Directory:</b> <code>{escape_html(session.working_dir)}</code>",
            parse_mode="HTML",
        )

    # 3. Model selector menu
    elif data == "menu_models":
        buttons = []
        for model_id, label in config.available_models.items():
            check = "✓ " if session.model == model_id else ""
            buttons.append([InlineKeyboardButton(f"{check}{label}", callback_data=f"set_model:{model_id}")])
        buttons.append([InlineKeyboardButton("🔙 Back to Status", callback_data="show_status")])

        await query.answer()
        await query.edit_message_text(
            "🤖 <b>Select Agent Model:</b>\n\nChoose the model to use for subsequent prompts:",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
        )

    # 4. Set model
    elif data.startswith("set_model:"):
        model_id = data.split(":", 1)[1]
        session_manager.set_model(user.id, model_id)
        label = config.available_models.get(model_id, model_id)
        await query.answer(f"Switched model to {label}")
        await _show_status_view(query, user.id)

    # 5. Effort selector menu
    elif data == "menu_effort":
        efforts = [
            ("low", "🌱 Low Effort (Faster, less reasoning)"),
            ("medium", "⚖️ Medium Effort (Balanced)"),
            ("high", "🧠 High Effort (Deep reasoning)"),
        ]
        buttons = []
        for val, label in efforts:
            check = "✓ " if session.effort == val else ""
            buttons.append([InlineKeyboardButton(f"{check}{label}", callback_data=f"set_effort:{val}")])
        buttons.append([InlineKeyboardButton("🔙 Back to Status", callback_data="show_status")])

        await query.answer()
        await query.edit_message_text(
            "🧠 <b>Select Reasoning Effort:</b>",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
        )

    # 6. Set effort
    elif data.startswith("set_effort:"):
        effort_val = data.split(":", 1)[1]
        session_manager.set_effort(user.id, effort_val)
        await query.answer(f"Reasoning effort set to {effort_val.upper()}")
        await _show_status_view(query, user.id)

    # 7. Mode selector menu
    elif data == "menu_mode":
        modes = [
            ("accept-edits", "✏️ Accept Edits (Allows file edits & tool commands)"),
            ("plan", "📋 Plan Mode (Read-only analysis & planning)"),
        ]
        buttons = []
        for m_val, m_label in modes:
            check = "✓ " if session.mode == m_val else ""
            buttons.append([InlineKeyboardButton(f"{check}{m_label}", callback_data=f"set_mode:{m_val}")])
        buttons.append([InlineKeyboardButton("🔙 Back to Status", callback_data="show_status")])

        await query.answer()
        await query.edit_message_text(
            "🎯 <b>Select Execution Mode:</b>",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
        )

    # 8. Set mode
    elif data.startswith("set_mode:"):
        mode_val = data.split(":", 1)[1]
        session_manager.set_mode(user.id, mode_val)
        await query.answer(f"Mode set to {mode_val}")
        await _show_status_view(query, user.id)

    # 9. Toggle Permissions
    elif data == "toggle_perms":
        new_val = session_manager.toggle_auto_approve(user.id)
        state_str = "Auto-Approve Enabled" if new_val else "Standard Prompting"
        await query.answer(f"Tool permissions: {state_str}")
        await _show_status_view(query, user.id)

    # 10. Show status
    elif data == "show_status":
        await query.answer()
        await _show_status_view(query, user.id)

    # 11. Pagination for sessions list
    elif data.startswith("page_conv:"):
        page = int(data.split(":", 1)[1])
        await query.answer()
        await _show_conversations_page(query, user.id, page=page)

    # 12. Resume conversation
    elif data.startswith("resume_conv:"):
        conv_id = data.split(":", 1)[1]
        session_manager.set_active_conversation(user.id, conv_id)
        await query.answer("Session resumed!")
        await query.edit_message_text(
            f"🔄 <b>Resumed Conversation:</b> <code>{conv_id}</code>\n\n"
            f"📁 <b>Working Directory:</b> <code>{escape_html(session.working_dir)}</code>\n"
            f"🤖 <b>Model:</b> <code>{escape_html(session.model)}</code>\n\n"
            "Send your next message to continue this conversation.",
            parse_mode="HTML",
        )

    # 13. Workspace menu
    elif data == "menu_workspaces":
        await query.answer()
        await _show_workspaces_menu(query, user.id)

    # 14. Set workspace
    elif data.startswith("set_ws:"):
        idx = int(data.split(":", 1)[1])
        avail = session_manager.get_available_workspaces(user.id)
        if 0 <= idx < len(avail):
            target_path = avail[idx]
            ok, res = session_manager.set_working_dir(user.id, target_path)
            if ok:
                await query.answer(f"Workspace set to {Path(res).name}!")
            else:
                await query.answer(f"Error: {res}", show_alert=True)
        await _show_status_view(query, user.id)

    else:
        await query.answer()


async def _show_workspaces_menu(query, user_id: int) -> None:
    """Render interactive workspace selection menu."""
    session = session_manager.get_session(user_id)
    workspaces = session_manager.get_available_workspaces(user_id)

    buttons = []
    for i, ws in enumerate(workspaces[:12]):
        folder_name = Path(ws).name or ws
        is_active = (ws == session.working_dir)
        check = "✓ " if is_active else ""
        btn_text = f"{check}📁 {folder_name}"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"set_ws:{i}")])

    buttons.append([InlineKeyboardButton("🔙 Back to Status", callback_data="show_status")])

    text = (
        "📁 <b>Select Workspace Directory</b>\n\n"
        f"<b>Current:</b> <code>{escape_html(session.working_dir)}</code>\n\n"
        "Tap a detected project or directory to switch to it:\n"
        "<i>(Or use <code>/cd /path/to/project</code> for any custom path)</i>"
    )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML",
    )


async def _show_status_view(query, user_id: int) -> None:
    """Render and edit message to show the current session status dashboard."""
    session = session_manager.get_session(user_id)
    model_name = config.available_models.get(session.model, session.model)

    conv_display = (
        f"<code>{session.active_conversation_id}</code>"
        if session.active_conversation_id
        else "<i>(None - new session on next prompt)</i>"
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
            InlineKeyboardButton("📁 Change Workspace", callback_data="menu_workspaces"),
            InlineKeyboardButton("🤖 Change Model", callback_data="menu_models"),
        ],
        [
            InlineKeyboardButton("🧠 Reasoning Effort", callback_data="menu_effort"),
            InlineKeyboardButton("🎯 Execution Mode", callback_data="menu_mode"),
        ],
        [
            InlineKeyboardButton("🛡️ Toggle Auto-Approve", callback_data="toggle_perms"),
            InlineKeyboardButton("✨ New Conversation", callback_data="reset_conv"),
        ],
        [
            InlineKeyboardButton("📜 Browse Saved Sessions", callback_data="page_conv:0"),
        ],
    ]

    await query.edit_message_text(
        status_text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML",
    )


async def _show_conversations_page(query, user_id: int, page: int = 0, page_size: int = 5) -> None:
    """Render paginated list of conversations stored in brain storage."""
    all_convs = session_manager.list_saved_conversations(limit=50)
    session = session_manager.get_session(user_id)

    if not all_convs:
        await query.edit_message_text(
            "📜 <b>No saved conversations found in brain storage.</b>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="show_status")]]),
            parse_mode="HTML",
        )
        return

    total_pages = (len(all_convs) + page_size - 1) // page_size
    page = max(0, min(page, total_pages - 1))
    start_idx = page * page_size
    page_items = all_convs[start_idx : start_idx + page_size]

    text_lines = [
        f"📜 <b>Saved Conversations (Page {page + 1}/{total_pages}):</b>\n",
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

    # Nav row
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page_conv:{page - 1}"))
    nav_row.append(InlineKeyboardButton("🔙 Dashboard", callback_data="show_status"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"page_conv:{page + 1}"))
    buttons.append(nav_row)

    await query.edit_message_text(
        "\n".join(text_lines),
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML",
    )
