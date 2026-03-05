<div align="center">

# 🧠 AI Brain by Boy Barley

**RAG-Powered AI Assistant with Multi-Channel Integration**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

*Upload your documents → AI answers questions based on your data*
*Supports: Telegram · WhatsApp · Messenger · REST API*

</div>

---

## ⚡ Quick Install (One-Liner)

```bash
wget -O install.sh https://raw.githubusercontent.com/boybarley/ai-brain-/main/install.sh && chmod +x install.sh && sudo bash install.sh
```

That's it. The installer will:
- ✅ Install all dependencies (Python, Redis, Ollama)
- ✅ Clone this repository
- ✅ Setup Python virtual environment
- ✅ Download embedding model
- ✅ Configure systemd services
- ✅ Start everything

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Your Server                         │
│                                                          │
│   ┌──────────┐    ┌────────┐    ┌──────────────────┐   │
│   │ FastAPI   │───▶│ Redis  │───▶│  Celery Worker   │   │
│   │ :5000     │    │ :6379  │    │  (task queue)    │   │
│   └──────────┘    └────────┘    └────────┬─────────┘   │
│        │                                  │             │
│   ┌────▼─────┐    ┌──────────────────────▼──────────┐  │
│   │ Webhooks │    │        core_rag.py               │  │
│   │ TG/WA/FB │    │  ┌──────────┐  ┌─────────────┐  │  │
│   └──────────┘    │  │  FAISS   │  │  Build       │  │  │
│                   │  │  Search  │  │  Prompt      │  │  │
│   ┌───────────┐   │  └──────────┘  └──────┬──────┘  │  │
│   │  Ollama   │◀──│    Embedding          │         │  │
│   │  (embed)  │   └───────────────────────┼─────────┘  │
│   └───────────┘                           │             │
└───────────────────────────────────────────┼─────────────┘
                                            │ API
                                  ┌─────────▼──────────┐
                                  │   LLM Provider     │
                                  │ OpenRouter / OpenAI │
                                  │ Groq / Ollama      │
                                  └────────────────────┘
```

---

## 📋 Requirements

| Component | Minimum |
|-----------|---------|
| OS | Ubuntu 20.04 / 22.04 |
| RAM | **2 GB** (with cloud LLM) or **8 GB** (with local Ollama LLM) |
| Disk | 5 GB free |
| Python | 3.10+ |

---

## 🔧 Manual Installation

<details>
<summary>Click to expand manual steps</summary>

```bash
# 1. System dependencies
sudo apt update && sudo apt install -y python3 python3-pip python3-venv redis-server git curl

# 2. Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 3. Clone repo
git clone https://github.com/boybarley/ai-brain-.git /root/ai-brain
cd /root/ai-brain

# 4. Python setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 5. Download embedding model
ollama pull nomic-embed-text

# 6. Configure
cp config.yaml.example config.yaml
nano config.yaml  # Set your LLM API key

# 7. Ingest sample data
python ingest_data.py

# 8. Start services
uvicorn api_server:app --host 0.0.0.0 --port 5000 &
celery -A tasks worker --loglevel=info --concurrency=1 --pool=solo &
```

</details>

---

## ⚙️ Configuration

Edit `config.yaml` to configure your LLM provider:

### OpenRouter (Recommended — Low RAM)

```yaml
llm_provider: "openrouter"
llm_model: "google/gemini-2.0-flash-001"
llm_base_url: "https://openrouter.ai/api/v1"
llm_api_key: "sk-or-v1-your-key-here"
```

Get your API key at [openrouter.ai/keys](https://openrouter.ai/keys)

### Available Models on OpenRouter

| Model | Cost | Speed | Quality |
|-------|------|-------|---------|
| `google/gemini-2.0-flash-001` | 💰 | ⚡⚡⚡ | ⭐⭐⭐⭐ |
| `deepseek/deepseek-chat-v3-0324` | 💰 | ⚡⚡ | ⭐⭐⭐⭐⭐ |
| `openai/gpt-4o-mini` | 💰💰 | ⚡⚡⚡ | ⭐⭐⭐⭐ |
| `anthropic/claude-3.5-sonnet` | 💰💰💰 | ⚡⚡ | ⭐⭐⭐⭐⭐ |
| `meta-llama/llama-3.1-8b-instruct` | 💰 | ⚡⚡⚡ | ⭐⭐⭐ |

<details>
<summary>Other Providers</summary>

#### OpenAI Direct
```yaml
llm_provider: "openai"
llm_model: "gpt-4o-mini"
llm_base_url: "https://api.openai.com/v1"
llm_api_key: "sk-your-key"
```

#### Groq (Fast & Free Tier)
```yaml
llm_provider: "groq"
llm_model: "llama-3.1-8b-instant"
llm_base_url: "https://api.groq.com/openai/v1"
llm_api_key: "gsk_your-key"
```

#### Ollama (Local — Requires 8GB+ RAM)
```yaml
llm_provider: "ollama"
llm_model: "llama3"
llm_base_url: "http://localhost:11434"
llm_api_key: ""
```

</details>

After changing config:
```bash
sudo systemctl restart bot-api bot-worker
```

---

## 📄 Adding Your Data

### Method 1: Upload Documents

Place files in the `data/` folder:

```bash
# Copy files
cp your-document.pdf /root/ai-brain/data/
cp knowledge-base.txt /root/ai-brain/data/
cp data.xlsx /root/ai-brain/data/

