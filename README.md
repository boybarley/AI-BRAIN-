# 🧠 AI Brain — Multi-Platform RAG Bot

> Sistem "Otak AI" berbasis **RAG (Retrieval-Augmented Generation)** yang modular
> dan berperforma tinggi. Satu otak AI, banyak platform.

## 📐 Arsitektur
User → [Messenger/Telegram/WhatsApp]
↓
Cloudflare Tunnel
↓
FastAPI Server (api_server.py)
├── /webhooks/{platform} → Parse & verify
└── /api/v1/query → Direct API access
↓
Redis Queue (Broker)
↓
Celery Worker (tasks.py)
↓
Core RAG Engine (core_rag.py)
├── FAISS Similarity Search (10 docs)
├── Cross-Encoder Re-ranking (→ 3 docs)
├── Prompt Engineering + Source Citation
└── LLM Generation (Ollama / Cloud)
↓
Platform Adapter (platform_adapters.py)
↓
User ← [Reply with answer + sources]



## ⚡ Quick Start

### Prerequisites

- **OS:** Ubuntu 22.04 / 24.04 LTS (dalam Proxmox VM)
- **RAM:** Minimum 4GB (8GB+ recommended untuk model lokal)
- **Python:** 3.10+
- **Ollama** (untuk model lokal) atau API key cloud provider

### Step 1: Clone & Install

