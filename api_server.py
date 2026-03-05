"""
api_server.py — FastAPI REST API + Webhook Server
Endpoints: /health, /api/v1/query, /api/v1/task/{id}, /api/v1/query/sync
Webhooks:  /webhook/messenger, /webhook/telegram, /webhook/whatsapp
"""

import os
import logging
from typing import Optional

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_config() -> dict:
    with open(os.path.join(BASE_DIR, "config.yaml"), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ─── App ─────────────────────────────────────────────────────

app = FastAPI(
    title="AI Brain API",
    description="RAG-powered AI Assistant API",
    version="1.0.0",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Models ──────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str
    conversation_id: Optional[str] = None


class QueryResponse(BaseModel):
    status: str
    task_id: str
    message: str


# ─── Core Routes ─────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "AI Brain API",
        "version": "1.0.0",
    }


@app.post("/api/v1/query", response_model=QueryResponse)
async def submit_query(request: QueryRequest):
    """Submit a query for async processing via Celery."""
    from tasks import process_rag_query

    try:
        task = process_rag_query.delay(
            query=request.query,
            conversation_id=request.conversation_id,
        )
        return QueryResponse(
            status="accepted",
            task_id=task.id,
            message="Query submitted for processing",
        )
    except Exception as e:
        logger.error(f"Submit error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/task/{task_id}")
async def get_task_result(task_id: str):
    """Poll task result by ID."""
    from celery.result import AsyncResult
    from tasks import celery_app

    result = AsyncResult(task_id, app=celery_app)

    response = {"task_id": task_id, "status": result.state.lower()}

    if result.state == "SUCCESS":
        response["status"] = "success"
        response["result"] = result.result
    elif result.state == "FAILURE":
        response["status"] = "failed"
        response["error"] = str(result.result)

    return response


@app.post("/api/v1/query/sync")
async def sync_query(request: QueryRequest):
    """Synchronous query — bypasses Celery, for testing only."""
    from core_rag import process_query

    try:
        result = process_query(
            query=request.query,
            conversation_id=request.conversation_id,
        )
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"Sync query error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/reload")
async def reload_engine():
    """Reload RAG engine cache (after re-ingestion or config change)."""
    from core_rag import reload_cache

    reload_cache()
    return {"status": "ok", "message": "Engine cache reloaded"}


# ─── Facebook Messenger Webhook ──────────────────────────────

@app.get("/webhook/messenger")
async def messenger_verify(request: Request):
    config = _load_config()
    params = request.query_params

    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == config.get("messenger_verify_token")
    ):
        return int(params.get("hub.challenge", "0"))
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook/messenger")
async def messenger_webhook(request: Request):
    from tasks import process_rag_query
    import requests as req

    config = _load_config()
    body = await request.json()

    for entry in body.get("entry", []):
        for event in entry.get("messaging", []):
            sender_id = event.get("sender", {}).get("id")
            message_text = event.get("message", {}).get("text")

            if not (sender_id and message_text):
                continue

            task = process_rag_query.delay(
                query=message_text,
                conversation_id=f"messenger_{sender_id}",
            )
            try:
                result = task.get(timeout=25)
                answer = result.get("answer", "Maaf, terjadi kesalahan.")
            except Exception:
                answer = "Maaf, sistem sedang sibuk. Coba lagi nanti."

            req.post(
                "https://graph.facebook.com/v18.0/me/messages",
                params={"access_token": config.get("messenger_page_access_token")},
                json={
                    "recipient": {"id": sender_id},
                    "message": {"text": answer},
                },
                timeout=10,
            )

    return {"status": "ok"}


# ─── Telegram Webhook ───────────────────────────────────────

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    from tasks import process_rag_query
    import requests as req

    config = _load_config()
    body = await request.json()

    message = body.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    if not (chat_id and text):
        return {"status": "ok"}

    if text.startswith("/start"):
        answer = "Halo! 👋 Saya AI Assistant. Silakan ajukan pertanyaan Anda."
    else:
        task = process_rag_query.delay(
            query=text,
            conversation_id=f"telegram_{chat_id}",
        )
        try:
            result = task.get(timeout=55)
            answer = result.get("answer", "Maaf, terjadi kesalahan.")
        except Exception:
            answer = "Maaf, sistem sedang sibuk. Coba lagi nanti."

    bot_token = config.get("telegram_bot_token")
    req.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": answer, "parse_mode": "Markdown"},
        timeout=10,
    )

    return {"status": "ok"}


# ─── WhatsApp Webhook ───────────────────────────────────────

@app.get("/webhook/whatsapp")
async def whatsapp_verify(request: Request):
    config = _load_config()
    params = request.query_params

    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == config.get("whatsapp_verify_token")
    ):
        return int(params.get("hub.challenge", "0"))
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    from tasks import process_rag_query
    import requests as req

    config = _load_config()
    body = await request.json()

    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            messages = change.get("value", {}).get("messages", [])

            for msg in messages:
                phone = msg.get("from")
                text = msg.get("text", {}).get("body", "")

                if not (phone and text):
                    continue

                task = process_rag_query.delay(
                    query=text,
                    conversation_id=f"whatsapp_{phone}",
                )
                try:
                    result = task.get(timeout=25)
                    answer = result.get("answer", "Maaf, terjadi kesalahan.")
                except Exception:
                    answer = "Maaf, sistem sedang sibuk. Coba lagi nanti."

                phone_id = config.get("whatsapp_phone_number_id")
                api_token = config.get("whatsapp_api_token")
                req.post(
                    f"https://graph.facebook.com/v18.0/{phone_id}/messages",
                    headers={"Authorization": f"Bearer {api_token}"},
                    json={
                        "messaging_product": "whatsapp",
                        "to": phone,
                        "type": "text",
                        "text": {"body": answer},
                    },
                    timeout=10,
                )

    return {"status": "ok"}
