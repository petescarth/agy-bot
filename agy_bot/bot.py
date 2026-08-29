"""Telegram Application builder and handler registration."""

from __future__ import annotations

import logging
from typing import List

from telegram import BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from agy_bot.config import config
from agy_bot.handlers.callback_handlers import handle_callback_query
from agy_bot.handlers.command_handlers import (
    cd_cmd,
    effort_cmd,
    git_cmd,
    help_cmd,
    ls_cmd,
    mode_cmd,
    model_cmd,
    new_cmd,
    perms_cmd,
    pwd_cmd,
    resume_cmd,
    sessions_cmd,
    start_cmd,
    status_cmd,
    stop_cmd,
)
from agy_bot.handlers.message_handlers import (
    handle_document_message,
    handle_photo_message,
    handle_prompt_message,
)

logger = logging.getLogger(__name__)


async def post_init_setup(app: Application) -> None:
    """Setup bot commands menu for Telegram UI autocomplete."""
    commands = [
        BotCommand("start", "Start bot & view overview"),
        BotCommand("status", "View control dashboard & stats"),
        BotCommand("new", "Start a fresh conversation"),
        BotCommand("sessions", "Browse & resume past sessions"),
        BotCommand("model", "Change AI model"),
        BotCommand("effort", "Adjust reasoning effort"),
        BotCommand("mode", "Switch execution mode (accept-edits/plan)"),
        BotCommand("perms", "Toggle auto-approval permissions"),
        BotCommand("cd", "Change working directory"),
        BotCommand("pwd", "Show current workspace path"),
        BotCommand("ls", "List files in workspace"),
        BotCommand("git", "Show git status & recent commits"),
        BotCommand("stop", "Cancel currently executing prompt"),
        BotCommand("help", "View full command guide"),
    ]
    try:
        await app.bot.set_my_commands(commands)
        logger.info("Configured %d Telegram autocomplete commands.", len(commands))
    except Exception as e:
        logger.warning("Could not set bot commands menu: %s", e)


async def error_handler(update: object, context) -> None:
    """Global unhandled exception handler."""
    logger.error("Exception handling update %s: %s", update, context.error, exc_info=context.error)


def create_application() -> Application:
    """Instantiate and configure the Telegram application."""
    errors = config.validate()
    if errors:
        for err in errors:
            logger.error("Config validation error: %s", err)

    app = ApplicationBuilder().token(config.telegram_bot_token).post_init(post_init_setup).build()

    # Command Handlers
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("new", new_cmd))
    app.add_handler(CommandHandler("clear", new_cmd))
    app.add_handler(CommandHandler("sessions", sessions_cmd))
    app.add_handler(CommandHandler("resume", resume_cmd))
    app.add_handler(CommandHandler("cd", cd_cmd))
    app.add_handler(CommandHandler("pwd", pwd_cmd))
    app.add_handler(CommandHandler("ls", ls_cmd))
    app.add_handler(CommandHandler("git", git_cmd))
    app.add_handler(CommandHandler("model", model_cmd))
    app.add_handler(CommandHandler("effort", effort_cmd))
    app.add_handler(CommandHandler("mode", mode_cmd))
    app.add_handler(CommandHandler("perms", perms_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("cancel", stop_cmd))

    # Callback Query Handlers (Inline Buttons)
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    # Message Handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prompt_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))

    # Global Error Handler
    app.add_error_handler(error_handler)

    return app
