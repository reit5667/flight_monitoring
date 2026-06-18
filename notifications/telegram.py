import logging
import os

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

logger = logging.getLogger(__name__)


async def send_notification(message: str) -> bool:
    """Send HTML-formatted message to Telegram chat. Returns True on success."""
    if not message:
        logger.warning("send_notification called with empty message")
        return False

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        return False

    try:
        async with Bot(token=token) as bot:
            await bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode=ParseMode.HTML,
            )
        logger.info("Telegram notification sent (%d chars)", len(message))
        return True
    except TelegramError as e:
        logger.error("Telegram API error: %s", e)
        return False
    except Exception:
        logger.exception("Unexpected error sending Telegram notification")
        return False
