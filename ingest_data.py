"""
ingest_data.py — Universal Data Ingestion Script
==================================================
Memproses file dari folder data/ dan membangun FAISS vector index.

Tipe file yang didukung:
  - .pdf  → PyPDFLoader
  - .txt  → TextLoader
  - .md   → TextLoader

Usage:
  python ingest_data.py              # Proses semua file di data/
  python ingest_data.py /path/to/dir  # Proses dari folder custom
  python ingest_data.py --append      # Append ke index yang sudah ada
"""

import os
import sys
import logging
from typing import List

from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS

from core_rag import load_config, create_embeddings

# ─── Logging ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Tipe file yang didukung
LOADERS = {
    ".pdf": "pdf",
    ".txt": "text",
    ".md": "text",
}


def load_documents_from_directory(data_dir: str) -> List[Document]:
    """
    Scan folder dan load semua file yang didukung.
    Metadata `source` diisi dengan nama file.
    """
    full_dir = (
        data_dir if os.path.isabs(data_dir)
        else os.path.join(BASE_DIR, data_dir)
    )

    if not os.path.exists(full_dir):
        logger.warning(f"Directory not found: {full_dir}")
        os.makedirs(full_dir, exist_ok=True)
        logger.info(f"Created directory: {full_dir}")
        return []

    documents = []
    files = sorted(os.listdir(full_dir))
    supported_count = 0

    logger.info(f"📂 Scanning directory: {full_dir}")

    for filename in files:
        filepath = os.path.join(full_dir, filename)
        ext = os.path.splitext(filename)[1].lower()

        if ext not in LOADERS:
            continue

        supported_count += 1
        loader_type = LOADERS[ext]

        try:
            if loader_type == "pdf":
                from langchain_community.document_loaders import PyPDFLoader
                loader = PyPDFLoader(filepath)
                docs = loader.load()

                # Set source metadata to filename
                for doc in docs:
                    doc.metadata["source"] = filename
                    doc.metadata["type"] = "pdf"
                    doc.metadata["page"] = doc.metadata.get("page", 0)

                documents.extend(docs)
                logger.info(
                    f"  📄 {filename} — {len(docs)} page(s) loaded"
                )

            elif loader_type == "text":
                from langchain_community.document_loaders import TextLoader

                # Try UTF-8 first, then fallback encodings
                loaded = False
                for encoding in ("utf-8", "latin-1", "cp1252"):
                    try:
                        loader = TextLoader(filepath, encoding=encoding)
                        docs = loader.load()

                        for doc in docs:
                            doc.metadata["source"] = filename
                            doc.metadata["type"] = (
                                "markdown" if ext == ".md" else "text"
                            )

                        documents.extend(docs)
                        logger.info(
                            f"  📝 {filename} — loaded ({encoding})"
                        )
                        loaded = True
                        break

                    except UnicodeDecodeError:
                        continue

                if not loaded:
                    logger.error(
                        f"  ❌ {filename} — could not decode with any encoding"
                    )

        except Exception as e:
            logger.error(f"  ❌ {filename} — failed to load: {e}")

    logger.info(
        f"\n📊 Summary: {supported_count} supported file(s) found, "
        f"{len(documents)} document(s) loaded"
    )

    return documents


def ingest(
    data_dir: str = "data",
    append: bool = False,
    config: dict = None,
):
    """
    Pipeline utama untuk ingest data.
    
    Args:
        data_dir: Folder berisi file data
        append:   True = merge ke index yang ada; False = replace
        config:   Config dictionary (auto-load jika None)
    """
    if config is None:
        config = load_config()

    logger.info("🚀 Starting data ingestion pipeline...")
    logger.info(f"   Mode: {'APPEND' if append else 'REPLACE'}")

    # ── Step 1: Load Documents ───────────────────────────────
    documents = load_documents_from_directory(data_dir)

    if not documents:
        logger.warning(
            "⚠️  No documents found. Place PDF/TXT/MD files in "
            f"the '{data_dir}/' folder."
        )
        return

    # ── Step 2: Split Into Chunks ────────────────────────────
    chunk_size = config.get("chunk_size", 1000)
    chunk_overlap = config.get("chunk_overlap", 200)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks = splitter.split_documents(documents)

    logger.info(
        f"✂️  Split {len(documents)} document(s) → {len(chunks)} chunks "
        f"(size={chunk_size}, overlap={chunk_overlap})"
    )

    # ── Step 3: Create Embeddings & FAISS Index ──────────────
    logger.info("🔄 Creating embeddings (this may take a while)...")
    embeddings = create_embeddings(config)

    vs_path = config.get("vector_store_path", "db/faiss_index")
    full_path = os.path.join(BASE_DIR, vs_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    if append and os.path.exists(full_path):
        # Append mode: merge with existing
        logger.info("🔄 Appending to existing FAISS index...")
        existing = FAISS.load_local(
            full_path, embeddings,
            allow_dangerous_deserialization=True,
        )
        new_store = FAISS.from_documents(chunks, embeddings)
        existing.merge_from(new_store)
        existing.save_local(full_path)

        logger.info(
            f"✅ Index updated! Total vectors: {existing.index.ntotal}"
        )
    else:
        # Replace mode: create fresh index
        logger.info("🆕 Creating new FAISS index...")
        store = FAISS.from_documents(chunks, embeddings)
        store.save_local(full_path)

        logger.info(
            f"✅ Index created! Total vectors: {store.index.ntotal}"
        )

    logger.info(f"📍 Saved to: {full_path}")
    logger.info(
        "\n💡 Tip: Restart services to load new data:\n"
        "   sudo systemctl restart bot-api bot-worker\n"
        "   — or call POST /api/v1/reload"
    )


# ══════════════════════════════════════════════════════════════
#  CLI INTERFACE
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Universal Data Ingestor for AI Brain",
    )
    parser.add_argument(
        "data_dir", nargs="?", default="data",
        help="Directory containing data files (default: data/)",
    )
    parser.add_argument(
        "--append", action="store_true",
        help="Append to existing FAISS index instead of replacing",
    )

    args = parser.parse_args()
    ingest(data_dir=args.data_dir, append=args.append)
