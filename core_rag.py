"""
core_rag.py — Core RAG (Retrieval-Augmented Generation) Engine
"""

import os
import logging
from typing import Dict, Any, List, Optional

import yaml
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")

SYSTEM_PROMPT = """\
Anda adalah asisten AI untuk **Baliwithkidz** — platform layanan keluarga di Bali.

**Aturan:**
1. Jawab berdasarkan konteks yang diberikan di bawah ini.
2. Jika konteks mengandung informasi yang RELEVAN dengan pertanyaan, WAJIB berikan jawaban. Jangan pernah bilang "tidak ditemukan" jika ada data relevan di konteks.
3. HANYA jika konteks benar-benar TIDAK RELEVAN sama sekali, katakan: "Maaf, informasi tersebut tidak ditemukan dalam database saya."
4. Sertakan detail: nama, deskripsi singkat, dan cara menghubungi (WhatsApp/Phone) jika tersedia.
5. **WAJIB sertakan URL/link detail jika tersedia di konteks** (format: "🔗 Detail: <url>").
6. Jika ada beberapa hasil, tampilkan dalam format list yang rapi.
7. Jawab dengan rapi, jelas, dan profesional. Gunakan bahasa yang sama dengan pertanyaan (Indonesia/English).
8. Jangan mengarang informasi yang tidak ada di konteks.

**Konteks:**
{context}

**Sumber tersedia:**
{sources}"""


def load_config(path=None):
    with open(path or CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def create_embeddings(config):
    provider = config.get("embedding_provider", "ollama")
    model = config.get("embedding_model", "nomic-embed-text")

    if provider == "ollama":
        from langchain_ollama import OllamaEmbeddings
        return OllamaEmbeddings(
            model=model,
            base_url=config.get("ollama_base_url", "http://localhost:11434"),
        )
    elif provider == "openai":
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(
            model=model,
            openai_api_key=config.get("embedding_api_key", ""),
        )
    else:
        raise ValueError(f"Unknown embedding provider: '{provider}'")


def create_llm(config):
    provider = config.get("llm_provider", "ollama")
    model = config.get("llm_model", "llama3")
    temperature = config.get("llm_temperature", 0.3)

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=model,
            base_url=config.get("llm_base_url", "http://localhost:11434"),
            temperature=temperature,
        )
    elif provider in ("openai", "openrouter", "groq"):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model,
            openai_api_key=config.get("llm_api_key", ""),
            openai_api_base=config.get("llm_base_url", "https://api.openai.com/v1"),
            temperature=temperature,
            max_tokens=config.get("llm_max_tokens", 1024),
        )
    else:
        raise ValueError(f"Unknown LLM provider: '{provider}'")


class _Cache:
    def __init__(self):
        self.config = None
        self.embeddings = None
        self.vector_store = None
        self.llm = None

_cache = _Cache()


def get_config():
    if _cache.config is None:
        _cache.config = load_config()
    return _cache.config


def get_embeddings():
    if _cache.embeddings is None:
        _cache.embeddings = create_embeddings(get_config())
    return _cache.embeddings


def get_vector_store():
    if _cache.vector_store is None:
        config = get_config()
        vs_path = os.path.join(BASE_DIR, config.get("vector_store_path", "db/faiss_index"))
        if not os.path.exists(vs_path):
            return None
        from langchain_community.vectorstores import FAISS
        _cache.vector_store = FAISS.load_local(
            vs_path, get_embeddings(), allow_dangerous_deserialization=True,
        )
    return _cache.vector_store


def get_llm():
    if _cache.llm is None:
        _cache.llm = create_llm(get_config())
    return _cache.llm


def reload_cache():
    global _cache
    _cache = _Cache()


def process_query(query, conversation_id=None):
    config = get_config()

    vector_store = get_vector_store()
    if vector_store is None:
        return {
            "answer": "Database belum diinisialisasi. Jalankan: python ingest_data.py",
            "sources": [],
            "conversation_id": conversation_id,
        }

    docs = vector_store.similarity_search(query, k=config.get("retrieval_top_k", 5))

    if not docs:
        return {
            "answer": "Maaf, informasi tersebut tidak ditemukan dalam database saya.",
            "sources": [],
            "conversation_id": conversation_id,
        }

    docs = docs[:config.get("rerank_top_k", 3)]

    sources = list({doc.metadata.get("source", "Unknown") for doc in docs})
    context_parts = []
    for doc in docs:
        src = doc.metadata.get("source", "Unknown")
        context_parts.append(f"[Sumber: {src}]\n{doc.page_content}")
    context = "\n\n---\n\n".join(context_parts)
    sources_text = "\n".join(f"- {s}" for s in sources)

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "{question}"),
    ])
    chain = prompt | get_llm() | StrOutputParser()

    try:
        answer = chain.invoke({
            "context": context,
            "sources": sources_text,
            "question": query,
        })
    except Exception as e:
        logger.error(f"LLM failed: {e}", exc_info=True)
        return {
            "answer": "Terjadi kesalahan saat memproses pertanyaan Anda.",
            "sources": [],
            "conversation_id": conversation_id,
        }

    return {
        "answer": answer,
        "sources": sources,
        "conversation_id": conversation_id,
    }
