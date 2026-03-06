#!/bin/bash
#══════════════════════════════════════════════════════════════
#              AI-BRAIN INSTALLER v2.0
#══════════════════════════════════════════════════════════════

set -e

GREEN='\033[92m'
RED='\033[91m'
CYAN='\033[96m'
YELLOW='\033[93m'
BOLD='\033[1m'
RESET='\033[0m'

echo -e "${CYAN}${BOLD}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║              🧠 AI-BRAIN INSTALLER v2.0                     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${RESET}"

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$BASE_DIR"

# ─── Step 1: System packages ────────────────────────────
echo -e "${YELLOW}[1/7] Installing system packages...${RESET}"
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv git curl wget lsof > /dev/null 2>&1
echo -e "${GREEN}  ✅ System packages OK${RESET}"

# ─── Step 2: Python venv ────────────────────────────────
echo -e "${YELLOW}[2/7] Setting up Python virtual environment...${RESET}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}  ✅ Venv created${RESET}"
else
    echo -e "${GREEN}  ✅ Venv already exists${RESET}"
fi
source venv/bin/activate

# ─── Step 3: Python packages ────────────────────────────
echo -e "${YELLOW}[3/7] Installing Python packages...${RESET}"
pip install --upgrade pip -q

pip install -q \
    requests \
    pyyaml \
    psutil \
    flask \
    flask-cors \
    fastapi \
    uvicorn \
    langchain \
    langchain-community \
    sentence-transformers \
    faiss-cpu \
    beautifulsoup4 \
    crawl4ai \
    trafilatura \
    feedparser \
    schedule \
    python-dotenv \
    rich

echo -e "${GREEN}  ✅ Python packages OK${RESET}"

# ─── Step 4: Ollama ─────────────────────────────────────
echo -e "${YELLOW}[4/7] Checking Ollama...${RESET}"
if command -v ollama &> /dev/null; then
    echo -e "${GREEN}  ✅ Ollama already installed${RESET}"
else
    echo "  Installing Ollama..."
    curl -fsSL https://ollama.ai/install.sh | sh
    echo -e "${GREEN}  ✅ Ollama installed${RESET}"
fi

# Start Ollama if not running
if ! pgrep -x "ollama" > /dev/null; then
    echo "  Starting Ollama..."
    ollama serve &>/dev/null &
    sleep 3
fi

# Pull default model if none exists
MODELS=$(ollama list 2>/dev/null | tail -n +2 | wc -l)
if [ "$MODELS" -eq 0 ]; then
    echo "  Pulling default model (mistral)... this may take a while"
    ollama pull mistral
    echo -e "${GREEN}  ✅ Model mistral pulled${RESET}"
else
    echo -e "${GREEN}  ✅ Ollama has $MODELS model(s)${RESET}"
fi

# Pull embedding model
if ! ollama list 2>/dev/null | grep -q "nomic-embed-text"; then
    echo "  Pulling embedding model..."
    ollama pull nomic-embed-text
    echo -e "${GREEN}  ✅ nomic-embed-text pulled${RESET}"
else
    echo -e "${GREEN}  ✅ Embedding model exists${RESET}"
fi

# ─── Step 5: Create directories ─────────────────────────
echo -e "${YELLOW}[5/7] Creating directories...${RESET}"
mkdir -p data db logs backups
echo -e "${GREEN}  ✅ Directories OK${RESET}"

# ─── Step 6: Generate config ────────────────────────────
echo -e "${YELLOW}[6/7] Generating configuration...${RESET}"
if [ -f "settings.py" ]; then
    python3 settings.py optimize
    echo -e "${GREEN}  ✅ Config auto-optimized${RESET}"
else
    echo -e "${RED}  ⚠️ settings.py not found, skipping${RESET}"
fi

# ─── Step 7: Create crawl_sites.json if missing ─────────
echo -e "${YELLOW}[7/7] Checking crawl sites...${RESET}"
if [ ! -f "crawl_sites.json" ]; then
    cat > crawl_sites.json << 'SITES'
{
  "sites": [
    {
      "name": "Detik News",
      "url": "https://www.detik.com",
      "enabled": true
    },
    {
      "name": "Kompas",
      "url": "https://www.kompas.com",
      "enabled": true
    },
    {
      "name": "CNN Indonesia",
      "url": "https://www.cnnindonesia.com",
      "enabled": true
    }
  ]
}
SITES
    echo -e "${GREEN}  ✅ Default crawl sites created${RESET}"
else
    echo -e "${GREEN}  ✅ Crawl sites exists${RESET}"
fi

# ─── Done ────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║              ✅ INSTALLATION COMPLETE!                      ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║                                                            ║"
echo "║  Quick Start:                                              ║"
echo "║    source venv/bin/activate                                ║"
echo "║    python3 manage.py          # Main Dashboard             ║"
echo "║    python3 settings.py        # Settings Center            ║"
echo "║                                                            ║"
echo "║  CLI Commands:                                             ║"
echo "║    python3 settings.py detect    # System info             ║"
echo "║    python3 settings.py validate  # Check config            ║"
echo "║    python3 settings.py optimize  # Auto-optimize           ║"
echo "║                                                            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${RESET}"