# Ingest into vector database
cd /root/ai-brain && source venv/bin/activate
python ingest_data.py
```

Supported formats: `.txt` `.md` `.pdf` `.docx` `.csv` `.xlsx`

### Method 2: Crawl a Website

```bash
cd /root/ai-brain && source venv/bin/activate

# Basic crawl
python crawl.py https://yourcompany.com

# Advanced options
python crawl.py https://yourcompany.com --depth 3 --max-pages 100

# Then ingest crawled content
python ingest_data.py
```

### Method 3: Append New Data (Keep Existing)

```bash
# Add new files to data/, then:
python ingest_data.py APPEND
```

### Reload After Ingestion

```bash
# Restart to load new vectors
sudo systemctl restart bot-api bot-worker

# Or hot-reload via API
curl -X POST http://localhost:5000/api/v1/reload
```

---

## 🚀 API Reference

### Health Check

```bash
curl http://localhost:5000/health
```

### Submit Query (Async)

```bash
curl -X POST http://localhost:5000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is your refund policy?"}'
```

Response:
```json
{
  "status": "accepted",
  "task_id": "abc-123-def",
  "message": "Query submitted for processing"
}
```

### Get Result

```bash
curl http://localhost:5000/api/v1/task/abc-123-def
```

Response:
```json
{
  "task_id": "abc-123-def",
  "status": "success",
  "result": {
    "answer": "Our refund policy allows...",
    "sources": ["faq.pdf", "policy.txt"],
    "conversation_id": null
  }
}
```

### Sync Query (Testing)

```bash
curl -X POST http://localhost:5000/api/v1/query/sync \
  -H "Content-Type: application/json" \
  -d '{"query": "Your question here"}'
```

### Interactive Docs

Open `http://your-server:5000/docs` for Swagger UI.

---

## 💬 Channel Integration

### Telegram Bot

1. Create bot via [@BotFather](https://t.me/BotFather)
2. Copy the token
3. Edit `config.yaml`:
   ```yaml
   telegram_bot_token: "123456:ABC-DEF..."
   ```
4. Set webhook:
   ```bash
   curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://yourdomain.com/webhook/telegram"
   ```

### WhatsApp Business

1. Setup at [Meta Business Suite](https://business.facebook.com)
2. Edit `config.yaml`:
   ```yaml
   whatsapp_verify_token: "your-verify-token"
   whatsapp_api_token: "your-api-token"
   whatsapp_phone_number_id: "your-phone-id"
   ```
3. Set webhook URL: `https://yourdomain.com/webhook/whatsapp`

### Facebook Messenger

1. Create app at [Meta Developers](https://developers.facebook.com)
2. Edit `config.yaml`:
   ```yaml
   messenger_verify_token: "your-verify-token"
   messenger_page_access_token: "your-page-token"
   ```
3. Set webhook URL: `https://yourdomain.com/webhook/messenger`

> **Note:** Webhooks require HTTPS. Use Nginx + Certbot for SSL.

---

## 🛠️ Management Commands

```bash
# Check service status
sudo systemctl status bot-api bot-worker

# View logs
tail -f /root/ai-brain/logs/api.log
tail -f /root/ai-brain/logs/worker.log

# Restart services
sudo systemctl restart bot-api bot-worker

# Re-ingest all data
cd /root/ai-brain && source venv/bin/activate
rm -rf db/faiss_index
python ingest_data.py
sudo systemctl restart bot-api bot-worker
```

---

## 🐛 Troubleshooting

<details>
<summary><b>Task stuck in "started" or "pending"</b></summary>

**Cause:** Worker crash (usually OOM) or LLM timeout.

```bash
# Check worker log
tail -50 /root/ai-brain/logs/worker-error.log

# Check RAM
free -h

# Fix: Reduce concurrency or switch to cloud LLM
sudo systemctl restart bot-worker
```
</details>

<details>
<summary><b>Empty curl response</b></summary>

**Cause:** API server not ready yet.

```bash
# Wait and retry
sleep 5
curl http://localhost:5000/health

# Or check logs
tail -20 /root/ai-brain/logs/api-error.log
```
</details>

<details>
<summary><b>"No documents found" on ingest</b></summary>

**Cause:** `data/` folder is empty.

```bash
ls -la /root/ai-brain/data/
# Add your files, then re-run:
python ingest_data.py
```
</details>

<details>
<summary><b>Ollama connection refused</b></summary>

```bash
sudo systemctl start ollama
sudo systemctl status ollama
ollama list   # Should show nomic-embed-text
```
</details>

---

## 📁 Project Structure

```
ai-brain/
├── install.sh              # One-click installer
├── config.yaml.example     # Configuration template
├── config.yaml             # Your config (git-ignored)
├── requirements.txt        # Python dependencies
├── api_server.py           # FastAPI server + webhooks
├── core_rag.py             # RAG engine (search + LLM)
├── tasks.py                # Celery async tasks
├── ingest_data.py          # Document ingestion
├── crawl.py                # Website crawler
├── data/                   # Your documents (PDF, TXT, etc.)
├── db/                     # FAISS vector index
└── logs/                   # Application logs
```

---

## 📄 License

MIT License — free for personal and commercial use.

---

<div align="center">

**Built with ❤️ by [boybarley](https://boybarley.com) **

</div>
