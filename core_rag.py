"""
core_rag.py — Core RAG (Retrieval-Augmented Generation) Engine
Handles: embeddings, vector search, LLM invocation, re-ranking
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

# ─── System Prompt ──────────────────────────────────────────

SYSTEM_PROMPT = """\
Anda adalah asisten AI yang sangat membantu dan akurat. Pengetahuan Anda \
bersumber dari database dokumen dan konten website internal.

**Aturan:**
1. JAWAB HANYA berdasarkan konteks yang diberikan.
2. Jika jawaban TIDAK ADA dalam konteks, katakan: \
"Maaf, informasi tersebut tidak ditemukan dalam database saya. \
Silakan hubungi admin untuk pertanyaan lebih lanjut."
3. Jika menggunakan informasi dari website, SERTAKAN URL sumber.
4. Jika dari dokumen, sebutkan nama file.
5. Jawab dengan ringkas, jelas, dan profesional dalam Bahasa Indonesia.

**Konteks:**
{context}

**Sumber tersedia:**
{sources}"""


# ─── Config ─────────────────────────────────────────────────

def load_config(path: str = None) -> dict:
    config_file = path or CONFIG_PATH
    with open(config_file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ─── Factory: Embeddings ────────────────────────────────────

def create_embeddings(config: dict):
    provider = config.get("embedding_provider", "ollama")
    model = config.get("embedding_model", "nomic-embed-text")
    logger.info(f"Creating embeddings: provider={provider}, model={model}")

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
    elif provider == "huggingface":
        from langchain_community.embeddings import HuggingFaceInferenceAPIEmbeddings
        return HuggingFaceInferenceAPIEmbeddings(
            api_key=config.get("embedding_api_key", ""),
            model_name=model,
        )
    else:
        raise ValueError(f"Unknown embedding provider: '{provider}'")


# ─── Factory: LLM ───────────────────────────────────────────

def create_llm(config: dict):
    provider = config.get("llm_provider", "ollama")
    model = config.get("llm_model", "llama3")
    temperature = config.get("llm_temperature", 0.3)
    logger.info(f"Creating LLM: provider={provider}, model={model}")

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


# ─── Singleton Cache ────────────────────────────────────────

class _EngineCache:
    __slots__ = ("config", "embeddings", "vector_store", "llm", "reranker")

    def __init__(self):
        self.config = None
        self.embeddings = None
        self.vector_store = None
        self.llm = None
        self.reranker = None


_cache = _EngineCache()


def get_config() -> dict:
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
        vs_path = config.get("vector_store_path", "db/faiss_index")
        full_path = os.path.join(BASE_DIR, vs_path)

        if not os.path.exists(full_path):
            logger.warning(f"Vector store not found: {full_path}")
            return None

        from langchain_community.vectorstores import FAISS
        _cache.vector_store = FAISS.load_local(
            full_path,
            get_embeddings(),
            allow_dangerous_deserialization=True,
        )
        logger.info(f"FAISS loaded: {_cache.vector_store.index.ntotal} vectors")
    return _cache.vector_store


def get_llm():
    if _cache.llm is None:
        _cache.llm = create_llm(get_config())
    return _cache.llm


def get_reranker():
    if _cache.reranker is None:
        try:
            from sentence_transformers import CrossEncoder
            model_name = get_config().get(
                "reranker_model", "cross-encoder/ms-marco-MiniLM-L-6-v2"
            )
            _cache.reranker = CrossEncoder(model_name)
            logger.info(f"Re-ranker loaded: {model_name}")
        except ImportError:
            logger.info("sentence-transformers not installed — re-ranking disabled")
        except Exception as e:
            logger.warning(f"Failed to load re-ranker: {e}")
    return _cache.reranker


def reload_cache():
    """Clear all cached objects (call after config change or re-ingest)."""
    global _cache
    _cache = _EngineCache()
    logger.info("Engine cache cleared")


# ─── Re-ranking ─────────────────────────────────────────────

def rerank_documents(
    query: str, documents: List[Document], top_k: int = 3
) -> List[Document]:
    reranker = get_reranker()
    if reranker is None:
        return documents[:top_k]
    try:
        pairs = [(query, doc.page_content) for doc in documents]
        scores = reranker.predict(pairs)
        scored = sorted(zip(documents, scores), key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in scored[:top_k]]
    except Exception as e:
        logger.error(f"Re-ranking failed: {e}")
        return documents[:top_k]


# ─── Main Query Processing ──────────────────────────────────

def process_query(
    query: str, conversation_id: Optional[str] = None
) -> Dict[str, Any]:
    config = get_config()
    logger.info(f"Processing: '{query[:80]}' (cid={conversation_id})")

    # 1. Get vector store
    vector_store = get_vector_store()
    if vector_store is None:
        return {
            "answer": "Database belum diinisialisasi. Jalankan: python ingest_data.py",
            "sources": [],
            "conversation_id": conversation_id,
        }

    # 2. Similarity search
    initial_k = config.get("retrieval_top_k", 5)
    try:
        docs = vector_store.similarity_search(query, k=initial_k)
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return {
            "answer": "Terjadi kesalahan saat mencari informasi.",
            "sources": [],
            "conversation_id": conversation_id,
        }

    if not docs:
        return {
            "answer": "Maaf, informasi tersebut tidak ditemukan dalam database saya.",
            "sources": [],
            "conversation_id": conversation_id,
        }

    # 3. Optional re-ranking
    rerank_top_k = config.get("rerank_top_k", 3)
    if config.get("use_reranker", False):
        docs = rerank_documents(query, docs, top_k=rerank_top_k)
    else:
        docs = docs[:rerank_top_k]

    # 4. Build context
    sources = list({doc.metadata.get("source", "Unknown") for doc in docs})
    context_parts = []
    for doc in docs:
        src = doc.metadata.get("source", "Unknown")
        context_parts.append(f"[Sumber: {src}]\n{doc.page_content}")
    context = "\n\n---\n\n".join(context_parts)
    sources_text = "\n".join(f"- {s}" for s in sources)

    # 5. LLM invocation
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
