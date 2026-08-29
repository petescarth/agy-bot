#!/usr/bin/env python3
"""Main entrypoint to run the Antigravity Telegram Bot Bridge."""

import logging
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agy_bot.bot import create_application
from agy_bot.config import config


def main() -> None:
    # Setup structured logging
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    logger = logging.getLogger("agy_bot")

    errors = config.validate()
    if errors:
        logger.error("Configuration validation failed:")
        for err in errors:
            logger.error("  - %s", err)
        logger.error("Please update your .env file or environment variables before running.")
        sys.exit(1)

    logger.info("Starting Antigravity Telegram Bot Bridge...")
    logger.info("Default Working Directory: %s", config.default_working_dir)
    logger.info("Allowed User IDs: %s", config.allowed_user_ids)
    logger.info("Default Model: %s (Effort: %s)", config.default_model, config.default_effort)
    logger.info("Using agy binary: %s", config.agy_bin)

    app = create_application()
    print("\n🚀 Antigravity Telegram Bot is running! Press Ctrl+C to stop.\n")
    app.run_polling()


if __name__ == "__main__":
    main()
