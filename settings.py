#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║              AI-BRAIN SETTINGS CENTER v2.0                  ║
║          Centralized Configuration Management               ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import sys
import yaml
import json
import shutil
import subprocess
import requests
import psutil
from pathlib import Path
from datetime import datetime

# ─── Paths ───────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.yaml"
CRAWL_FILE = BASE_DIR / "crawl_sites.json"
DATA_DIR = BASE_DIR / "data"
DB_DIR = BASE_DIR / "db"
LOG_DIR = BASE_DIR / "logs"
BACKUP_DIR = BASE_DIR / "backups"

# ─── Default Configuration ───────────────────────────────
DEFAULT_CONFIG = {
    "system": {
        "name": "AI-BRAIN",
        "version": "2.0",
        "language": "id",  # id, en
        "debug": False,
        "log_level": "INFO",  # DEBUG, INFO, WARNING, ERROR
        "auto_start": True,
        "timezone": "Asia/Jakarta",
    },
    "models": {
        "provider": "ollama",  # ollama, openrouter, hybrid
        "ollama": {
            "enabled": True,
            "host": "http://localhost:11434",
            "default_model": "mistral",
            "embedding_model": "nomic-embed-text",
            "installed_models": [],
            "auto_pull": True,
            "gpu_layers": -1,  # -1 = auto
            "context_length": 4096,
            "temperature": 0.7,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
        },
        "openrouter": {
            "enabled": False,
            "api_key": "",
            "default_model": "mistralai/mistral-7b-instruct",
            "fallback_model": "google/gemma-2-9b-it:free",
            "max_tokens": 2048,
            "temperature": 0.7,
            "budget_limit_daily": 1.0,  # USD
            "budget_spent_today": 0.0,
        },
        "hybrid": {
            "strategy": "local_first",  # local_first, cloud_first, smart
            "fallback_enabled": True,
            "cloud_for_complex_only": True,
            "complexity_threshold": 0.7,
        }
    },
    "rag": {
        "enabled": True,
        "engine": "faiss",  # faiss, chroma
        "faiss": {
            "index_path": "db/faiss_index",
            "dimension": 768,
            "metric": "cosine",  # cosine, l2, ip
            "nprobe": 10,
        },
        "chunking": {
            "method": "recursive",  # fixed, recursive, semantic
            "chunk_size": 500,
            "chunk_overlap": 50,
            "min_chunk_size": 100,
        },
        "retrieval": {
            "top_k": 5,
            "score_threshold": 0.3,
            "reranking": False,
            "context_window": 3,
        },
    },
    "crawler": {
        "enabled": True,
        "schedule": "daily",  # manual, hourly, daily, weekly
        "schedule_time": "02:00",
        "max_pages_per_site": 50,
        "max_depth": 3,
        "timeout": 30,
        "delay_between_requests": 1.0,
        "user_agent": "AI-BRAIN-Crawler/2.0",
        "respect_robots_txt": True,
        "sites": [],
    },
    "api": {
        "enabled": True,
        "host": "0.0.0.0",
        "port": 8000,
        "cors_origins": ["*"],
        "rate_limit": 60,  # requests per minute
        "auth_enabled": False,
        "api_key": "",
        "ssl_enabled": False,
    },
    "dashboard": {
        "enabled": True,
        "port": 5000,
        "theme": "dark",  # dark, light
        "refresh_interval": 30,
        "show_system_stats": True,
    },
    "telegram": {
        "enabled": False,
        "bot_token": "",
        "allowed_users": [],
        "admin_users": [],
        "webhook_url": "",
    },
    "security": {
        "encrypt_config": False,
        "api_key_rotation_days": 90,
        "max_input_length": 10000,
        "blocked_words": [],
        "rate_limit_per_ip": 30,
    },
    "backup": {
        "enabled": True,
        "schedule": "weekly",
        "keep_last": 5,
        "include_data": True,
        "include_index": True,
    },
    "performance": {
        "max_workers": 4,
        "batch_size": 32,
        "cache_enabled": True,
        "cache_ttl": 3600,
        "max_memory_mb": 2048,
        "gpu_memory_fraction": 0.8,
    }
}


