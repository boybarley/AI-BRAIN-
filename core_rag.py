"""
core_rag.py — Core RAG Engine
==============================
Modul logika inti AI. Tidak mengetahui apapun tentang FastAPI, 
Messenger, atau platform lainnya. Tugasnya murni:
  INPUT  → query (string)
  OUTPUT → { "answer": str, "sources": list[str] }

Mendukung:
  - FAISS (CPU) sebagai vector database
  - Pluggable embedding models (Ollama, OpenAI, HuggingFace)
  - Pluggable LLM providers (Ollama, OpenAI, OpenRouter, Groq, dll.)
  - Cross-Encoder re-ranking untuk meningkatkan relevansi
  - Caching komponen berat (model, vector store) di level modul
"""

import os
import logging
from typing import Dict, Any, List, Optional

import yaml
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# ─── Logging ─────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")

# ─── System Prompt ───────────────────────────────────────────
SYSTEM_PROMPT = """\
Anda adalah asisten AI yang sangat canggih dan akurat, dengan pengetahuan \
yang bersumber dari database dokumen PDF dan konten website internal. \
Prioritaskan untuk selalu memberikan jawaban berdasarkan fakta dari \
sumber-sumber tersebut.

**Aturan Penting:**
1. JAWAB HANYA berdasarkan konteks yang diberikan. Jika jawaban tidak ada \
dalam konteks, katakan dengan jujur: 'Maaf, informasi tersebut tidak \
ditemukan dalam database saya. Silakan hubungi admin untuk pertanyaan \
lebih lanjut.'
2. **Sertakan Sumber:** Jika Anda menggunakan informasi dari sebuah \
website, **WAJIB** mencantumkan daftar link URL sumber di akhir jawaban \
Anda dalam format list. Jika dari PDF, sebutkan nama file dokumennya.
3. Jawablah dengan ringkas, jelas, dan profesional menggunakan bahasa Indonesia.

**Konteks dari Database:**
{context}

**Sumber yang tersedia:**
{sources}"""


# ══════════════════════════════════════════════════════════════
#  CONFIGURATION
# ══════════════════════════════════════════════════════════════

def load_config(path: str = None) -> dict:
    """Load configuration from YAML file."""
    config_file = path or CONFIG_PATH
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        logger.info(f"Configuration loaded from {config_file}")
        return config
    except FileNotFoundError:
        logger.error(f"Config file not found: {config_file}")
        raise
    except yaml.YAMLError as e:
        logger.error(f"Invalid YAML in config: {e}")
        raise


# ══════════════════════════════════════════════════════════════
#  FACTORY FUNCTIONS
# ══════════════════════════════════════════════════════════════

def create_embeddings(config: dict):
    """
    Factory function: buat model embedding berdasarkan config.
    
    Supported providers:
      - "ollama"      → OllamaEmbeddings (lokal)
      - "openai"      → OpenAIEmbeddings (cloud)
      - "huggingface"  → HuggingFaceInferenceAPIEmbeddings (cloud)
    """
    provider = config.get("embedding_provider", "ollama")
    model = config.get("embedding_model", "nomic-embed-text")

    logger.info(f"Creating embeddings: provider={provider}, model={model}")

    if provider == "ollama":
        from langchain_community.embeddings import OllamaEmbeddings
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
        raise ValueError(
            f"Unknown embedding provider: '{provider}'. "
            f"Supported: ollama, openai, huggingface"
        )


