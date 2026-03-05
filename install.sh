#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════╗
# ║        AI Brain — Automated Installation Script          ║
# ║            Tested on Ubuntu 22.04 / 24.04 LTS           ║
# ╚══════════════════════════════════════════════════════════╝
set -euo pipefail

# ─── Variables ───────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${PROJECT_DIR}/venv"
CURRENT_USER="$(whoami)"
PYTHON="python3"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; }

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║          AI BRAIN — Installation Script              ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  Project Dir: ${PROJECT_DIR}"
echo "║  User:        ${CURRENT_USER}"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ─── Step 1: System Dependencies ────────────────────────
info "Step 1/7: Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 \
    python3-venv \
    python3-pip \
    python3-dev \
    build-essential \
    redis-server \
    curl \
    git
success "System dependencies installed"

# ─── Step 2: Python Virtual Environment ─────────────────
info "Step 2/7: Setting up Python virtual environment..."
if [ ! -d "${VENV_DIR}" ]; then
    ${PYTHON} -m venv "${VENV_DIR}"
    success "Virtual environment created at ${VENV_DIR}"
else
    warn "Virtual environment already exists, reusing..."
fi

# Activate venv
source "${VENV_DIR}/bin/activate"
pip install --upgrade pip -q
success "Virtual environment activated"

# ─── Step 3: Python Dependencies ────────────────────────
info "Step 3/7: Installing Python dependencies..."
pip install -r "${PROJECT_DIR}/requirements.txt" -q
success "Python dependencies installed"

# ─── Step 4: Project Directories ────────────────────────
info "Step 4/7: Creating project directories..."
mkdir -p "${PROJECT_DIR}/data"
mkdir -p "${PROJECT_DIR}/db"
mkdir -p "${PROJECT_DIR}/logs"
success "Directories created: data/, db/, logs/"

# ─── Step 5: Config File ────────────────────────────────
info "Step 5/7: Checking configuration..."
if [ ! -f "${PROJECT_DIR}/config.yaml" ]; then
    error "config.yaml not found! Please create it before continuing."
    error "See README.md for the template."
    exit 1
else
    success "config.yaml found"
fi

# ─── Step 6: Redis ──────────────────────────────────────
info "Step 6/7: Configuring Redis..."
sudo systemctl enable redis-server
sudo systemctl start redis-server

# Verify Redis is running
if redis-cli ping > /dev/null 2>&1; then
    success "Redis is running (PONG received)"
else
    error "Redis is not responding! Check: sudo systemctl status redis-server"
    exit 1
fi

# ─── Step 7: Systemd Services ───────────────────────────
info "Step 7/7: Setting up systemd services..."

# --- bot-api.service ---
sudo tee /etc/systemd/system/bot-api.service > /dev/null <<SERVICEEOF
[Unit]
Description=AI Brain — FastAPI Server
Documentation=https://github.com/ai-brain
After=network.target redis-server.service
Wants=redis-server.service

[Service]
Type=simple
User=${CURRENT_USER}
Group=${CURRENT_USER}
WorkingDirectory=${PROJECT_DIR}
Environment="PATH=${VENV_DIR}/bin:/usr/local/bin:/usr/bin"
Environment="PYTHONUNBUFFERED=1"
ExecStart=${VENV_DIR}/bin/uvicorn api_server:app \\
    --host 0.0.0.0 \\
    --port 5000 \\
    --workers 2 \\
    --log-level info
Restart=always
RestartSec=5
StandardOutput=append:${PROJECT_DIR}/logs/api.log
StandardError=append:${PROJECT_DIR}/logs/api-error.log

[Install]
WantedBy=multi-user.target
SERVICEEOF

# --- bot-worker.service ---
sudo tee /etc/systemd/system/bot-worker.service > /dev/null <<SERVICEEOF
[Unit]
Description=AI Brain — Celery Worker
Documentation=https://github.com/ai-brain
After=network.target redis-server.service
Wants=redis-server.service

[Service]
Type=simple
User=${CURRENT_USER}
Group=${CURRENT_USER}
WorkingDirectory=${PROJECT_DIR}
Environment="PATH=${VENV_DIR}/bin:/usr/local/bin:/usr/bin"
Environment="PYTHONUNBUFFERED=1"
ExecStart=${VENV_DIR}/bin/celery -A tasks worker \\
    --loglevel=info \\
    --concurrency=2 \\
    --max-tasks-per-child=100
Restart=always
RestartSec=5
StandardOutput=append:${PROJECT_DIR}/logs/worker.log
StandardError=append:${PROJECT_DIR}/logs/worker-error.log

[Install]
WantedBy=multi-user.target
SERVICEEOF

# Reload and enable
sudo systemctl daemon-reload
sudo systemctl enable bot-api bot-worker
success "Systemd services created and enabled"

# ─── Start Services ─────────────────────────────────────
info "Starting services..."
sudo systemctl start bot-api
sudo systemctl start bot-worker
sleep 2

# ─── Summary ────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║           ✅ Installation Complete!                  ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

info "Service Status:"
echo "  ┌─────────────────────────────────────────────────────"
printf "  │ bot-api:    "
if systemctl is-active --quiet bot-api; then
    echo -e "${GREEN}RUNNING${NC}"
else
    echo -e "${RED}STOPPED${NC}"
fi
printf "  │ bot-worker: "
if systemctl is-active --quiet bot-worker; then
    echo -e "${GREEN}RUNNING${NC}"
else
    echo -e "${RED}STOPPED${NC}"
fi
printf "  │ redis:      "
if systemctl is-active --quiet redis-server; then
    echo -e "${GREEN}RUNNING${NC}"
else
    echo -e "${RED}STOPPED${NC}"
fi
echo "  └─────────────────────────────────────────────────────"

echo ""
info "🔗 API Endpoints:"
echo "  │ Swagger UI:  http://localhost:5000/docs"
echo "  │ Health:      http://localhost:5000/health"
echo "  │ Query API:   POST http://localhost:5000/api/v1/query"
echo ""
info "📋 Next Steps:"
echo "  │ 1. Edit config.yaml with your API keys"
echo "  │ 2. Place documents in data/ folder"
echo "  │ 3. Run: source venv/bin/activate && python ingest_data.py"
echo "  │ 4. Setup Cloudflare Tunnel → http://localhost:5000"
echo "  │ 5. Configure platform webhooks (Messenger/Telegram/WhatsApp)"
echo ""
info "🔧 Managing Services:"
echo "  │ sudo systemctl start|stop|restart bot-api bot-worker"
echo "  │ tail -f logs/api.log"
echo "  │ tail -f logs/worker.log"
echo ""