class Settings:
    """AI-Brain Settings Manager"""

    def __init__(self):
        self.config = {}
        self.load()

    # ─── Core Methods ────────────────────────────────────

    def load(self):
        """Load config from file or create default"""
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r') as f:
                self.config = yaml.safe_load(f) or {}
            # Merge with defaults (add new keys)
            self.config = self._deep_merge(DEFAULT_CONFIG, self.config)
        else:
            self.config = DEFAULT_CONFIG.copy()
            self.save()

    def save(self):
        """Save config to file"""
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def get(self, key_path, default=None):
        """Get nested config value: get('models.ollama.host')"""
        keys = key_path.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set(self, key_path, value):
        """Set nested config value: set('models.ollama.host', 'http://...')"""
        keys = key_path.split('.')
        config = self.config
        for k in keys[:-1]:
            config = config.setdefault(k, {})
        config[keys[-1]] = value
        self.save()

    def _deep_merge(self, default, override):
        """Deep merge two dicts"""
        result = default.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    # ─── Auto Detection ──────────────────────────────────

    def detect_system(self):
        """Auto-detect system capabilities"""
        info = {
            "hostname": os.uname().nodename,
            "cpu_cores": psutil.cpu_count(),
            "ram_total_gb": round(psutil.virtual_memory().total / (1024**3), 1),
            "ram_available_gb": round(psutil.virtual_memory().available / (1024**3), 1),
            "ram_usage_pct": psutil.virtual_memory().percent,
            "disk_total_gb": round(psutil.disk_usage('/').total / (1024**3), 1),
            "disk_free_gb": round(psutil.disk_usage('/').free / (1024**3), 1),
            "gpu": self._detect_gpu(),
            "ollama_running": self._check_ollama(),
            "ollama_models": self._get_ollama_models(),
            "python_version": sys.version.split()[0],
            "faiss_index_exists": Path(self.get('rag.faiss.index_path', 'db/faiss_index')).exists(),
        }
        return info

    def _detect_gpu(self):
        """Detect GPU"""
        try:
            result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,memory.free',
                                   '--format=csv,noheader,nounits'],
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                parts = result.stdout.strip().split(', ')
                return {
                    "available": True,
                    "name": parts[0],
                    "memory_total_mb": int(parts[1]),
                    "memory_free_mb": int(parts[2]),
                }
        except:
            pass
        return {"available": False, "name": "None", "memory_total_mb": 0}

    def _check_ollama(self):
        """Check if Ollama is running"""
        try:
            r = requests.get(self.get('models.ollama.host', 'http://localhost:11434') + '/api/tags', timeout=3)
            return r.status_code == 200
        except:
            return False

    def _get_ollama_models(self):
        """Get installed Ollama models"""
        try:
            host = self.get('models.ollama.host', 'http://localhost:11434')
            r = requests.get(f'{host}/api/tags', timeout=5)
            if r.status_code == 200:
                models = [m['name'] for m in r.json().get('models', [])]
                self.set('models.ollama.installed_models', models)
                return models
        except:
            pass
        return []

    def detect_and_optimize(self):
        """Auto-detect and optimize settings"""
        info = self.detect_system()
        ram = info['ram_total_gb']
        changes = []

        # RAM-based optimization
        if ram <= 2:
            self.set('models.ollama.context_length', 2048)
            self.set('rag.chunking.chunk_size', 300)
            self.set('performance.max_workers', 2)
            self.set('performance.max_memory_mb', 1024)
            changes.append("⚡ Low RAM mode (≤2GB)")
        elif ram <= 4:
            self.set('models.ollama.context_length', 4096)
            self.set('rag.chunking.chunk_size', 500)
            self.set('performance.max_workers', 4)
            self.set('performance.max_memory_mb', 2048)
            changes.append("⚡ Medium RAM mode (≤4GB)")
        else:
            self.set('models.ollama.context_length', 8192)
            self.set('rag.chunking.chunk_size', 1000)
            self.set('performance.max_workers', 8)
            self.set('performance.max_memory_mb', 4096)
            changes.append("🚀 High RAM mode (>4GB)")

        # GPU optimization
        if info['gpu']['available']:
            self.set('models.ollama.gpu_layers', -1)
            changes.append(f"🎮 GPU detected: {info['gpu']['name']}")
        else:
            self.set('models.ollama.gpu_layers', 0)
            changes.append("💻 CPU-only mode")

        # Provider auto-select
        if info['ollama_running'] and info['ollama_models']:
            self.set('models.provider', 'ollama')
            changes.append(f"🤖 Ollama active: {', '.join(info['ollama_models'][:3])}")
        elif self.get('models.openrouter.api_key'):
            self.set('models.provider', 'openrouter')
            changes.append("☁️ Using OpenRouter (Ollama not available)")

        self.save()
        return changes

    # ─── Backup & Restore ────────────────────────────────

    def backup(self):
        """Backup current config"""
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = BACKUP_DIR / f"config_backup_{timestamp}.yaml"
        shutil.copy2(CONFIG_FILE, backup_file)

        # Keep only last N backups
        keep = self.get('backup.keep_last', 5)
        backups = sorted(BACKUP_DIR.glob('config_backup_*.yaml'), reverse=True)
        for old in backups[keep:]:
            old.unlink()
        return backup_file

    def restore(self, backup_file=None):
        """Restore from backup"""
        if backup_file is None:
            backups = sorted(BACKUP_DIR.glob('config_backup_*.yaml'), reverse=True)
            if not backups:
                return None
            backup_file = backups[0]
        shutil.copy2(backup_file, CONFIG_FILE)
        self.load()
        return backup_file

    def list_backups(self):
        """List available backups"""
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        return sorted(BACKUP_DIR.glob('config_backup_*.yaml'), reverse=True)

    # ─── Validation ──────────────────────────────────────

    def validate(self):
        """Validate current configuration"""
        issues = []
        warnings = []

        # Check Ollama
        if self.get('models.provider') in ['ollama', 'hybrid']:
            if not self._check_ollama():
                issues.append("❌ Ollama not running")
            elif not self._get_ollama_models():
                warnings.append("⚠️ No Ollama models installed")

        # Check OpenRouter
        if self.get('models.provider') in ['openrouter', 'hybrid']:
            key = self.get('models.openrouter.api_key', '')
            if not key:
                issues.append("❌ OpenRouter API key not set")
            else:
                try:
                    r = requests.get('https://openrouter.ai/api/v1/models',
                                   headers={'Authorization': f'Bearer {key}'}, timeout=5)
                    if r.status_code != 200:
                        issues.append("❌ OpenRouter API key invalid")
                except:
                    warnings.append("⚠️ Cannot reach OpenRouter API")

        # Check directories
        for d in [DATA_DIR, DB_DIR]:
            if not d.exists():
                warnings.append(f"⚠️ Directory missing: {d}")

        # Check FAISS index
        if self.get('rag.enabled'):
            idx_path = Path(self.get('rag.faiss.index_path', 'db/faiss_index'))
            if not idx_path.exists():
                warnings.append("⚠️ FAISS index not built yet")

        # Check disk space
        disk_free = psutil.disk_usage('/').free / (1024**3)
        if disk_free < 1:
            issues.append(f"❌ Low disk space: {disk_free:.1f}GB free")
        elif disk_free < 5:
            warnings.append(f"⚠️ Disk space low: {disk_free:.1f}GB free")

        return {"issues": issues, "warnings": warnings, "valid": len(issues) == 0}

    # ─── Export / Import ─────────────────────────────────

    def export_json(self, filepath=None):
        """Export config as JSON"""
        if filepath is None:
            filepath = BASE_DIR / "config_export.json"
        safe_config = self.config.copy()
        # Mask secrets
        if 'openrouter' in safe_config.get('models', {}):
            key = safe_config['models']['openrouter'].get('api_key', '')
            if key:
                safe_config['models']['openrouter']['api_key'] = key[:8] + '...'
        if 'telegram' in safe_config:
            token = safe_config['telegram'].get('bot_token', '')
            if token:
                safe_config['telegram']['bot_token'] = token[:8] + '...'
        with open(filepath, 'w') as f:
            json.dump(safe_config, f, indent=2)
        return filepath

    # ─── Reset ───────────────────────────────────────────

    def reset(self, section=None):
        """Reset config to defaults"""
        self.backup()
        if section and section in DEFAULT_CONFIG:
            self.config[section] = DEFAULT_CONFIG[section].copy()
        else:
            self.config = DEFAULT_CONFIG.copy()
        self.save()


# ═════════════════════════════════════════════════════════
#                    INTERACTIVE TUI
# ═════════════════════════════════════════════════════════