def create_llm(config: dict):
    """
    Factory function: buat LLM instance berdasarkan config.
    
    Supported providers:
      - "ollama"       → ChatOllama (lokal)
      - "openai"       → ChatOpenAI (OpenAI native)
      - "openrouter"   → ChatOpenAI (OpenAI-compatible)
      - "groq"         → ChatOpenAI (OpenAI-compatible)
      - "minimax"      → ChatOpenAI (OpenAI-compatible)
    """
    provider = config.get("llm_provider", "ollama")
    model = config.get("llm_model", "llama3")
    temperature = config.get("llm_temperature", 0.3)

    logger.info(f"Creating LLM: provider={provider}, model={model}")

    if provider == "ollama":
        from langchain_community.chat_models import ChatOllama
        return ChatOllama(
            model=model,
            base_url=config.get("llm_base_url", "http://localhost:11434"),
            temperature=temperature,
        )

    elif provider in ("openai", "openrouter", "groq", "minimax"):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model,
            openai_api_key=config.get("llm_api_key", ""),
            openai_api_base=config.get("llm_base_url", "https://api.openai.com/v1"),
            temperature=temperature,
            max_tokens=config.get("llm_max_tokens", 1024),
        )

    else:
        raise ValueError(
            f"Unknown LLM provider: '{provider}'. "
            f"Supported: ollama, openai, openrouter, groq, minimax"
        )


# ══════════════════════════════════════════════════════════════
#  MODULE-LEVEL CACHE  (Singleton Pattern)
#  Komponen berat di-cache agar tidak di-load ulang setiap query
# ══════════════════════════════════════════════════════════════

class _EngineCache:
    """Menyimpan referensi ke objek-objek berat yang mahal untuk dibuat."""
    __slots__ = ("config", "embeddings", "vector_store", "llm", "reranker")

    def __init__(self):
        self.config: Optional[dict] = None
        self.embeddings = None
        self.vector_store = None
        self.llm = None
        self.reranker = None


_cache = _EngineCache()


def get_config() -> dict:
    """Get cached config (load once)."""
    if _cache.config is None:
        _cache.config = load_config()
    return _cache.config


def get_embeddings():
    """Get cached embeddings model."""
    if _cache.embeddings is None:
        _cache.embeddings = create_embeddings(get_config())
    return _cache.embeddings


def get_vector_store():
    """Get cached FAISS vector store."""
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
        logger.info(
            f"FAISS loaded: {_cache.vector_store.index.ntotal} vectors"
        )
    return _cache.vector_store


def get_llm():
    """Get cached LLM instance."""
    if _cache.llm is None:
        _cache.llm = create_llm(get_config())
    return _cache.llm


def get_reranker():
    """Get cached cross-encoder re-ranker (lazy loaded)."""
    if _cache.reranker is None:
        try:
            from sentence_transformers import CrossEncoder
            model_name = get_config().get(
                "reranker_model",
                "cross-encoder/ms-marco-MiniLM-L-6-v2",
            )
            _cache.reranker = CrossEncoder(model_name)
            logger.info(f"Re-ranker loaded: {model_name}")
        except ImportError:
            logger.warning(
                "sentence-transformers not installed — re-ranking disabled"
            )
        except Exception as e:
            logger.warning(f"Failed to load re-ranker: {e}")
    return _cache.reranker


def reload_cache():
    """
    Reset semua cache. Panggil setelah:
      - Mengubah config.yaml
      - Menambah data baru ke FAISS (ingest_data / crawl)
    Worker/server perlu di-restart agar efektif.
    """
    global _cache
    _cache = _EngineCache()
    logger.info("Engine cache cleared")


# ══════════════════════════════════════════════════════════════
#  CROSS-ENCODER RE-RANKING
# ══════════════════════════════════════════════════════════════

def rerank_documents(
    query: str,
    documents: List[Document],
    top_k: int = 3,
) -> List[Document]:
    """
    Re-rank dokumen menggunakan cross-encoder model.
    
    Alur: FAISS mengambil ~10 dokumen → Cross-encoder menilai relevansi
    semantik setiap dokumen terhadap query → Ambil top_k terbaik.
    
    Fallback: jika re-ranker gagal, kembalikan dokumen asli (truncated).
    """
    reranker = get_reranker()
    if reranker is None:
        return documents[:top_k]

    try:
        pairs = [(query, doc.page_content) for doc in documents]
        scores = reranker.predict(pairs)

        scored_docs = sorted(
            zip(documents, scores),
            key=lambda x: x[1],
            reverse=True,
        )

        result = [doc for doc, _ in scored_docs[:top_k]]
        logger.debug(
            f"Re-ranked {len(documents)} → {len(result)} documents"
        )
        return result

    except Exception as e:
        logger.error(f"Re-ranking failed, using fallback: {e}")
        return documents[:top_k]


