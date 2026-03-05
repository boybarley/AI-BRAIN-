"""
api_server.py — FastAPI API Server
====================================
Server utama yang mengekspos:
  - /api/v1/query          → Internal API untuk direct query
  - /api/v1/task/{id}      → Cek status task
  - /webhooks/messenger    → Facebook Messenger webhook
  - /webhooks/telegram     → Telegram webhook
  - /webhooks/whatsapp     → WhatsApp Business API webhook
  - /health                → Health check

Semua pemrosesan berat di-offload ke Celery worker.
"""

import hmac
import hashlib
import logging
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

from core_rag import load_config
from tasks import process_rag_query

# ─── Logging ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ─── Config ──────────────────────────────────────────────────
config = load_config()

# ─── FastAPI App ─────────────────────────────────────────────
app = FastAPI(
    title="AI Brain — Multi-Platform RAG API",
    description=(
        "Otak AI berbasis RAG yang modular. "
        "Mendukung Messenger, Telegram, dan WhatsApp."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


# ══════════════════════════════════════════════════════════════
#  REQUEST / RESPONSE MODELS
# ══════════════════════════════════════════════════════════════

class QueryRequest(BaseModel):
    """Request body untuk /api/v1/query."""
    query: str
    conversation_id: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "query": "Apa itu machine learning?",
                "conversation_id": "user_123",
            }
        }


class TaskResponse(BaseModel):
    """Response setelah task di-submit."""
    status: str
    task_id: str
    message: str


# ══════════════════════════════════════════════════════════════
#  HELPER: SIGNATURE VERIFICATION
# ══════════════════════════════════════════════════════════════

