"""
tasks.py — Celery task definitions
"""

import os
import logging

import yaml
from celery import Celery

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_config() -> dict:
    config_path = os.path.join(BASE_DIR, "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


_config = _load_config()
_redis_url = _config.get("redis_url", "redis://localhost:6379/0")

celery_app = Celery(
    "ai_brain",
    broker=_redis_url,
    backend=_redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
)


@celery_app.task(
    name="tasks.process_rag_query",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
)
def process_rag_query(self, query: str, conversation_id: str = None):
    """Process a RAG query asynchronously."""
    try:
        from core_rag import process_query

        result = process_query(query=query, conversation_id=conversation_id)
        return result
    except Exception as e:
        logger.error(f"Task failed: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=5)


@celery_app.task(name="tasks.health_check")
def health_check():
    """Simple health check task."""
    return {"status": "healthy", "worker": "operational"}
