"""Prompt, media, and document message handlers with live streaming updates."""

from __future__ import annotations

import asyncio
import io
import logging
import os
import time
from typing import List, Optional

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    constants,
)
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from agy_bot.agy_client import (
    InitEvent,
    ResultEvent,
    StepUpdateEvent,
    agy_client,
)
from agy_bot.config import config
from agy_bot.formatting import (
    escape_html,
    format_duration,
    format_progress_message,
    format_stats_footer,
    format_tool_call_summary,
    split_text_smartly,
)
from agy_bot.session_manager import session_manager

logger = logging.getLogger(__name__)


def is_authorized(user_id: int) -> bool:
    return user_id in config.allowed_user_ids


async def handle_prompt_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages sent to the bot by forwarding to agy CLI."""
    user = update.effective_user
    if not user or not is_authorized(user.id):
        if update.message:
            await update.message.reply_text("⛔ Unauthorized user.")
        return

    session = session_manager.get_session(user.id)
    if session.is_running():
        buttons = [[InlineKeyboardButton("🛑 Cancel Current Task", callback_data="cancel_run")]]
        if update.message:
            await update.message.reply_text(
                "⏳ <b>Agent is currently executing a previous task.</b>\n"
                "Please wait for it to complete or cancel it:",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode="HTML",
            )
        return

    prompt_text = update.message.text.strip() if update.message and update.message.text else ""
    if not prompt_text:
        return

    # Spawn asynchronous execution task
    task = asyncio.create_task(_run_agent_flow(update, context, prompt_text, user.id))
    session.current_task = task


async def handle_document_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle uploaded documents/files by saving to workspace and informing agent."""
    user = update.effective_user
    if not user or not is_authorized(user.id):
        return

    session = session_manager.get_session(user.id)
    if session.is_running():
        if update.message:
            await update.message.reply_text("⏳ Agent is busy. Please wait for current task to complete.")
        return

    doc = update.message.document if update.message else None
    if not doc:
        return

    file_name = doc.file_name or f"upload_{int(time.time())}"
    caption = update.message.caption or f"Please inspect the uploaded file '{file_name}'."

    dest_dir = session.working_dir
    dest_path = os.path.join(dest_dir, file_name)

    try:
        tfile = await doc.get_file()
        await tfile.download_to_drive(dest_path)

        prompt = f"The user uploaded the file '{file_name}' (saved to '{dest_path}').\nUser Instruction: {caption}"
        if update.message:
            await update.message.reply_text(f"📥 Saved <code>{escape_html(file_name)}</code> to workspace. Starting agent...", parse_mode="HTML")

        task = asyncio.create_task(_run_agent_flow(update, context, prompt, user.id))
        session.current_task = task
    except Exception as e:
        logger.exception("Error saving uploaded document: %s", e)
        if update.message:
            await update.message.reply_text(f"❌ Failed to save uploaded file: {escape_html(str(e))}", parse_mode="HTML")


