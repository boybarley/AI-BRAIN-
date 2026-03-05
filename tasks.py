"""
tasks.py — Celery Task Definitions
====================================
Menangani pemrosesan RAG secara asinkron.

Alur:
  1. API Server menerima request → submit task ke Redis queue
  2. Celery Worker mengambil task dari queue
  3. Worker menjalankan core_rag.process_query()
  4. Worker mengirim jawaban via platform_adapters
"""

import logging
from celery import Celery
from core_rag import load_config

# ─── Logging ─────────────────────────────────────────────────
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

# ─── Celery App Configuration ────────────────────────────────
_config = load_config()
_redis_url = _config.get("redis_url", "redis://localhost:6379/0")

app = Celery(
    "ai_brain",
    broker=_redis_url,
    backend=_redis_url,
)

app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timezone
    timezone="Asia/Jakarta",
    enable_utc=True,

    # Reliability
    task_track_started=True,
    task_acks_late=True,            # Acknowledge after completion
    worker_prefetch_multiplier=1,   # Fetch 1 task at a time

    # Results
    result_expires=3600,            # Results expire after 1 hour

    # Retry
    task_default_retry_delay=30,
    task_max_retries=3,
)


# ══════════════════════════════════════════════════════════════
#  TASKS
# ══════════════════════════════════════════════════════════════

@app.task(
    bind=True,
    name="tasks.process_rag_query",
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
)
def process_rag_query(
    self,
    query: str,
    conversation_id: str = None,
    platform: str = None,
    user_id: str = None,
) -> dict:
    """
    Task utama: proses query RAG secara asinkron.
    
    Jika `platform` dan `user_id` diberikan (dari webhook), 
    jawaban akan dikirim langsung ke pengguna via adapter.
    
    Jika tidak (dari /api/v1/query), hasil dikembalikan untuk
    di-poll via /api/v1/task/{task_id}.
    
    Args:
        query:           Pertanyaan pengguna
        conversation_id: ID percakapan untuk tracking
        platform:        "messenger" | "telegram" | "whatsapp" | None
        user_id:         ID pengguna di platform
    
    Returns:
        {"answer": str, "sources": list, "conversation_id": str}
    """
    logger.info(
        f"[Task {self.request.id}] Processing: "
        f"platform={platform}, user={user_id}, "
        f"query='{query[:60]}...'"
    )

    try:
        # ── Step 1: Process through RAG Engine ───────────────
        from core_rag import process_query
        result = process_query(
            query=query,
            conversation_id=conversation_id,
        )

        # ── Step 2: Send reply to platform (if applicable) ──
        if platform and user_id:
            from platform_adapters import send_platform_reply

            success = send_platform_reply(
                platform=platform,
                user_id=user_id,
                answer=result["answer"],
                sources=result["sources"],
            )

            if success:
                logger.info(
                    f"[Task {self.request.id}] Reply sent to "
                    f"{platform}:{user_id}"
                )
            else:
                logger.warning(
                    f"[Task {self.request.id}] Failed to send reply to "
                    f"{platform}:{user_id}"
                )

        logger.info(f"[Task {self.request.id}] Completed successfully")
        return result

    except Exception as exc:
        logger.error(
            f"[Task {self.request.id}] Failed: {exc}",
            exc_info=True,
        )

        # Send error message to user if possible
        if platform and user_id:
            try:
                from platform_adapters import send_platform_reply
                send_platform_reply(
                    platform=platform,
                    user_id=user_id,
                    answer=(
                        "⚠️ Maaf, terjadi kesalahan saat memproses "
                        "pertanyaan Anda. Silakan coba lagi nanti."
                    ),
                    sources=[],
                )
            except Exception:
                pass

        # Retry with exponential backoff
        raise self.retry(exc=exc)


@app.task(name="tasks.health_check")
def health_check() -> dict:
    """Simple health check task for monitoring."""
    return {"status": "healthy", "worker": "active"}