def verify_messenger_signature(
    payload: bytes, signature: str, app_secret: str
) -> bool:
    """Verify Facebook Messenger X-Hub-Signature-256."""
    if not app_secret or not signature:
        return True  # Skip if not configured
    
    expected = "sha256=" + hmac.new(
        app_secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


# ══════════════════════════════════════════════════════════════
#  INTERNAL API ENDPOINTS
# ══════════════════════════════════════════════════════════════

@app.post(
    "/api/v1/query",
    response_model=TaskResponse,
    status_code=202,
    tags=["Internal API"],
    summary="Submit RAG query",
)
async def submit_query(request: QueryRequest):
    """
    Submit query untuk diproses secara asinkron oleh RAG engine.
    
    Mengembalikan `202 Accepted` dengan `task_id` yang bisa di-poll
    melalui `/api/v1/task/{task_id}`.
    """
    task = process_rag_query.delay(
        query=request.query,
        conversation_id=request.conversation_id,
    )

    logger.info(
        f"Query submitted: task_id={task.id}, "
        f"query='{request.query[:60]}...'"
    )

    return TaskResponse(
        status="accepted",
        task_id=task.id,
        message="Query submitted for processing",
    )


@app.get(
    "/api/v1/task/{task_id}",
    tags=["Internal API"],
    summary="Check task status",
)
async def get_task_status(task_id: str):
    """
    Cek status dan hasil dari task yang sudah di-submit.
    
    States: PENDING → STARTED → SUCCESS / FAILURE
    """
    result = process_rag_query.AsyncResult(task_id)

    response = {
        "task_id": task_id,
        "status": result.state.lower(),
    }

    if result.state == "SUCCESS":
        response["result"] = result.result
    elif result.state == "FAILURE":
        response["error"] = str(result.info)
    elif result.state == "STARTED":
        response["message"] = "Task is being processed..."
    else:
        response["message"] = "Task is queued, waiting for worker..."

    return response


# ══════════════════════════════════════════════════════════════
#  WEBHOOK: FACEBOOK MESSENGER
# ══════════════════════════════════════════════════════════════

@app.get(
    "/webhooks/messenger",
    tags=["Webhooks"],
    summary="Messenger verification challenge",
)
async def messenger_verify(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    """
    Facebook Messenger webhook verification (GET).
    Facebook mengirim challenge saat setup webhook.
    """
    verify_token = config.get("messenger_verify_token", "")

    if hub_mode == "subscribe" and hub_verify_token == verify_token:
        logger.info("✅ Messenger webhook verified successfully")
        return PlainTextResponse(content=hub_challenge)

    logger.warning(
        f"❌ Messenger verification failed: "
        f"mode={hub_mode}, token_match={hub_verify_token == verify_token}"
    )
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post(
    "/webhooks/messenger",
    tags=["Webhooks"],
    summary="Messenger incoming messages",
)
async def messenger_webhook(request: Request):
    """
    Handle incoming Facebook Messenger messages.
    
    Alur:
      1. (Optional) Verify signature
      2. Parse payload → extract sender_id & text
      3. Submit Celery task
      4. Return 200 OK immediately
    """
    body_bytes = await request.body()

    # Optional signature verification
    app_secret = config.get("messenger_app_secret", "")
    signature = request.headers.get("X-Hub-Signature-256", "")

    if app_secret and not verify_messenger_signature(
        body_bytes, signature, app_secret
    ):
        logger.warning("Messenger signature verification failed")
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Parse payload
    try:
        body = await request.json()

        for entry in body.get("entry", []):
            for event in entry.get("messaging", []):
                sender_id = event.get("sender", {}).get("id")
                message = event.get("message", {})
                text = message.get("text")

                # Skip non-text messages (images, stickers, etc.)
                if not sender_id or not text:
                    continue

                # Skip echo messages (sent by the page itself)
                if message.get("is_echo"):
                    continue

                logger.info(
                    f"📩 Messenger message from {sender_id}: "
                    f"'{text[:50]}...'"
                )

                # Queue async processing
                process_rag_query.delay(
                    query=text,
                    conversation_id=f"messenger_{sender_id}",
                    platform="messenger",
                    user_id=sender_id,
                )

    except Exception as e:
        logger.error(f"Error parsing Messenger webhook: {e}", exc_info=True)

    # ALWAYS return 200 OK to Facebook (to avoid retries)
    return JSONResponse(content={"status": "ok"}, status_code=200)


# ══════════════════════════════════════════════════════════════
#  WEBHOOK: TELEGRAM
# ══════════════════════════════════════════════════════════════

@app.post(
    "/webhooks/telegram",
    tags=["Webhooks"],
    summary="Telegram incoming messages",
)
async def telegram_webhook(request: Request):
    """
    Handle incoming Telegram messages.
    
    Telegram tidak memiliki mekanisme verifikasi challenge;
    verifikasi dilakukan saat setup webhook melalui Bot API.
    """
    try:
        body = await request.json()

        # Support both message and edited_message
        message = body.get("message") or body.get("edited_message")
        if not message:
            return JSONResponse(content={"status": "ok"}, status_code=200)

        chat = message.get("chat", {})
        chat_id = str(chat.get("id", ""))
        text = message.get("text", "")

        if not chat_id or not text:
            return JSONResponse(content={"status": "ok"}, status_code=200)

        logger.info(
            f"📩 Telegram message from {chat_id}: '{text[:50]}...'"
        )

        # Handle /start command
        if text.strip() == "/start":
            from platform_adapters import send_telegram_reply
            send_telegram_reply(
                chat_id,
                "👋 Halo! Saya adalah asisten AI. "
                "Silakan ajukan pertanyaan Anda, dan saya akan "
                "menjawab berdasarkan database pengetahuan saya.",
                [],
            )
            return JSONResponse(content={"status": "ok"}, status_code=200)

        # Handle /help command
        if text.strip() == "/help":
            from platform_adapters import send_telegram_reply
            send_telegram_reply(
                chat_id,
                "💡 Cara menggunakan bot:\n\n"
                "Cukup kirim pertanyaan Anda dalam bahasa Indonesia. "
                "Saya akan mencari jawabannya dari database dokumen "
                "dan website yang sudah diindeks.\n\n"
                "Contoh: \"Apa saja layanan yang tersedia?\"",
                [],
            )
            return JSONResponse(content={"status": "ok"}, status_code=200)

        # Queue RAG processing
        process_rag_query.delay(
            query=text,
            conversation_id=f"telegram_{chat_id}",
            platform="telegram",
            user_id=chat_id,
        )

    except Exception as e:
        logger.error(f"Error parsing Telegram webhook: {e}", exc_info=True)

    return JSONResponse(content={"status": "ok"}, status_code=200)


# ══════════════════════════════════════════════════════════════
#  WEBHOOK: WHATSAPP BUSINESS API
# ══════════════════════════════════════════════════════════════

@app.get(
    "/webhooks/whatsapp",
    tags=["Webhooks"],
    summary="WhatsApp verification challenge",
)
async def whatsapp_verify(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    """WhatsApp webhook verification (GET) — mirip dengan Messenger."""
    verify_token = config.get("whatsapp_verify_token", "")

    if hub_mode == "subscribe" and hub_verify_token == verify_token:
        logger.info("✅ WhatsApp webhook verified successfully")
        return PlainTextResponse(content=hub_challenge)

    raise HTTPException(status_code=403, detail="Verification failed")


@app.post(
    "/webhooks/whatsapp",
    tags=["Webhooks"],
    summary="WhatsApp incoming messages",
)
async def whatsapp_webhook(request: Request):
    """Handle incoming WhatsApp Business API messages."""
    try:
        body = await request.json()

        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                # Skip status updates (sent, delivered, read)
                if "statuses" in value:
                    continue

                for msg in value.get("messages", []):
                    phone = msg.get("from", "")
                    msg_type = msg.get("type", "")

                    if msg_type == "text":
                        text = msg.get("text", {}).get("body", "")

                        if phone and text:
                            logger.info(
                                f"📩 WhatsApp message from {phone}: "
                                f"'{text[:50]}...'"
                            )

                            process_rag_query.delay(
                                query=text,
                                conversation_id=f"whatsapp_{phone}",
                                platform="whatsapp",
                                user_id=phone,
                            )

    except Exception as e:
        logger.error(
            f"Error parsing WhatsApp webhook: {e}", exc_info=True
        )

    return JSONResponse(content={"status": "ok"}, status_code=200)


# ══════════════════════════════════════════════════════════════
#  HEALTH & UTILITY
# ══════════════════════════════════════════════════════════════

@app.get("/health", tags=["Utility"], summary="Health check")
async def health_check():
    """Server health check endpoint."""
    return {
        "status": "healthy",
        "service": "AI Brain API",
        "version": "1.0.0",
    }


@app.post(
    "/api/v1/reload",
    tags=["Utility"],
    summary="Reload RAG engine cache",
)
async def reload_engine():
    """
    Reset cache internal RAG engine.
    Berguna setelah ingest data baru tanpa restart service.
    """
    from core_rag import reload_cache
    reload_cache()
    return {"status": "ok", "message": "Engine cache cleared"}


# ──────────────────────────────────────────────────────────────
#  Entry point
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api_server:app",
        host=config.get("server_host", "0.0.0.0"),
        port=config.get("server_port", 5000),
        reload=False,
        log_level="info",
    )