class SettingsTUI:
    """Terminal UI for Settings"""

    def __init__(self):
        self.settings = Settings()
        self.GREEN = '\033[92m'
        self.RED = '\033[91m'
        self.YELLOW = '\033[93m'
        self.CYAN = '\033[96m'
        self.BLUE = '\033[94m'
        self.BOLD = '\033[1m'
        self.DIM = '\033[2m'
        self.RESET = '\033[0m'

    def clear(self):
        os.system('clear' if os.name != 'nt' else 'cls')

    def header(self):
        print(f"""{self.CYAN}{self.BOLD}
╔══════════════════════════════════════════════════════════════╗
║           ⚙️  AI-BRAIN SETTINGS CENTER v2.0  ⚙️              ║
╠══════════════════════════════════════════════════════════════╣
║  Centralized Configuration Management                       ║
╚══════════════════════════════════════════════════════════════╝{self.RESET}""")

    def show_menu(self):
        self.clear()
        self.header()

        # Quick status
        info = self.settings.detect_system()
        provider = self.settings.get('models.provider', 'ollama')
        print(f"""
{self.DIM}┌─ Quick Status ─────────────────────────────────────────────┐{self.RESET}
  💻 RAM: {info['ram_available_gb']:.1f}/{info['ram_total_gb']}GB │ 💾 Disk: {info['disk_free_gb']:.0f}GB free
  🤖 Ollama: {'🟢 Running' if info['ollama_running'] else '🔴 Stopped'} │ Provider: {self.BOLD}{provider}{self.RESET}
  📦 Models: {', '.join(info['ollama_models'][:3]) or 'None'}
{self.DIM}└────────────────────────────────────────────────────────────┘{self.RESET}

{self.BOLD}  [1]{self.RESET} 🤖 Model Settings      (Ollama / OpenRouter / Hybrid)
{self.BOLD}  [2]{self.RESET} 📚 RAG & FAISS         (Embedding, Chunking, Retrieval)
{self.BOLD}  [3]{self.RESET} 🕷️  Crawler Settings    (Sites, Schedule, Depth)
{self.BOLD}  [4]{self.RESET} 🌐 API Settings        (Port, Auth, Rate Limit)
{self.BOLD}  [5]{self.RESET} 📱 Telegram Bot        (Token, Users, Webhook)
{self.BOLD}  [6]{self.RESET} 🎨 Dashboard           (Theme, Port, Refresh)
{self.BOLD}  [7]{self.RESET} ⚡ Performance         (Workers, Cache, Memory)
{self.BOLD}  [8]{self.RESET} 🔒 Security            (Auth, Rate Limit, Encryption)

{self.BOLD}  [A]{self.RESET} 🔍 Auto-Detect & Optimize
{self.BOLD}  [V]{self.RESET} ✅ Validate Configuration
{self.BOLD}  [B]{self.RESET} 💾 Backup / Restore
{self.BOLD}  [E]{self.RESET} 📤 Export Config
{self.BOLD}  [R]{self.RESET} 🔄 Reset to Defaults

{self.BOLD}  [0]{self.RESET} ← Back to Dashboard
""")

    def run(self):
        while True:
            self.show_menu()
            choice = input(f"  {self.CYAN}Select [0-8/A/V/B/E/R]:{self.RESET} ").strip().upper()

            if choice == '0':
                break
            elif choice == '1':
                self.model_settings()
            elif choice == '2':
                self.rag_settings()
            elif choice == '3':
                self.crawler_settings()
            elif choice == '4':
                self.api_settings()
            elif choice == '5':
                self.telegram_settings()
            elif choice == '6':
                self.dashboard_settings()
            elif choice == '7':
                self.performance_settings()
            elif choice == '8':
                self.security_settings()
            elif choice == 'A':
                self.auto_detect()
            elif choice == 'V':
                self.validate()
            elif choice == 'B':
                self.backup_restore()
            elif choice == 'E':
                self.export_config()
            elif choice == 'R':
                self.reset_config()

    # ─── Model Settings ──────────────────────────────────

    def model_settings(self):
        while True:
            self.clear()
            s = self.settings
            provider = s.get('models.provider')

            print(f"""{self.CYAN}{self.BOLD}
╔══════════════════════════════════════════════════════════════╗
║                   🤖 MODEL SETTINGS                         ║
╚══════════════════════════════════════════════════════════════╝{self.RESET}

  Current Provider: {self.BOLD}{self.GREEN}{provider}{self.RESET}

{self.BOLD}── Ollama (Local) ──────────────────────────────────────────{self.RESET}
  Enabled:      {self._bool_icon(s.get('models.ollama.enabled'))}
  Host:         {s.get('models.ollama.host')}
  Model:        {s.get('models.ollama.default_model')}
  Embedding:    {s.get('models.ollama.embedding_model')}
  Context:      {s.get('models.ollama.context_length')}
  Temperature:  {s.get('models.ollama.temperature')}
  GPU Layers:   {s.get('models.ollama.gpu_layers')}

{self.BOLD}── OpenRouter (Cloud) ──────────────────────────────────────{self.RESET}
  Enabled:      {self._bool_icon(s.get('models.openrouter.enabled'))}
  API Key:      {self._mask_key(s.get('models.openrouter.api_key', ''))}
  Model:        {s.get('models.openrouter.default_model')}
  Fallback:     {s.get('models.openrouter.fallback_model')}
  Budget/Day:   ${s.get('models.openrouter.budget_limit_daily')}

{self.BOLD}── Hybrid Mode ────────────────────────────────────────────{self.RESET}
  Strategy:     {s.get('models.hybrid.strategy')}
  Fallback:     {self._bool_icon(s.get('models.hybrid.fallback_enabled'))}

{self.BOLD}  [1]{self.RESET} Switch Provider (ollama/openrouter/hybrid)
{self.BOLD}  [2]{self.RESET} Set Ollama Model
{self.BOLD}  [3]{self.RESET} Set Ollama Embedding Model
{self.BOLD}  [4]{self.RESET} Set OpenRouter API Key
{self.BOLD}  [5]{self.RESET} Set OpenRouter Model
{self.BOLD}  [6]{self.RESET} Set Temperature
{self.BOLD}  [7]{self.RESET} Set Context Length
{self.BOLD}  [8]{self.RESET} Set Budget Limit
{self.BOLD}  [9]{self.RESET} Pull Ollama Model
{self.BOLD}  [0]{self.RESET} ← Back
""")
            ch = input(f"  {self.CYAN}Select:{self.RESET} ").strip()

            if ch == '0':
                break
            elif ch == '1':
                p = input("  Provider (ollama/openrouter/hybrid): ").strip().lower()
                if p in ['ollama', 'openrouter', 'hybrid']:
                    s.set('models.provider', p)
                    if p == 'openrouter':
                        s.set('models.openrouter.enabled', True)
                    elif p == 'ollama':
                        s.set('models.ollama.enabled', True)
                    elif p == 'hybrid':
                        s.set('models.ollama.enabled', True)
                        s.set('models.openrouter.enabled', True)
                    print(f"  {self.GREEN}✅ Provider set to: {p}{self.RESET}")
            elif ch == '2':
                models = s._get_ollama_models()
                if models:
                    print(f"  Available: {', '.join(models)}")
                m = input("  Model name: ").strip()
                if m:
                    s.set('models.ollama.default_model', m)
                    print(f"  {self.GREEN}✅ Model: {m}{self.RESET}")
            elif ch == '3':
                m = input("  Embedding model (e.g. nomic-embed-text): ").strip()
                if m:
                    s.set('models.ollama.embedding_model', m)
                    print(f"  {self.GREEN}✅ Embedding: {m}{self.RESET}")
            elif ch == '4':
                key = input("  OpenRouter API Key: ").strip()
                if key:
                    s.set('models.openrouter.api_key', key)
                    print(f"  {self.GREEN}✅ API Key saved{self.RESET}")
            elif ch == '5':
                m = input("  OpenRouter model (e.g. mistralai/mistral-7b-instruct): ").strip()
                if m:
                    s.set('models.openrouter.default_model', m)
                    print(f"  {self.GREEN}✅ Model: {m}{self.RESET}")
            elif ch == '6':
                t = input("  Temperature (0.0-2.0): ").strip()
                try:
                    t = float(t)
                    if 0 <= t <= 2:
                        s.set('models.ollama.temperature', t)
                        s.set('models.openrouter.temperature', t)
                        print(f"  {self.GREEN}✅ Temperature: {t}{self.RESET}")
                except:
                    print(f"  {self.RED}Invalid number{self.RESET}")
            elif ch == '7':
                c = input("  Context length (1024-32768): ").strip()
                try:
                    c = int(c)
                    s.set('models.ollama.context_length', c)
                    print(f"  {self.GREEN}✅ Context: {c}{self.RESET}")
                except:
                    print(f"  {self.RED}Invalid number{self.RESET}")
            elif ch == '8':
                b = input("  Daily budget USD (e.g. 1.0): ").strip()
                try:
                    b = float(b)
                    s.set('models.openrouter.budget_limit_daily', b)
                    print(f"  {self.GREEN}✅ Budget: ${b}/day{self.RESET}")
                except:
                    print(f"  {self.RED}Invalid number{self.RESET}")
            elif ch == '9':
                m = input("  Model to pull (e.g. mistral, llama3): ").strip()
                if m:
                    print(f"  Pulling {m}... (this may take a while)")
                    os.system(f"ollama pull {m}")
                    print(f"  {self.GREEN}✅ Done{self.RESET}")

            if ch != '0':
                input(f"\n  {self.DIM}Press Enter...{self.RESET}")

    # ─── RAG Settings ────────────────────────────────────

    def rag_settings(self):
        while True:
            self.clear()
            s = self.settings
            print(f"""{self.CYAN}{self.BOLD}
╔══════════════════════════════════════════════════════════════╗
║                  📚 RAG & FAISS SETTINGS                    ║
╚══════════════════════════════════════════════════════════════╝{self.RESET}

  RAG Enabled:     {self._bool_icon(s.get('rag.enabled'))}
  Engine:          {s.get('rag.engine')}

{self.BOLD}── FAISS ──────────────────────────────────────────────────{self.RESET}
  Index Path:      {s.get('rag.faiss.index_path')}
  Dimension:       {s.get('rag.faiss.dimension')}
  Metric:          {s.get('rag.faiss.metric')}

{self.BOLD}── Chunking ───────────────────────────────────────────────{self.RESET}
  Method:          {s.get('rag.chunking.method')}
  Chunk Size:      {s.get('rag.chunking.chunk_size')}
  Overlap:         {s.get('rag.chunking.chunk_overlap')}
  Min Size:        {s.get('rag.chunking.min_chunk_size')}

{self.BOLD}── Retrieval ──────────────────────────────────────────────{self.RESET}
  Top K:           {s.get('rag.retrieval.top_k')}
  Score Threshold: {s.get('rag.retrieval.score_threshold')}
  Reranking:       {self._bool_icon(s.get('rag.retrieval.reranking'))}

{self.BOLD}  [1]{self.RESET} Toggle RAG On/Off
{self.BOLD}  [2]{self.RESET} Set Chunk Size
{self.BOLD}  [3]{self.RESET} Set Chunk Overlap
{self.BOLD}  [4]{self.RESET} Set Top K
{self.BOLD}  [5]{self.RESET} Set Score Threshold
{self.BOLD}  [6]{self.RESET} Set Dimension
{self.BOLD}  [7]{self.RESET} Toggle Reranking
{self.BOLD}  [0]{self.RESET} ← Back
""")
            ch = input(f"  {self.CYAN}Select:{self.RESET} ").strip()

            if ch == '0':
                break
            elif ch == '1':
                current = s.get('rag.enabled')
                s.set('rag.enabled', not current)
                print(f"  {self.GREEN}✅ RAG: {'Enabled' if not current else 'Disabled'}{self.RESET}")
            elif ch == '2':
                v = input("  Chunk size (100-2000): ").strip()
                try:
                    s.set('rag.chunking.chunk_size', int(v))
                    print(f"  {self.GREEN}✅ Chunk size: {v}{self.RESET}")
                except:
                    pass
            elif ch == '3':
                v = input("  Overlap (0-500): ").strip()
                try:
                    s.set('rag.chunking.chunk_overlap', int(v))
                    print(f"  {self.GREEN}✅ Overlap: {v}{self.RESET}")
                except:
                    pass
            elif ch == '4':
                v = input("  Top K (1-20): ").strip()
                try:
                    s.set('rag.retrieval.top_k', int(v))
                    print(f"  {self.GREEN}✅ Top K: {v}{self.RESET}")
                except:
                    pass
            elif ch == '5':
                v = input("  Score threshold (0.0-1.0): ").strip()
                try:
                    s.set('rag.retrieval.score_threshold', float(v))
                    print(f"  {self.GREEN}✅ Threshold: {v}{self.RESET}")
                except:
                    pass
            elif ch == '6':
                v = input("  Dimension (384/768/1024): ").strip()
                try:
                    s.set('rag.faiss.dimension', int(v))
                    print(f"  {self.GREEN}✅ Dimension: {v}{self.RESET}")
                except:
                    pass
            elif ch == '7':
                current = s.get('rag.retrieval.reranking')
                s.set('rag.retrieval.reranking', not current)
                print(f"  {self.GREEN}✅ Reranking: {'On' if not current else 'Off'}{self.RESET}")

            if ch != '0':
                input(f"\n  {self.DIM}Press Enter...{self.RESET}")

    # ─── Crawler Settings ────────────────────────────────

    def crawler_settings(self):
        while True:
            self.clear()
            s = self.settings

            # Load sites from crawl_sites.json
            sites = []
            if CRAWL_FILE.exists():
                with open(CRAWL_FILE) as f:
                    sites = json.load(f).get('sites', [])

            print(f"""{self.CYAN}{self.BOLD}
╔══════════════════════════════════════════════════════════════╗
║                  🕷️  CRAWLER SETTINGS                        ║
╚══════════════════════════════════════════════════════════════╝{self.RESET}

  Enabled:          {self._bool_icon(s.get('crawler.enabled'))}
  Schedule:         {s.get('crawler.schedule')} @ {s.get('crawler.schedule_time')}
  Max Pages/Site:   {s.get('crawler.max_pages_per_site')}
  Max Depth:        {s.get('crawler.max_depth')}
  Timeout:          {s.get('crawler.timeout')}s
  Delay:            {s.get('crawler.delay_between_requests')}s
  Robots.txt:       {self._bool_icon(s.get('crawler.respect_robots_txt'))}

{self.BOLD}── Sites ({len(sites)}) ────────────────────────────────────────────{self.RESET}""")

            for i, site in enumerate(sites[:10], 1):
                name = site.get('name', 'Unknown')
                url = site.get('url', '')
                enabled = site.get('enabled', True)
                icon = '🟢' if enabled else '🔴'
                print(f"  {icon} {i}. {name}: {url}")

            if len(sites) > 10:
                print(f"  ... and {len(sites)-10} more")

            print(f"""
{self.BOLD}  [1]{self.RESET} Add Site
{self.BOLD}  [2]{self.RESET} Remove Site
{self.BOLD}  [3]{self.RESET} Set Schedule
{self.BOLD}  [4]{self.RESET} Set Max Pages
{self.BOLD}  [5]{self.RESET} Set Max Depth
{self.BOLD}  [6]{self.RESET} Run Crawler Now
{self.BOLD}  [0]{self.RESET} ← Back
""")
            ch = input(f"  {self.CYAN}Select:{self.RESET} ").strip()

            if ch == '0':
                break
            elif ch == '1':
                name = input("  Site name: ").strip()
                url = input("  URL: ").strip()
                if name and url:
                    sites.append({"name": name, "url": url, "enabled": True})
                    self._save_crawl_sites(sites)
                    print(f"  {self.GREEN}✅ Added: {name}{self.RESET}")
            elif ch == '2':
                idx = input("  Remove site number: ").strip()
                try:
                    idx = int(idx) - 1
                    if 0 <= idx < len(sites):
                        removed = sites.pop(idx)
                        self._save_crawl_sites(sites)
                        print(f"  {self.GREEN}✅ Removed: {removed['name']}{self.RESET}")
                except:
                    pass
            elif ch == '3':
                sch = input("  Schedule (manual/hourly/daily/weekly): ").strip()
                if sch in ['manual', 'hourly', 'daily', 'weekly']:
                    s.set('crawler.schedule', sch)
                    if sch != 'manual':
                        t = input("  Time (HH:MM): ").strip()
                        if t:
                            s.set('crawler.schedule_time', t)
                    print(f"  {self.GREEN}✅ Schedule: {sch}{self.RESET}")
            elif ch == '4':
                v = input("  Max pages per site: ").strip()
                try:
                    s.set('crawler.max_pages_per_site', int(v))
                    print(f"  {self.GREEN}✅ Max pages: {v}{self.RESET}")
                except:
                    pass
            elif ch == '5':
                v = input("  Max depth: ").strip()
                try:
                    s.set('crawler.max_depth', int(v))
                    print(f"  {self.GREEN}✅ Max depth: {v}{self.RESET}")
                except:
                    pass
            elif ch == '6':
                print("  🕷️ Starting crawler...")
                os.system("cd /root/ai-brain && python3 crawl4ai_scraper.py 2>&1 | tail -20")

            if ch != '0':
                input(f"\n  {self.DIM}Press Enter...{self.RESET}")

    def _save_crawl_sites(self, sites):
        with open(CRAWL_FILE, 'w') as f:
            json.dump({"sites": sites}, f, indent=2)

    # ─── API Settings ────────────────────────────────────

    def api_settings(self):
        while True:
            self.clear()
            s = self.settings
            print(f"""{self.CYAN}{self.BOLD}
╔══════════════════════════════════════════════════════════════╗
║                   🌐 API SETTINGS                           ║
╚══════════════════════════════════════════════════════════════╝{self.RESET}

  Enabled:      {self._bool_icon(s.get('api.enabled'))}
  Host:         {s.get('api.host')}
  Port:         {s.get('api.port')}
  CORS:         {s.get('api.cors_origins')}
  Rate Limit:   {s.get('api.rate_limit')} req/min
  Auth:         {self._bool_icon(s.get('api.auth_enabled'))}
  API Key:      {self._mask_key(s.get('api.api_key', ''))}
  SSL:          {self._bool_icon(s.get('api.ssl_enabled'))}

{self.BOLD}  [1]{self.RESET} Set Port
{self.BOLD}  [2]{self.RESET} Toggle Auth
{self.BOLD}  [3]{self.RESET} Generate New API Key
{self.BOLD}  [4]{self.RESET} Set Rate Limit
{self.BOLD}  [5]{self.RESET} Toggle SSL
{self.BOLD}  [0]{self.RESET} ← Back
""")
            ch = input(f"  {self.CYAN}Select:{self.RESET} ").strip()

            if ch == '0':
                break
            elif ch == '1':
                v = input("  Port (1024-65535): ").strip()
                try:
                    s.set('api.port', int(v))
                    print(f"  {self.GREEN}✅ Port: {v}{self.RESET}")
                except:
                    pass
            elif ch == '2':
                current = s.get('api.auth_enabled')
                s.set('api.auth_enabled', not current)
                print(f"  {self.GREEN}✅ Auth: {'Enabled' if not current else 'Disabled'}{self.RESET}")
            elif ch == '3':
                import secrets
                key = secrets.token_urlsafe(32)
                s.set('api.api_key', key)
                print(f"  {self.GREEN}✅ New API Key: {key}{self.RESET}")
            elif ch == '4':
                v = input("  Rate limit (req/min): ").strip()
                try:
                    s.set('api.rate_limit', int(v))
                    print(f"  {self.GREEN}✅ Rate limit: {v}/min{self.RESET}")
                except:
                    pass
            elif ch == '5':
                current = s.get('api.ssl_enabled')
                s.set('api.ssl_enabled', not current)
                print(f"  {self.GREEN}✅ SSL: {'Enabled' if not current else 'Disabled'}{self.RESET}")

            if ch != '0':
                input(f"\n  {self.DIM}Press Enter...{self.RESET}")

    # ─── Telegram Settings ───────────────────────────────

    def telegram_settings(self):
        while True:
            self.clear()
            s = self.settings
            print(f"""{self.CYAN}{self.BOLD}
╔══════════════════════════════════════════════════════════════╗
║                  📱 TELEGRAM BOT SETTINGS                   ║
╚══════════════════════════════════════════════════════════════╝{self.RESET}

  Enabled:      {self._bool_icon(s.get('telegram.enabled'))}
  Bot Token:    {self._mask_key(s.get('telegram.bot_token', ''))}
  Allowed:      {s.get('telegram.allowed_users', [])}
  Admins:       {s.get('telegram.admin_users', [])}
  Webhook:      {s.get('telegram.webhook_url') or 'Not set'}

{self.BOLD}  [1]{self.RESET} Toggle Enabled
{self.BOLD}  [2]{self.RESET} Set Bot Token
{self.BOLD}  [3]{self.RESET} Add Allowed User
{self.BOLD}  [4]{self.RESET} Set Webhook URL
{self.BOLD}  [0]{self.RESET} ← Back
""")
            ch = input(f"  {self.CYAN}Select:{self.RESET} ").strip()

            if ch == '0':
                break
            elif ch == '1':
                current = s.get('telegram.enabled')
                s.set('telegram.enabled', not current)
                print(f"  {self.GREEN}✅ Telegram: {'Enabled' if not current else 'Disabled'}{self.RESET}")
            elif ch == '2':
                token = input("  Bot token: ").strip()
                if token:
                    s.set('telegram.bot_token', token)
                    print(f"  {self.GREEN}✅ Token saved{self.RESET}")
            elif ch == '3':
                uid = input("  User ID: ").strip()
                if uid:
                    users = s.get('telegram.allowed_users', [])
                    users.append(uid)
                    s.set('telegram.allowed_users', users)
                    print(f"  {self.GREEN}✅ Added: {uid}{self.RESET}")
            elif ch == '4':
                url = input("  Webhook URL: ").strip()
                if url:
                    s.set('telegram.webhook_url', url)
                    print(f"  {self.GREEN}✅ Webhook: {url}{self.RESET}")

            if ch != '0':
                input(f"\n  {self.DIM}Press Enter...{self.RESET}")

    # ─── Dashboard Settings ──────────────────────────────

    def dashboard_settings(self):
        while True:
            self.clear()
            s = self.settings
            print(f"""{self.CYAN}{self.BOLD}
╔══════════════════════════════════════════════════════════════╗
║                  🎨 DASHBOARD SETTINGS                      ║
╚══════════════════════════════════════════════════════════════╝{self.RESET}

  Enabled:       {self._bool_icon(s.get('dashboard.enabled'))}
  Port:          {s.get('dashboard.port')}
  Theme:         {s.get('dashboard.theme')}
  Refresh:       {s.get('dashboard.refresh_interval')}s
  System Stats:  {self._bool_icon(s.get('dashboard.show_system_stats'))}

{self.BOLD}  [1]{self.RESET} Set Port
{self.BOLD}  [2]{self.RESET} Toggle Theme (dark/light)
{self.BOLD}  [3]{self.RESET} Set Refresh Interval
{self.BOLD}  [0]{self.RESET} ← Back
""")
            ch = input(f"  {self.CYAN}Select:{self.RESET} ").strip()

            if ch == '0':
                break
            elif ch == '1':
                v = input("  Port: ").strip()
                try:
                    s.set('dashboard.port', int(v))
                    print(f"  {self.GREEN}✅ Port: {v}{self.RESET}")
                except:
                    pass
            elif ch == '2':
                current = s.get('dashboard.theme')
                new_theme = 'light' if current == 'dark' else 'dark'
                s.set('dashboard.theme', new_theme)
                print(f"  {self.GREEN}✅ Theme: {new_theme}{self.RESET}")
            elif ch == '3':
                v = input("  Refresh interval (seconds): ").strip()
                try:
                    s.set('dashboard.refresh_interval', int(v))
                    print(f"  {self.GREEN}✅ Refresh: {v}s{self.RESET}")
                except:
                    pass

            if ch != '0':
                input(f"\n  {self.DIM}Press Enter...{self.RESET}")

    # ─── Performance Settings ────────────────────────────

    def performance_settings(self):
        while True:
            self.clear()
            s = self.settings
            print(f"""{self.CYAN}{self.BOLD}
╔══════════════════════════════════════════════════════════════╗
║                  ⚡ PERFORMANCE SETTINGS                     ║
╚══════════════════════════════════════════════════════════════╝{self.RESET}

  Max Workers:      {s.get('performance.max_workers')}
  Batch Size:       {s.get('performance.batch_size')}
  Cache Enabled:    {self._bool_icon(s.get('performance.cache_enabled'))}
  Cache TTL:        {s.get('performance.cache_ttl')}s
  Max Memory:       {s.get('performance.max_memory_mb')}MB
  GPU Memory:       {s.get('performance.gpu_memory_fraction')*100:.0f}%

{self.BOLD}  [1]{self.RESET} Set Max Workers
{self.BOLD}  [2]{self.RESET} Set Batch Size
{self.BOLD}  [3]{self.RESET} Toggle Cache
{self.BOLD}  [4]{self.RESET} Set Cache TTL
{self.BOLD}  [5]{self.RESET} Set Max Memory
{self.BOLD}  [0]{self.RESET} ← Back
""")
            ch = input(f"  {self.CYAN}Select:{self.RESET} ").strip()

            if ch == '0':
                break
            elif ch == '1':
                v = input("  Max workers (1-16): ").strip()
                try:
                    s.set('performance.max_workers', int(v))
                    print(f"  {self.GREEN}✅ Workers: {v}{self.RESET}")
                except:
                    pass
            elif ch == '2':
                v = input("  Batch size (8-128): ").strip()
                try:
                    s.set('performance.batch_size', int(v))
                    print(f"  {self.GREEN}✅ Batch: {v}{self.RESET}")
                except:
                    pass
            elif ch == '3':
                current = s.get('performance.cache_enabled')
                s.set('performance.cache_enabled', not current)
                print(f"  {self.GREEN}✅ Cache: {'On' if not current else 'Off'}{self.RESET}")
            elif ch == '4':
                v = input("  Cache TTL (seconds): ").strip()
                try:
                    s.set('performance.cache_ttl', int(v))
                    print(f"  {self.GREEN}✅ TTL: {v}s{self.RESET}")
                except:
                    pass
            elif ch == '5':
                v = input("  Max memory (MB): ").strip()
                try:
                    s.set('performance.max_memory_mb', int(v))
                    print(f"  {self.GREEN}✅ Memory: {v}MB{self.RESET}")
                except:
                    pass

            if ch != '0':
                input(f"\n  {self.DIM}Press Enter...{self.RESET}")

    # ─── Security Settings ───────────────────────────────

    def security_settings(self):
        while True:
            self.clear()
            s = self.settings
            print(f"""{self.CYAN}{self.BOLD}
╔══════════════════════════════════════════════════════════════╗
║                  🔒 SECURITY SETTINGS                       ║
╚══════════════════════════════════════════════════════════════╝{self.RESET}

  Encrypt Config:   {self._bool_icon(s.get('security.encrypt_config'))}
  Key Rotation:     Every {s.get('security.api_key_rotation_days')} days
  Max Input:        {s.get('security.max_input_length')} chars
  Rate Limit/IP:    {s.get('security.rate_limit_per_ip')} req/min
  Blocked Words:    {len(s.get('security.blocked_words', []))} words

{self.BOLD}  [1]{self.RESET} Set Max Input Length
{self.BOLD}  [2]{self.RESET} Set Rate Limit per IP
{self.BOLD}  [3]{self.RESET} Add Blocked Word
{self.BOLD}  [4]{self.RESET} Set Key Rotation Days
{self.BOLD}  [0]{self.RESET} ← Back
""")
            ch = input(f"  {self.CYAN}Select:{self.RESET} ").strip()

            if ch == '0':
                break
            elif ch == '1':
                v = input("  Max input length: ").strip()
                try:
                    s.set('security.max_input_length', int(v))
                    print(f"  {self.GREEN}✅ Max input: {v}{self.RESET}")
                except:
                    pass
            elif ch == '2':
                v = input("  Rate limit per IP: ").strip()
                try:
                    s.set('security.rate_limit_per_ip', int(v))
                    print(f"  {self.GREEN}✅ Rate: {v}/min{self.RESET}")
                except:
                    pass
            elif ch == '3':
                w = input("  Word to block: ").strip()
                if w:
                    words = s.get('security.blocked_words', [])
                    words.append(w)
                    s.set('security.blocked_words', words)
                    print(f"  {self.GREEN}✅ Blocked: {w}{self.RESET}")
            elif ch == '4':
                v = input("  Rotation days: ").strip()
                try:
                    s.set('security.api_key_rotation_days', int(v))
                    print(f"  {self.GREEN}✅ Rotation: {v} days{self.RESET}")
                except:
                    pass

            if ch != '0':
                input(f"\n  {self.DIM}Press Enter...{self.RESET}")

    # ─── Auto Detect ─────────────────────────────────────

    def auto_detect(self):
        self.clear()
        print(f"""{self.CYAN}{self.BOLD}
╔══════════════════════════════════════════════════════════════╗
║              🔍 AUTO-DETECT & OPTIMIZE                      ║
╚══════════════════════════════════════════════════════════════╝{self.RESET}
""")
        print("  Scanning system...")
        info = self.settings.detect_system()

        print(f"""
{self.BOLD}── System Info ─────────────────────────────────────────────{self.RESET}
  Hostname:     {info['hostname']}
  CPU:          {info['cpu_cores']} cores
  RAM:          {info['ram_available_gb']:.1f} / {info['ram_total_gb']} GB ({info['ram_usage_pct']}% used)
  Disk:         {info['disk_free_gb']:.0f} GB free / {info['disk_total_gb']:.0f} GB
  GPU:          {info['gpu']['name']} ({info['gpu'].get('memory_total_mb',0)}MB)
  Python:       {info['python_version']}
  Ollama:       {'🟢 Running' if info['ollama_running'] else '🔴 Stopped'}
  Models:       {', '.join(info['ollama_models']) or 'None'}
  FAISS Index:  {'✅ Exists' if info['faiss_index_exists'] else '❌ Not built'}
""")

        confirm = input(f"  {self.YELLOW}Optimize settings based on this? (y/n):{self.RESET} ").strip().lower()
        if confirm == 'y':
            changes = self.settings.detect_and_optimize()
            print(f"\n  {self.GREEN}✅ Optimized!{self.RESET}")
            for c in changes:
                print(f"  {c}")

        input(f"\n  {self.DIM}Press Enter...{self.RESET}")

    # ─── Validate ────────────────────────────────────────

    def validate(self):
        self.clear()
        print(f"""{self.CYAN}{self.BOLD}
╔══════════════════════════════════════════════════════════════╗
║              ✅ VALIDATE CONFIGURATION                      ║
╚══════════════════════════════════════════════════════════════╝{self.RESET}
""")
        print("  Checking configuration...\n")
        result = self.settings.validate()

        if result['issues']:
            print(f"  {self.RED}{self.BOLD}Issues:{self.RESET}")
            for issue in result['issues']:
                print(f"    {issue}")

        if result['warnings']:
            print(f"\n  {self.YELLOW}{self.BOLD}Warnings:{self.RESET}")
            for warn in result['warnings']:
                print(f"    {warn}")

        if result['valid']:
            print(f"\n  {self.GREEN}{self.BOLD}✅ Configuration is VALID!{self.RESET}")
        else:
            print(f"\n  {self.RED}{self.BOLD}❌ Configuration has issues!{self.RESET}")

        input(f"\n  {self.DIM}Press Enter...{self.RESET}")

    # ─── Backup / Restore ────────────────────────────────

    def backup_restore(self):
        while True:
            self.clear()
            backups = self.settings.list_backups()
            print(f"""{self.CYAN}{self.BOLD}
╔══════════════════════════════════════════════════════════════╗
║              💾 BACKUP / RESTORE                            ║
╚══════════════════════════════════════════════════════════════╝{self.RESET}

{self.BOLD}── Available Backups ({len(backups)}) ─────────────────────────────{self.RESET}""")

            for i, b in enumerate(backups[:10], 1):
                size = b.stat().st_size / 1024
                print(f"  {i}. {b.name} ({size:.1f}KB)")

            if not backups:
                print("  No backups yet.")

            print(f"""
{self.BOLD}  [1]{self.RESET} Create Backup Now
{self.BOLD}  [2]{self.RESET} Restore from Latest
{self.BOLD}  [3]{self.RESET} Restore from Specific
{self.BOLD}  [0]{self.RESET} ← Back
""")
            ch = input(f"  {self.CYAN}Select:{self.RESET} ").strip()

            if ch == '0':
                break
            elif ch == '1':
                f = self.settings.backup()
                print(f"  {self.GREEN}✅ Backup saved: {f.name}{self.RESET}")
            elif ch == '2':
                f = self.settings.restore()
                if f:
                    print(f"  {self.GREEN}✅ Restored from: {f.name}{self.RESET}")
                else:
                    print(f"  {self.RED}No backups available{self.RESET}")
            elif ch == '3':
                idx = input("  Backup number: ").strip()
                try:
                    idx = int(idx) - 1
                    if 0 <= idx < len(backups):
                        self.settings.restore(backups[idx])
                        print(f"  {self.GREEN}✅ Restored: {backups[idx].name}{self.RESET}")
                except:
                    pass

            if ch != '0':
                input(f"\n  {self.DIM}Press Enter...{self.RESET}")

    # ─── Export ──────────────────────────────────────────

    def export_config(self):
        f = self.settings.export_json()
        print(f"  {self.GREEN}✅ Exported to: {f}{self.RESET}")
        print(f"  {self.DIM}(API keys masked for safety){self.RESET}")
        input(f"\n  {self.DIM}Press Enter...{self.RESET}")

    # ─── Reset ───────────────────────────────────────────

    def reset_config(self):
        self.clear()
        print(f"""{self.CYAN}{self.BOLD}
╔══════════════════════════════════════════════════════════════╗
║              🔄 RESET CONFIGURATION                         ║
╚══════════════════════════════════════════════════════════════╝{self.RESET}

{self.BOLD}  [1]{self.RESET} Reset Models only
{self.BOLD}  [2]{self.RESET} Reset RAG only
{self.BOLD}  [3]{self.RESET} Reset Crawler only
{self.BOLD}  [4]{self.RESET} Reset Performance only
{self.BOLD}  [5]{self.RESET} 🔴 Reset EVERYTHING
{self.BOLD}  [0]{self.RESET} ← Cancel
""")
        ch = input(f"  {self.CYAN}Select:{self.RESET} ").strip()

        sections = {'1': 'models', '2': 'rag', '3': 'crawler', '4': 'performance'}

        if ch in sections:
            confirm = input(f"  {self.YELLOW}Reset {sections[ch]}? (y/n):{self.RESET} ").strip().lower()
            if confirm == 'y':
                self.settings.reset(sections[ch])
                print(f"  {self.GREEN}✅ {sections[ch]} reset to defaults{self.RESET}")
        elif ch == '5':
            confirm = input(f"  {self.RED}⚠️ Reset ALL settings? Type 'RESET':{self.RESET} ").strip()
            if confirm == 'RESET':
                self.settings.reset()
                print(f"  {self.GREEN}✅ All settings reset to defaults{self.RESET}")

        if ch != '0':
            input(f"\n  {self.DIM}Press Enter...{self.RESET}")

    # ─── Helpers ─────────────────────────────────────────

    def _bool_icon(self, val):
        return f"{'🟢 On' if val else '🔴 Off'}"

    def _mask_key(self, key):
        if not key:
            return "❌ Not set"
        return key[:8] + "..." + key[-4:] if len(key) > 12 else "***"


