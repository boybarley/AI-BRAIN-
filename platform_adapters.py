"""
platform_adapters.py — Platform-Specific Message Adapters
==========================================================
Fungsi-fungsi terpisah untuk mengirim pesan ke setiap platform.
Setiap adapter:
  - Membaca kredensial dari config.yaml
  - Memformat jawaban + sumber
  - Menangani batasan panjang karakter per platform
  - Retry dengan logging
"""

import logging
from typing import List

import requests

from core_rag import get_config

# ─── Logging ─────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────
MESSENGER_CHAR_LIMIT = 2000
TELEGRAM_CHAR_LIMIT = 4096
WHATSAPP_CHAR_LIMIT = 4096


# ══════════════════════════════════════════════════════════════
#  MESSAGE FORMATTING
# ══════════════════════════════════════════════════════════════

def format_message_with_sources(
    answer: str, sources: List[str]
) -> str:
    """
    Format jawaban + sumber.
    Hanya tambahkan block sumber jika belum ada di dalam jawaban.
    """
    message = answer.strip()

    # Check if sources are already included in the answer text
    if sources:
        sources_already_present = all(
            source in message for source in sources
        )

        if not sources_already_present:
            message += "\n\n📚 **Sumber:**"
            for source in sources:
                message += f"\n• {source}"

    return message


def split_message(text: str, limit: int) -> List[str]:
    """Split long messages into chunks respecting char limit."""
    if len(text) <= limit:
        return [text]

    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break

        # Try to split at newline
        split_pos = text.rfind("\n", 0, limit)
        if split_pos == -1:
            # Try to split at space
            split_pos = text.rfind(" ", 0, limit)
        if split_pos == -1:
            # Hard split
            split_pos = limit

        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip()

    return chunks


# ══════════════════════════════════════════════════════════════
#  FACEBOOK MESSENGER ADAPTER
# ══════════════════════════════════════════════════════════════

def send_messenger_reply(
    user_id: str, answer: str, sources: List[str]
) -> bool:
    """
    Kirim balasan ke Facebook Messenger.
    
    API Reference: https://developers.facebook.com/docs/messenger-platform
    """
    config = get_config()
    access_token = config.get("messenger_page_access_token", "")

    if not access_token:
        logger.error("Messenger page access token not configured")
        return False

    message_text = format_message_with_sources(answer, sources)
    chunks = split_message(message_text, MESSENGER_CHAR_LIMIT)

    url = (
        "https://graph.facebook.com/v18.0/me/messages"
        f"?access_token={access_token}"
    )

    for i, chunk in enumerate(chunks):
        payload = {
            "recipient": {"id": user_id},
            "message": {"text": chunk},
            "messaging_type": "RESPONSE",
        }

        try:
            resp = requests.post(url, json=payload, timeout=30)

            if resp.status_code != 200:
                logger.error(
                    f"Messenger API error [{resp.status_code}]: "
                    f"{resp.text}"
                )
                return False

            logger.debug(
                f"Messenger chunk {i+1}/{len(chunks)} sent to {user_id}"
            )

        except requests.RequestException as e:
            logger.error(f"Messenger send failed: {e}")
            return False

    logger.info(f"✅ Messenger reply sent to {user_id}")
    return True


# ══════════════════════════════════════════════════════════════
#  TELEGRAM ADAPTER
# ══════════════════════════════════════════════════════════════

def send_telegram_reply(
    chat_id: str, answer: str, sources: List[str]
) -> bool:
    """
    Kirim balasan ke Telegram.
    
    Mencoba Markdown dulu; jika gagal, fallback ke plain text.
    API Reference: https://core.telegram.org/bots/api
    """
    config = get_config()
    bot_token = config.get("telegram_bot_token", "")

    if not bot_token:
        logger.error("Telegram bot token not configured")
        return False

    message_text = format_message_with_sources(answer, sources)
    chunks = split_message(message_text, TELEGRAM_CHAR_LIMIT)

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    for i, chunk in enumerate(chunks):
        # Try with Markdown first
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "Markdown",
        }

        try:
            resp = requests.post(url, json=payload, timeout=30)

            # If Markdown parsing fails, retry without parse_mode
            if resp.status_code != 200:
                logger.debug(
                    f"Telegram Markdown failed, retrying plain text..."
                )
                payload.pop("parse_mode")
                resp = requests.post(url, json=payload, timeout=30)

                if resp.status_code != 200:
                    logger.error(
                        f"Telegram API error [{resp.status_code}]: "
                        f"{resp.text}"
                    )
                    return False

            logger.debug(
                f"Telegram chunk {i+1}/{len(chunks)} sent to {chat_id}"
            )

        except requests.RequestException as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    logger.info(f"✅ Telegram reply sent to {chat_id}")
    return True


# ══════════════════════════════════════════════════════════════
#  WHATSAPP BUSINESS API ADAPTER
# ══════════════════════════════════════════════════════════════

def send_whatsapp_reply(
    phone_number: str, answer: str, sources: List[str]
) -> bool:
    """
    Kirim balasan ke WhatsApp via Cloud API.
    
    API Reference: https://developers.facebook.com/docs/whatsapp/cloud-api
    """
    config = get_config()
    api_token = config.get("whatsapp_api_token", "")
    phone_id = config.get("whatsapp_phone_number_id", "")

    if not api_token or not phone_id:
        logger.error("WhatsApp API credentials not configured")
        return False

    message_text = format_message_with_sources(answer, sources)
    chunks = split_message(message_text, WHATSAPP_CHAR_LIMIT)

    url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }

    for i, chunk in enumerate(chunks):
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "text",
            "text": {"body": chunk},
        }

        try:
            resp = requests.post(
                url, json=payload, headers=headers, timeout=30
            )

            if resp.status_code not in (200, 201):
                logger.error(
                    f"WhatsApp API error [{resp.status_code}]: "
                    f"{resp.text}"
                )
                return False

            logger.debug(
                f"WhatsApp chunk {i+1}/{len(chunks)} sent to {phone_number}"
            )

        except requests.RequestException as e:
            logger.error(f"WhatsApp send failed: {e}")
            return False

    logger.info(f"✅ WhatsApp reply sent to {phone_number}")
    return True


# ══════════════════════════════════════════════════════════════
#  ROUTER / DISPATCHER
# ══════════════════════════════════════════════════════════════

_ADAPTERS = {
    "messenger": send_messenger_reply,
    "telegram": send_telegram_reply,
    "whatsapp": send_whatsapp_reply,
}


def send_platform_reply(
    platform: str,
    user_id: str,
    answer: str,
    sources: List[str],
) -> bool:
    """
    Route balasan ke adapter platform yang sesuai.
    
    Args:
        platform: "messenger" | "telegram" | "whatsapp"
        user_id:  Platform-specific user identifier
        answer:   Teks jawaban dari RAG engine
        sources:  List of source URLs/filenames
    
    Returns:
        True jika berhasil terkirim, False jika gagal
    """
    adapter = _ADAPTERS.get(platform)

    if adapter is None:
        logger.error(
            f"Unknown platform: '{platform}'. "
            f"Supported: {list(_ADAPTERS.keys())}"
        )
        return False

    return adapter(user_id, answer, sources)