# ══════════════════════════════════════════════════════════════
#  MAIN QUERY FUNCTION
# ══════════════════════════════════════════════════════════════

def process_query(
    query: str,
    conversation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Proses query pengguna melalui pipeline RAG lengkap.
    
    Pipeline:
      1. Similarity search di FAISS (top_k dokumen)
      2. Cross-encoder re-ranking (opsional)
      3. Ekstraksi metadata source
      4. Prompt engineering dengan konteks
      5. LLM generation
      6. Structured output
    
    Args:
        query: Pertanyaan pengguna
        conversation_id: ID percakapan (untuk tracking, future use)
    
    Returns:
        {
            "answer": "Teks jawaban...",
            "sources": ["https://...", "dokumen.pdf"],
            "conversation_id": "user123"
        }
    """
    config = get_config()

    logger.info(
        f"Processing query: '{query[:80]}...' "
        f"(conversation_id={conversation_id})"
    )

    # ── Step 1: Load Vector Store ────────────────────────────
    vector_store = get_vector_store()
    if vector_store is None:
        return {
            "answer": (
                "⚠️ Database belum diinisialisasi. "
                "Silakan jalankan `python ingest_data.py` terlebih dahulu."
            ),
            "sources": [],
            "conversation_id": conversation_id,
        }

    # ── Step 2: Similarity Search ────────────────────────────
    initial_k = config.get("retrieval_top_k", 10)

    try:
        docs = vector_store.similarity_search(query, k=initial_k)
    except Exception as e:
        logger.error(f"Similarity search failed: {e}")
        return {
            "answer": "Terjadi kesalahan saat mencari informasi. Silakan coba lagi.",
            "sources": [],
            "conversation_id": conversation_id,
        }

    if not docs:
        return {
            "answer": (
                "Maaf, informasi tersebut tidak ditemukan dalam database saya. "
                "Silakan hubungi admin untuk pertanyaan lebih lanjut."
            ),
            "sources": [],
            "conversation_id": conversation_id,
        }

    logger.info(f"Retrieved {len(docs)} documents from FAISS")

    # ── Step 3: Re-ranking ───────────────────────────────────
    rerank_top_k = config.get("rerank_top_k", 3)
    use_reranker = config.get("use_reranker", True)

    if use_reranker:
        docs = rerank_documents(query, docs, top_k=rerank_top_k)
    else:
        docs = docs[:rerank_top_k]

    # ── Step 4: Extract Sources & Build Context ──────────────
    sources = list(set(
        doc.metadata.get("source", "Unknown") for doc in docs
    ))

    context_parts = []
    for doc in docs:
        src = doc.metadata.get("source", "Unknown")
        context_parts.append(f"[Sumber: {src}]\n{doc.page_content}")

    context = "\n\n---\n\n".join(context_parts)
    sources_text = "\n".join(f"- {s}" for s in sources)

    # ── Step 5: Prompt + LLM Chain ───────────────────────────
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "{question}"),
    ])

    llm = get_llm()
    chain = prompt | llm | StrOutputParser()

    try:
        answer = chain.invoke({
            "context": context,
            "sources": sources_text,
            "question": query,
        })
    except Exception as e:
        logger.error(f"LLM invocation failed: {e}", exc_info=True)
        return {
            "answer": (
                "Terjadi kesalahan saat memproses pertanyaan Anda. "
                "Silakan coba lagi nanti."
            ),
            "sources": [],
            "conversation_id": conversation_id,
        }

    logger.info(
        f"Query processed — answer length: {len(answer)}, "
        f"sources: {sources}"
    )

    return {
        "answer": answer,
        "sources": sources,
        "conversation_id": conversation_id,
    }