```bash
# Clone project
git clone https://github.com/your-repo/ai-brain.git
cd ai-brain

# Edit konfigurasi
cp config.yaml.example config.yaml  # atau edit langsung
nano config.yaml

# Jalankan installer
chmod +x install.sh
./install.sh
Step 2: Setup Ollama (Model Lokal)

# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull model LLM
ollama pull llama3
# atau model yang lebih kecil:
# ollama pull mistral
# ollama pull phi3

# Pull model embedding
ollama pull nomic-embed-text
# atau alternatif:
# ollama pull mxbai-embed-large

# Verifikasi
ollama list
Step 3: Siapkan Data

# Taruh file PDF/TXT/MD di folder data/
cp /path/to/your/documents/*.pdf data/
cp /path/to/your/docs/*.txt data/

# Aktifkan virtual environment
source venv/bin/activate

# Ingest data (buat FAISS index)
python ingest_data.py

# (Opsional) Crawl website
python crawl.py https://docs.example.com --max-pages 30
Step 4: Setup Cloudflare Tunnel

# Install cloudflared
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
  | sudo tee /usr/share/keyrings/cloudflare-main.gpg > /dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] \
  https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt-get update && sudo apt-get install cloudflared

# Login ke Cloudflare
cloudflared tunnel login

# Buat tunnel
cloudflared tunnel create ai-brain

# Konfigurasi tunnel
cat > ~/.cloudflared/config.yml <<EOF
tunnel: <TUNNEL_ID>
credentials-file: /home/$USER/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: bot.yourdomain.com
    service: http://localhost:5000
  - service: http_status:404
EOF

# Buat DNS record
cloudflared tunnel route dns ai-brain bot.yourdomain.com

# Jalankan sebagai service
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
Sekarang https://bot.yourdomain.com → http://localhost:5000

Step 5: Konfigurasi Platform
Facebook Messenger
Buka Meta for Developers
Buat App → pilih "Business" type
Tambahkan product "Messenger"
Di Messenger Settings:
Generate Page Access Token → masukkan ke config.yaml
Setup Webhook:
Callback URL: https://bot.yourdomain.com/webhooks/messenger
Verify Token: sama dengan messenger_verify_token di config
Subscribe to: messages, messaging_postbacks
(Opsional) Masukkan App Secret ke messenger_app_secret untuk verifikasi signature
Telegram
Chat dengan @BotFather di Telegram
Kirim /newbot → ikuti instruksi → dapatkan Bot Token
Masukkan token ke telegram_bot_token di config.yaml
Set webhook:

curl -X POST "https://api.telegram.org/bot<YOUR_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://bot.yourdomain.com/webhooks/telegram"}'
WhatsApp Business API
Buka Meta for Developers
Buat App → pilih "Business" type
Tambahkan product "WhatsApp"
Di WhatsApp Settings:
Catat Phone Number ID dan Permanent Token
Setup Webhook:
Callback URL: https://bot.yourdomain.com/webhooks/whatsapp
Verify Token: sama dengan whatsapp_verify_token di config
Subscribe to: messages
Masukkan kredensial ke config.yaml
⚙️ Konfigurasi Cloud LLM Providers
OpenRouter

llm_provider: "openrouter"
llm_model: "meta-llama/llama-3-8b-instruct"
llm_base_url: "https://openrouter.ai/api/v1"
llm_api_key: "sk-or-v1-xxxxx"
Groq

llm_provider: "groq"
llm_model: "llama3-8b-8192"
llm_base_url: "https://api.groq.com/openai/v1"
llm_api_key: "gsk_xxxxx"
OpenAI

llm_provider: "openai"
llm_model: "gpt-4o-mini"
llm_base_url: "https://api.openai.com/v1"
llm_api_key: "sk-xxxxx"
🛠️ Manajemen Service

# Start/Stop/Restart
sudo systemctl start   bot-api bot-worker
sudo systemctl stop    bot-api bot-worker
sudo systemctl restart bot-api bot-worker

# Cek status
sudo systemctl status bot-api
sudo systemctl status bot-worker

# Lihat log real-time
tail -f logs/api.log
tail -f logs/worker.log
tail -f logs/api-error.log
📡 API Reference
Swagger UI tersedia di: http://localhost:5000/docs

Submit Query

curl -X POST http://localhost:5000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Apa itu machine learning?", "conversation_id": "test"}'

# Response (202):
# {"status":"accepted","task_id":"abc123","message":"Query submitted"}
Check Task Status

curl http://localhost:5000/api/v1/task/abc123

# Response (completed):
# {
#   "task_id": "abc123",
#   "status": "success",
#   "result": {
#     "answer": "Machine learning adalah...",
#     "sources": ["ml-intro.pdf", "https://example.com/ml"]
#   }
# }
Reload Engine Cache

curl -X POST http://localhost:5000/api/v1/reload
Health Check

curl http://localhost:5000/health
📂 Menambah Data Baru

source venv/bin/activate

# Tambah dari file
cp new-document.pdf data/
python ingest_data.py            # Replace semua
python ingest_data.py --append   # Append ke index yang ada

# Tambah dari website
python crawl.py https://new-site.com --max-pages 20

# Reload tanpa restart (atau restart service)
curl -X POST http://localhost:5000/api/v1/reload
sudo systemctl restart bot-worker
🔍 Troubleshooting
Masalah	Solusi
Ollama tidak terdeteksi	Pastikan ollama serve berjalan dan model sudah di-pull
Redis connection refused	sudo systemctl start redis-server
Webhook timeout (Messenger)	Pastikan Celery worker berjalan: sudo systemctl status bot-worker
FAISS index not found	Jalankan python ingest_data.py
Import error	Pastikan venv aktif: source venv/bin/activate
Permission denied (systemd)	Check user di service file, pastikan match
📜 License
MIT License



---

## Ringkasan Alur Kerja Sistem
┌─────────────────────────────────────────────────────────────┐
│ ALUR PEMROSESAN PESAN │
├─────────────────────────────────────────────────────────────┤
│ │
│ 1. User kirim pesan di Telegram/Messenger/WhatsApp │
│ │ │
│ 2. Platform kirim webhook ke FastAPI │
│ POST /webhooks/{platform} │
│ │ │
│ 3. FastAPI: │
│ ├── Verify token/signature │
│ ├── Parse payload → extract text & user_id │
│ ├── Submit Celery task (< 10ms) │
│ └── Return 200 OK immediately │
│ │ │
│ 4. Redis menyimpan task di queue │
│ │ │
│ 5. Celery Worker mengambil task: │
│ ├── core_rag.process_query() │
│ │ ├── FAISS similarity_search (k=10) │
│ │ ├── Cross-Encoder re-rank → top 3 │
│ │ ├── Build context + source metadata │
│ │ ├── ChatPromptTemplate + System Prompt │
│ │ └── LLM generate answer │
│ │ │
│ └── platform_adapters.send_{platform}_reply() │
│ ├── Format answer + sources │
│ ├── Split if exceeds char limit │
│ └── POST to platform API │
│ │ │
│ 6. User menerima jawaban + sumber referensi │
│ │
└─────────────────────────────────────────────────────────────┘



**Key design decisions:**

| Komponen | Pilihan | Alasan |
|----------|---------|--------|
| API Server | **FastAPI** | Async native, auto Swagger docs, type validation |
| Task Queue | **Celery + Redis** | Mencegah webhook timeout, retry otomatis, scalable |
| Vector DB | **FAISS (CPU)** | Ringan, cepat, tanpa external service |
| Re-ranker | **Cross-Encoder** | Meningkatkan relevansi $\sim$30-50% vs similarity saja |
| Config | **YAML** | Mudah dibaca, satu file untuk semua setting |
| Tunnel | **Cloudflare** | Gratis, HTTPS otomatis, stabil |

> **Catatan:** Setelah setiap perubahan `config.yaml` atau ingestion data baru, restart services:
> ```bash
> sudo systemctl restart bot-api bot-worker
> ```
> Atau gunakan endpoint `POST /api/v1/reload` untuk reload cache tanpa restart penuh (hanya berlaku untuk worker yang idle).