# ═════════════════════════════════════════════════════════
#                      MAIN
# ═════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Ensure dirs exist
    for d in [DATA_DIR, DB_DIR, LOG_DIR, BACKUP_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    if len(sys.argv) > 1:
        s = Settings()
        cmd = sys.argv[1]

        if cmd == "get" and len(sys.argv) > 2:
            print(s.get(sys.argv[2]))
        elif cmd == "set" and len(sys.argv) > 3:
            s.set(sys.argv[2], sys.argv[3])
            print(f"✅ {sys.argv[2]} = {sys.argv[3]}")
        elif cmd == "detect":
            info = s.detect_system()
            print(json.dumps(info, indent=2))
        elif cmd == "optimize":
            changes = s.detect_and_optimize()
            for c in changes:
                print(c)
        elif cmd == "validate":
            result = s.validate()
            print(json.dumps(result, indent=2, default=str))
        elif cmd == "backup":
            f = s.backup()
            print(f"✅ Backup: {f}")
        elif cmd == "export":
            f = s.export_json()
            print(f"✅ Export: {f}")
        elif cmd == "reset":
            s.reset(sys.argv[2] if len(sys.argv) > 2 else None)
            print("✅ Reset done")
        else:
            print("""
Usage:
  python settings.py              # Interactive TUI
  python settings.py get KEY      # Get value
  python settings.py set KEY VAL  # Set value
  python settings.py detect       # System info
  python settings.py optimize     # Auto-optimize
  python settings.py validate     # Check config
  python settings.py backup       # Backup config
  python settings.py export       # Export JSON
  python settings.py reset [section]
""")
    else:
        tui = SettingsTUI()
        tui.run()
