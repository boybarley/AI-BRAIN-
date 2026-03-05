#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  AI Brain — One-Click Installer
#  RAG-Powered AI Assistant with Multi-Channel Integration
#  https://github.com/boybarley/ai-brain-
# ═══════════════════════════════════════════════════════════════
set -e

REPO_URL="https://github.com/boybarley/ai-brain-.git"
INSTALL_DIR="/root/ai-brain"

# ── Colors ───────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log_info()  { echo -e "  ${GREEN}✔${NC} $1"; }
log_warn()  { echo -e "  ${YELLOW}⚠${NC} $1"; }
log_error() { echo -e "  ${RED}✖${NC} $1"; }
log_step()  { echo -e "\n${BLUE}━━━ Step $1 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

# ── Banner ───────────────────────────────────────────────────
clear
echo -e "${CYAN}"
cat << 'BANNER'

     █████╗ ██╗    ██████╗ ██████╗  █████╗ ██╗███╗   ██╗
    ██╔══██╗██║    ██╔══██╗██╔══██╗██╔══██╗██║████╗  ██║
    ███████║██║    ██████╔╝██████╔╝███████║██║██╔██╗ ██║
    ██╔══██║██║    ██╔══██╗██╔══██╗██╔══██║██║██║╚██╗██║
    ██║  ██║██║    ██████╔╝██║  ██║██║  ██║██║██║ ╚████║
    ╚═╝  ╚═╝╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝
    ─────────────────────────────────────────────────────
    RAG-Powered AI Assistant · v1.0.0
    github.com/boybarley/ai-brain-

BANNER
echo -e "${NC}"

# ── Pre-flight ───────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    log_error "Please run as root: sudo bash install.sh"
    exit 1
fi

echo -e "${BOLD}This will install AI Brain to ${INSTALL_DIR}${NC}"
echo -e "Components: Python3, Redis, Ollama, FastAPI, Celery"
echo ""
read -rp "Continue? [Y/n] " CONFIRM
CONFIRM=${CONFIRM:-Y}
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

# ═════════════════════════════════════════════════════════════
log_step "1/7" "System Dependencies"
# ═════════════════════════════════════════════════════════════

echo -e "  Installing packages..."
apt-get update -qq > /dev/null 2>&1
apt-get install -y -qq \
    python3 python3-pip python3-venv \
    redis-server git curl wget \
    build-essential libffi-dev \
    > /dev/null 2>&1

systemctl enable redis-server > /dev/null 2>&1
systemctl start redis-server
log_info "System packages installed"
log_info "Redis: $(systemctl is-active redis-server)"

# ═════════════════════════════════════════════════════════════
log_step "2/7" "Ollama (Local Embedding Engine)"
# ═════════════════════════════════════════════════════════════

if command -v ollama &> /dev/null; then
    log_info "Ollama already installed"
else
    echo -e "  Downloading Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh > /dev/null 2>&1
    log_info "Ollama installed"
fi

systemctl enable ollama > /dev/null 2>&1
systemctl start ollama
sleep 3
log_info "Ollama: $(systemctl is-active ollama)"

# ═════════════════════════════════════════════════════════════
log_step "3/7" "Clone Repository"
# ═════════════════════════════════════════════════════════════

if [ -d "$INSTALL_DIR/.git" ]; then
    cd "$INSTALL_DIR"
    git pull origin main > /dev/null 2>&1 || true
    log_info "Repository updated"
elif [ -f "$INSTALL_DIR/api_server.py" ]; then
    log_info "Files already exist at $INSTALL_DIR"
else
    git clone "$REPO_URL" "$INSTALL_DIR" > /dev/null 2>&1
    log_info "Repository cloned"
fi

cd "$INSTALL_DIR"
mkdir -p data db logs
log_info "Directory structure ready"

# ═════════════════════════════════════════════════════════════
log_step "4/7" "Python Virtual Environment"
# ═════════════════════════════════════════════════════════════

echo -e "  Creating venv & installing packages (this takes 1-2 min)..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt > /dev/null 2>&1
log_info "$(pip list 2>/dev/null | wc -l) packages installed"

# ═════════════════════════════════════════════════════════════
log_step "5/7" "Download Embedding Model"
# ═════════════════════════════════════════════════════════════

echo -e "  Pulling nomic-embed-text (~274 MB)..."
ollama pull nomic-embed-text > /dev/null 2>&1
log_info "nomic-embed-text ready"

# ═════════════════════════════════════════════════════════════
log_step "6/7" "Configuration"
# ═════════════════════════════════════════════════════════════

if [ ! -f config.yaml ]; then
    cp config.yaml.example config.yaml

    echo ""
    echo -e "  ${CYAN}╭──────────────────────────────────────────────╮${NC}"
    echo -e "  ${CYAN}│  LLM Provider Setup                          │${NC}"
    echo -e "  ${CYAN}│                                               │${NC}"
    echo -e "  ${CYAN}│  Recommended: OpenRouter (cloud, low RAM)    │${NC}"
    echo -e "  ${CYAN}│  Get API key: https://openrouter.ai/keys     │${NC}"
    echo -e "  ${CYAN}╰──────────────────────────────────────────────╯${NC}"
    echo ""
    read -rp "  Paste your OpenRouter API key (Enter to skip): " API_KEY

    if [ -n "$API_KEY" ]; then
        sed -i "s|YOUR_OPENROUTER_API_KEY|$API_KEY|g" config.yaml
        log_info "API key configured"
    else
        log_warn "Skipped — edit config.yaml later: nano $INSTALL_DIR/config.yaml"
    fi
else
    log_info "config.yaml exists — keeping current settings"
fi

# ═════════════════════════════════════════════════════════════
log_step "7/7" "Systemd Services"
# ═════════════════════════════════════════════════════════════

cat > /etc/systemd/system/bot-api.service << SVCEOF
[Unit]
Description=AI Brain — FastAPI Server
After=network.target redis-server.service ollama.service
Wants=redis-server.service
[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/venv/bin:/usr/local/bin:/usr/bin"
ExecStart=$INSTALL_DIR/venv/bin/uvicorn api_server:app --host 0.0.0.0 --port 5000 --workers 1
Restart=always
RestartSec=5
StandardOutput=append:$INSTALL_DIR/logs/api.log
StandardError=append:$INSTALL_DIR/logs/api-error.log
[Install]
WantedBy=multi-user.target
SVCEOF

cat > /etc/systemd/system/bot-worker.service << SVCEOF
[Unit]
Description=AI Brain — Celery Worker
After=network.target redis-server.service ollama.service
Wants=redis-server.service
[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/venv/bin:/usr/local/bin:/usr/bin"
ExecStart=$INSTALL_DIR/venv/bin/celery -A tasks worker --loglevel=info --concurrency=1 --pool=solo
Restart=always
RestartSec=10
StandardOutput=append:$INSTALL_DIR/logs/worker.log
StandardError=append:$INSTALL_DIR/logs/worker-error.log
[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable bot-api bot-worker > /dev/null 2>&1

# ── Ingest sample data ──────────────────────────────────────
if [ -f "$INSTALL_DIR/data/sample.txt" ]; then
    echo -e "  Ingesting sample data..."
    cd "$INSTALL_DIR"
    source venv/bin/activate
    python ingest_data.py > /dev/null 2>&1 || true
    log_info "Sample data ingested"
fi

# ── Start services ──────────────────────────────────────────
systemctl start bot-api bot-worker
sleep 3

# ═════════════════════════════════════════════════════════════
# ── Summary ─────────────────────────────────────────────────
# ═════════════════════════════════════════════════════════════

SERVER_IP=$(hostname -I | awk '{print $1}')
API_STATUS=$(systemctl is-active bot-api 2>/dev/null || echo "inactive")
WORKER_STATUS=$(systemctl is-active bot-worker 2>/dev/null || echo "inactive")

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  ✅ AI BRAIN INSTALLED SUCCESSFULLY!${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BOLD}Service Status:${NC}"
echo -e "    API Server:  $([ "$API_STATUS" = "active" ] && echo -e "${GREEN}● active${NC}" || echo -e "${RED}● $API_STATUS${NC}")  →  http://$SERVER_IP:5000"
echo -e "    Worker:      $([ "$WORKER_STATUS" = "active" ] && echo -e "${GREEN}● active${NC}" || echo -e "${RED}● $WORKER_STATUS${NC}")"
echo -e "    Redis:       $(systemctl is-active redis-server 2>/dev/null | sed "s/active/\\${GREEN}● active\\${NC}/" | sed "s/inactive/\\${RED}● inactive\\${NC}/")"
echo -e "    Ollama:      $(systemctl is-active ollama 2>/dev/null | sed "s/active/\\${GREEN}● active\\${NC}/" | sed "s/inactive/\\${RED}● inactive\\${NC}/")"
echo ""
echo -e "  ${BOLD}Quick Test:${NC}"
echo -e "    curl http://localhost:5000/health"
echo ""
echo -e "  ${BOLD}Next Steps:${NC}"
echo -e "    1. Add documents:  cp your-files.pdf $INSTALL_DIR/data/"
echo -e "    2. Ingest:         cd $INSTALL_DIR && source venv/bin/activate && python ingest_data.py"
echo -e "    3. Crawl website:  python crawl.py https://yoursite.com"
echo ""
if [ -z "$API_KEY" ]; then
echo -e "  ${YELLOW}⚠ Don't forget to set your API key:${NC}"
echo -e "    nano $INSTALL_DIR/config.yaml"
echo -e "    sudo systemctl restart bot-api bot-worker"
echo ""
fi
echo -e "  ${BOLD}Documentation:${NC} https://github.com/boybarley/ai-brain-"
echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
echo ""