async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle uploaded photo by saving to workspace and informing agent."""
    user = update.effective_user
    if not user or not is_authorized(user.id):
        return

    session = session_manager.get_session(user.id)
    if session.is_running():
        if update.message:
            await update.message.reply_text("⏳ Agent is busy. Please wait for current task to complete.")
        return

    photos = update.message.photo if update.message else None
    if not photos:
        return

    # Take highest resolution photo
    photo = photos[-1]
    file_name = f"photo_{int(time.time())}.jpg"
    caption = update.message.caption or f"Please analyze this uploaded image '{file_name}'."

    dest_dir = session.working_dir
    dest_path = os.path.join(dest_dir, file_name)

    try:
        tfile = await photo.get_file()
        await tfile.download_to_drive(dest_path)

        prompt = f"The user uploaded the image '{file_name}' (saved to '{dest_path}').\nUser Instruction: {caption}"
        if update.message:
            await update.message.reply_text(f"🖼️ Saved image to workspace. Starting agent...", parse_mode="HTML")

        task = asyncio.create_task(_run_agent_flow(update, context, prompt, user.id))
        session.current_task = task
    except Exception as e:
        logger.exception("Error saving uploaded photo: %s", e)
        if update.message:
            await update.message.reply_text(f"❌ Failed to save uploaded photo: {escape_html(str(e))}", parse_mode="HTML")


async def _run_agent_flow(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    prompt: str,
    user_id: int,
) -> None:
    """Core execution engine handling streaming, progress feedback, and completion."""
    session = session_manager.get_session(user_id)
    start_time = time.time()
    chat_id = update.effective_chat.id if update.effective_chat else user_id

    # 1. Send initial status message
    cancel_keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🛑 Cancel Execution", callback_data="cancel_run")]]
    )

    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="⚡ <b>Antigravity Agent Working...</b>\n<i>Initializing runtime environment</i>",
        reply_markup=cancel_keyboard,
        parse_mode="HTML",
    )

    tool_history: List[str] = []
    accumulated_text: List[str] = []
    current_action = "Analyzing workspace and prompt"
    last_update_time = time.time()
    result_event: Optional[ResultEvent] = None

    try:
        # Keep sending typing action in background
        async def keep_typing():
            while True:
                try:
                    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)
                except Exception:
                    pass
                await asyncio.sleep(4.5)

        typing_task = asyncio.create_task(keep_typing())

        try:
            async for event in agy_client.execute_stream(prompt, session):
                now = time.time()

                if isinstance(event, InitEvent):
                    current_action = f"Initialized ({len(event.tools)} tools available)"

                elif isinstance(event, StepUpdateEvent):
                    if event.step_type == "tool":
                        tool_desc = format_tool_call_summary(event.tool_name or "tool", event.tool_info)
                        if event.state == "ACTIVE":
                            current_action = f"Running {tool_desc}"
                        elif event.state == "DONE":
                            tool_history.append(f"{tool_desc} ({format_duration(event.duration_seconds)})")
                            current_action = f"Finished {tool_desc}"

                    elif event.step_type == "agent_response":
                        current_action = "Generating response..."
                        if event.text_delta:
                            accumulated_text.append(event.text_delta)

                    elif event.step_type == "system_message":
                        current_action = "Processing system update..."

                elif isinstance(event, ResultEvent):
                    result_event = event
                    break

                # Throttle message edits to respect Telegram rate limits
                if (now - last_update_time) >= config.stream_update_interval:
                    elapsed = now - start_time
                    partial_preview = "".join(accumulated_text) if config.stream_live_preview else ""
                    progress_text = format_progress_message(
                        current_action=current_action,
                        tool_history=tool_history,
                        elapsed_seconds=elapsed,
                        partial_text=partial_preview,
                        model=session.model,
                    )
                    try:
                        await status_msg.edit_text(
                            progress_text,
                            reply_markup=cancel_keyboard,
                            parse_mode="HTML",
                        )
                        last_update_time = now
                    except BadRequest:
                        pass  # Ignore "message is not modified" errors
                    except Exception as e:
                        logger.debug("Failed updating progress message: %s", e)

        finally:
            typing_task.cancel()

        total_duration = time.time() - start_time

        # 2. Render Final Output
        if result_event and result_event.status == "SUCCESS":
            final_text = result_event.response or "".join(accumulated_text) or "Task completed with empty output."
            footer = format_stats_footer(
                duration=result_event.duration_seconds or total_duration,
                usage=result_event.usage,
                conversation_id=result_event.conversation_id or session.active_conversation_id,
                model=session.model,
            )

            # Try deleting status message before sending final clean output
            try:
                await status_msg.delete()
            except Exception:
                pass

            # Deliver response (split if needed or send as attachment if huge)
            await _deliver_response(context.bot, chat_id, final_text, footer)

        elif result_event and result_event.status == "ERROR":
            err_msg = result_event.error_message or "Unknown execution error."
            try:
                await status_msg.edit_text(
                    f"❌ <b>Execution Error:</b>\n<pre>{escape_html(err_msg)}</pre>\n\n"
                    f"⏱️ Elapsed: {format_duration(total_duration)}",
                    parse_mode="HTML",
                )
            except Exception:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ <b>Execution Error:</b>\n<pre>{escape_html(err_msg)}</pre>",
                    parse_mode="HTML",
                )

        else:
            # Fallback if no result event reached
            final_text = "".join(accumulated_text) or "Command finished."
            footer = format_stats_footer(total_duration, conversation_id=session.active_conversation_id, model=session.model)
            try:
                await status_msg.delete()
            except Exception:
                pass
            await _deliver_response(context.bot, chat_id, final_text, footer)

    except asyncio.CancelledError:
        logger.info("Agent run task was cancelled.")
        try:
            await status_msg.edit_text("🛑 <b>Execution was cancelled.</b>", parse_mode="HTML")
        except Exception:
            pass

    except Exception as exc:
        logger.exception("Exception in _run_agent_flow: %s", exc)
        try:
            await status_msg.edit_text(f"❌ <b>Unexpected error:</b> {escape_html(str(exc))}", parse_mode="HTML")
        except Exception:
            pass

    finally:
        session.current_task = None


async def _deliver_response(bot, chat_id: int, text: str, footer: str) -> None:
    """Deliver agent response chunks or file attachment safely."""
    # If text is extremely large (> 12,000 characters), send summary + markdown file attachment
    if len(text) > 12000:
        preview = text[:2000] + "\n\n... (Full response attached as document below)"
        msg_text = f"{preview}\n\n━━━━━━━━━━━━━━━\n{footer}"
        await _safe_send_message(bot, chat_id, msg_text)

        # Send file attachment
        doc_bytes = text.encode("utf-8")
        doc_io = io.BytesIO(doc_bytes)
        doc_io.name = f"agy_response_{int(time.time())}.md"
        await bot.send_document(
            chat_id=chat_id,
            document=doc_io,
            caption=f"📄 Full response ({len(doc_bytes)} bytes)",
        )
        return

    # Split into chunks under 3900 characters
    chunks = split_text_smartly(text, max_chunk_size=config.max_message_length)
    for i, chunk in enumerate(chunks):
        is_last = (i == len(chunks) - 1)
        if is_last and footer:
            chunk_with_footer = f"{chunk}\n\n━━━━━━━━━━━━━━━\n{footer}"
        else:
            chunk_with_footer = chunk

        await _safe_send_message(bot, chat_id, chunk_with_footer)


async def _safe_send_message(bot, chat_id: int, text: str) -> None:
    """Attempt sending as Markdown; fallback to plain text if parsing fails."""
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=constants.ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )
    except BadRequest:
        try:
            # Fallback to HTML mode with escaped tags
            await bot.send_message(
                chat_id=chat_id,
                text=escape_html(text),
                parse_mode=constants.ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception:
            # Final fallback: Plain unformatted text
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                disable_web_page_preview=True,
            )
    except Exception as e:
        logger.warning("Error sending message: %s", e)
