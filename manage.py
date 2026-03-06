#!/usr/bin/env python3
"""
manage.py — AI Brain Management Dashboard
Works with: config.yaml, FAISS, Ollama, OpenRouter, crawl_smart.py
"""

import os
import sys
import json
import glob
import time
import shutil
import subprocess
import re
import requests
from datetime import datetime
from urllib.parse import urljoin, urlparse, parse_qs

# ── Rich UI ──────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm, IntPrompt
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich.markdown import Markdown
    from rich import box
except ImportError:
    os.system("pip install rich")
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm, IntPrompt
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich.markdown import Markdown
    from rich import box

try:
    import yaml
except ImportError:
    os.system("pip install pyyaml")
    import yaml

try:
    from bs4 import BeautifulSoup
except ImportError:
    os.system("pip install beautifulsoup4")
    from bs4 import BeautifulSoup

# ── Globals ──────────────────────────────────────────────
console = Console()
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_DIR, "data")
CONFIG_FILE = os.path.join(PROJECT_DIR, "config.yaml")
CRAWL_CONFIG = os.path.join(PROJECT_DIR, "crawl_sites.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


# ══════════════════════════════════════════════════════════
#  CONFIG HELPERS
# ══════════════════════════════════════════════════════════

def load_yaml_config() -> dict:
    """Load config.yaml."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def save_yaml_config(config: dict):
    """Save config.yaml."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def load_crawl_sites() -> list:
    """Load crawl sites list."""
    if os.path.exists(CRAWL_CONFIG):
        with open(CRAWL_CONFIG, "r") as f:
            return json.load(f)

    # Default BWK sites
    defaults = [
        {"name": "BWK Nanny", "url": "https://membersbwk.baliwithkidz.com/nanny.php", "prefix": "bwk_nanny", "category": "nanny", "enabled": True},
        {"name": "BWK Driver", "url": "https://membersbwk.baliwithkidz.com/car.php", "prefix": "bwk_driver", "category": "driver", "enabled": True},
        {"name": "BWK Villa", "url": "https://membersbwk.baliwithkidz.com/villa.php", "prefix": "bwk_villa", "category": "villa", "enabled": True},
        {"name": "BWK Activities", "url": "https://membersbwk.baliwithkidz.com/activities.php", "prefix": "bwk_activity", "category": "activities", "enabled": True},
        {"name": "BWK Medical", "url": "https://membersbwk.baliwithkidz.com/medical.php", "prefix": "bwk_medical", "category": "medical", "enabled": True},
        {"name": "BWK School", "url": "https://membersbwk.baliwithkidz.com/school.php", "prefix": "bwk_school", "category": "school", "enabled": True},
        {"name": "BWK Restaurant", "url": "https://membersbwk.baliwithkidz.com/restaurant.php", "prefix": "bwk_restaurant", "category": "restaurant", "enabled": True},
        {"name": "BWK Playground", "url": "https://membersbwk.baliwithkidz.com/playground.php", "prefix": "bwk_playground", "category": "playground", "enabled": True},
        {"name": "BWK Shop", "url": "https://membersbwk.baliwithkidz.com/shop.php", "prefix": "bwk_shop", "category": "shop", "enabled": True},
    ]
    save_crawl_sites(defaults)
    return defaults


def save_crawl_sites(sites: list):
    with open(CRAWL_CONFIG, "w") as f:
        json.dump(sites, f, indent=2)


# ══════════════════════════════════════════════════════════
#  UI COMPONENTS
# ══════════════════════════════════════════════════════════

def clear():
    os.system("clear" if os.name != "nt" else "cls")


def show_header():
    clear()
    header = """
 █████╗ ██╗    ██████╗ ██████╗  █████╗ ██╗███╗   ██╗
██╔══██╗██║    ██╔══██╗██╔══██╗██╔══██╗██║████╗  ██║
███████║██║    ██████╔╝██████╔╝███████║██║██╔██╗ ██║
██╔══██║██║    ██╔══██╗██╔══██╗██╔══██║██║██║╚██╗██║
██║  ██║██║    ██████╔╝██║  ██║██║  ██║██║██║ ╚████║
╚═╝  ╚═╝╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝"""
    console.print(header, style="bold cyan")
    console.print("  BaliWithKidz Management Dashboard v2.0", style="bold yellow")
    console.print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", style="dim")
    console.print("─" * 58, style="dim")


def show_status():
    """Show system status panel."""
    config = load_yaml_config()

    # API check
    api_ok = False
    api_port = config.get("server_port", 5000)
    try:
        r = requests.get(f"http://localhost:{api_port}/health", timeout=3)
        api_ok = r.status_code == 200
    except:
        pass

    # Redis check
    redis_ok = False
    try:
        r = subprocess.run(["redis-cli", "ping"], capture_output=True, text=True, timeout=3)
        redis_ok = "PONG" in r.stdout
    except:
        pass

    # Celery check
    celery_ok = False
    try:
        r = subprocess.run(["pgrep", "-f", "celery.*worker"], capture_output=True, timeout=3)
        celery_ok = r.returncode == 0
    except:
        pass

    # Data files
    txt_count = len(glob.glob(os.path.join(DATA_DIR, "*.txt")))

    # FAISS vectors
    vs_path = os.path.join(PROJECT_DIR, config.get("vector_store_path", "db/faiss_index"))
    faiss_count = "N/A"
    if os.path.exists(vs_path):
        try:
            import faiss as faiss_lib
            idx_file = os.path.join(vs_path, "index.faiss")
            if os.path.exists(idx_file):
                index = faiss_lib.read_index(idx_file)
                faiss_count = index.ntotal
        except:
            faiss_count = "✅ exists"

    # LLM info
    llm_info = f"{config.get('llm_provider', '?')} / {config.get('llm_model', '?')}"
    emb_info = f"{config.get('embedding_provider', '?')} / {config.get('embedding_model', '?')}"

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column(style="bold", width=14)
    table.add_column(width=16)
    table.add_column(style="bold", width=14)
    table.add_column(width=16)

    table.add_row(
        "API:", f"{'🟢 UP' if api_ok else '🔴 DOWN'} (:{api_port})",
        "Data Files:", f"📄 {txt_count}",
    )
    table.add_row(
        "Redis:", "🟢 UP" if redis_ok else "🔴 DOWN",
        "FAISS Vectors:", f"🧮 {faiss_count}",
    )
    table.add_row(
        "Celery:", "🟢 UP" if celery_ok else "🔴 DOWN",
        "LLM:", f"🤖 {config.get('llm_provider', '?')}",
    )

    console.print(Panel(table, title="[bold]System Status[/bold]", border_style="blue"))


def pause():
    Prompt.ask("\n[dim]Press Enter to continue[/dim]")


# ══════════════════════════════════════════════════════════
#  CRAWLER
# ══════════════════════════════════════════════════════════

def crawl_url(url: str, prefix: str, category: str, delay: int = 2) -> int:
    """Crawl a URL and sub-pages, save as .txt files."""
    console.print(f"\n🕷️  Crawling: [bold]{url}[/bold]")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        console.print(f"  [red]✗ Error: {e}[/red]")
        return 0

    soup = BeautifulSoup(resp.text, "html.parser")

    # Find sub-page links (e.g., nanny.php?view=farida)
    base_page = url.split("/")[-1].split("?")[0]
    vendor_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if base_page in href and "view=" in href:
            full = urljoin(url, href)
            if full not in vendor_links:
                vendor_links.append(full)

    os.makedirs(DATA_DIR, exist_ok=True)
    count = 0

    if not vendor_links:
        # Save listing page itself
        content = extract_content(soup, url, category)
        if content:
            fp = os.path.join(DATA_DIR, f"{prefix}_listing.txt")
            with open(fp, "w", encoding="utf-8") as f:
                f.write(content)
            console.print(f"  [green]✓ Saved: {prefix}_listing.txt[/green]")
            return 1
        return 0

    console.print(f"  Found [bold]{len(vendor_links)}[/bold] sub-pages\n")

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), TextColumn("{task.completed}/{task.total}"),
        console=console,
    ) as progress:
        task = progress.add_task("Crawling...", total=len(vendor_links))

        for vurl in vendor_links:
            parsed = urlparse(vurl)
            params = parse_qs(parsed.query)
            view = params.get("view", ["unknown"])[0]
            fname = f"{prefix}_{view}.txt"

            progress.update(task, description=f"{view}")

            try:
                vresp = requests.get(vurl, headers=HEADERS, timeout=30)
                vsoup = BeautifulSoup(vresp.text, "html.parser")
                content = extract_content(vsoup, vurl, category)

                if content and len(content) > 50:
                    with open(os.path.join(DATA_DIR, fname), "w", encoding="utf-8") as f:
                        f.write(content)
                    count += 1
            except Exception:
                pass

            progress.advance(task)
            time.sleep(delay)

    console.print(f"\n  [green]✅ Saved {count} files[/green]")
    return count


def extract_content(soup: BeautifulSoup, url: str, category: str) -> str:
    """Extract structured content from a page."""
    for tag in soup.find_all(["script", "style", "nav", "footer", "noscript", "iframe"]):
        tag.decompose()

    # Name
    name = ""
    for t in ["h1", "h2", "h3"]:
        el = soup.find(t)
        if el:
            name = el.get_text(strip=True)
            break
    if not name:
        title = soup.find("title")
        name = title.get_text(strip=True) if title else "Unknown"

    # Meta description
    desc = ""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta:
        desc = meta.get("content", "")

    # Contacts
    whatsapp = phone = messenger = ""
    for a in soup.find_all("a", href=True):
        h = a["href"]
        if "wa.me" in h:
            whatsapp = h
        elif "m.me" in h:
            messenger = h
        elif "tel:" in h:
            phone = h.replace("tel:", "")

    # Body text
    main = soup.find("main") or soup.find("article") or soup.find("div", class_=re.compile(r"content|main|detail|container"))
    body = main.get_text(separator="\n") if main else (soup.find("body").get_text(separator="\n") if soup.find("body") else "")
    body = re.sub(r'\n{3,}', '\n\n', body).strip()
    body = re.sub(r' {2,}', ' ', body)

    lines = [f"=== {name} ===", f"Category: {category}", f"Detail Page: {url}"]
    if desc:
        lines.append(f"Description: {desc}")
    if whatsapp:
        lines.append(f"WhatsApp: {whatsapp}")
    if phone:
        lines.append(f"Phone: {phone}")
    if messenger:
        lines.append(f"Messenger: {messenger}")
    if body:
        lines.append(f"\nContent:\n{body[:3000]}")

    return "\n".join(lines)


def menu_crawler():
    """Crawler management."""
    while True:
        clear()
        console.print("\n🕷️  [bold cyan]CRAWLER MANAGEMENT[/bold cyan]\n")

        sites = load_crawl_sites()
        table = Table(box=box.ROUNDED, title=f"Crawl Sites ({len(sites)})")
        table.add_column("#", width=4, style="bold")
        table.add_column("Name", style="cyan")
        table.add_column("URL", style="blue", max_width=45)
        table.add_column("Prefix", style="yellow")
        table.add_column("On?", width=5)

        for i, s in enumerate(sites, 1):
            status = "[green]✅[/green]" if s.get("enabled", True) else "[red]❌[/red]"
            table.add_row(str(i), s["name"], s["url"], s["prefix"], status)

        console.print(table)

        console.print("\n[bold]Actions:[/bold]")
        console.print("  [1] 🕷️  Crawl ALL enabled sites")
        console.print("  [2] 🎯 Crawl single site (pick #)")
        console.print("  [3] ➕ Add new site")
        console.print("  [4] ✏️  Edit site")
        console.print("  [5] 🗑️  Remove site")
        console.print("  [6] 🔄 Toggle ON/OFF")
        console.print("  [7] 🌐 Quick crawl (paste URL)")
        console.print("  [8] 🚀 Use crawl_smart.py (existing)")
        console.print("  [0] ← Back")

        ch = Prompt.ask("\n[bold]Choose[/bold]", choices=[str(i) for i in range(9)], default="0")

        if ch == "0":
            break

        elif ch == "1":
            console.print("\n[bold yellow]🕷️  Crawling all enabled sites...[/bold yellow]\n")
            config = load_yaml_config()
            total = 0
            for s in sites:
                if s.get("enabled", True):
                    total += crawl_url(s["url"], s["prefix"], s["category"], config.get("crawl_delay", 2))
            console.print(f"\n[bold green]🎉 Total: {total} files saved[/bold green]")
            if Confirm.ask("\n📦 Re-ingest into FAISS now?"):
                run_ingest()
            pause()

        elif ch == "2":
            idx = IntPrompt.ask("Site #", default=1)
            if 1 <= idx <= len(sites):
                s = sites[idx - 1]
                crawl_url(s["url"], s["prefix"], s["category"])
                if Confirm.ask("\n📦 Re-ingest?"):
                    run_ingest()
            pause()

        elif ch == "3":
            console.print("\n[bold]➕ Add New Crawl Site[/bold]\n")
            name = Prompt.ask("  Name")
            url = Prompt.ask("  URL")
            prefix = Prompt.ask("  Prefix", default=url.split("/")[-1].split(".")[0])
            cat = Prompt.ask("  Category", default=prefix)
            sites.append({"name": name, "url": url, "prefix": prefix, "category": cat, "enabled": True})
            save_crawl_sites(sites)
            console.print(f"[green]✅ Added: {name}[/green]")
            if Confirm.ask("Crawl now?"):
                crawl_url(url, prefix, cat)
            pause()

        elif ch == "4":
            idx = IntPrompt.ask("Site # to edit", default=1)
            if 1 <= idx <= len(sites):
                s = sites[idx - 1]
                s["name"] = Prompt.ask("  Name", default=s["name"])
                s["url"] = Prompt.ask("  URL", default=s["url"])
                s["prefix"] = Prompt.ask("  Prefix", default=s["prefix"])
                s["category"] = Prompt.ask("  Category", default=s.get("category", ""))
                save_crawl_sites(sites)
                console.print("[green]✅ Updated![/green]")
            pause()

        elif ch == "5":
            idx = IntPrompt.ask("Site # to remove", default=1)
            if 1 <= idx <= len(sites):
                if Confirm.ask(f"Remove [red]{sites[idx-1]['name']}[/red]?"):
                    sites.pop(idx - 1)
                    save_crawl_sites(sites)
                    console.print("[green]✅ Removed[/green]")
            pause()

        elif ch == "6":
            idx = IntPrompt.ask("Site # to toggle", default=1)
            if 1 <= idx <= len(sites):
                sites[idx-1]["enabled"] = not sites[idx-1].get("enabled", True)
                save_crawl_sites(sites)
                st = "ON" if sites[idx-1]["enabled"] else "OFF"
                console.print(f"[green]✅ {sites[idx-1]['name']} → {st}[/green]")
            pause()

        elif ch == "7":
            console.print("\n[bold]🌐 Quick Crawl[/bold]\n")
            url = Prompt.ask("  URL")
            prefix = Prompt.ask("  Prefix", default="quick")
            cat = Prompt.ask("  Category", default="general")
            crawl_url(url, prefix, cat)
            if Confirm.ask("\nSave to crawler list?"):
                name = Prompt.ask("  Name", default=url[:40])
                sites.append({"name": name, "url": url, "prefix": prefix, "category": cat, "enabled": True})
                save_crawl_sites(sites)
            if Confirm.ask("Re-ingest?"):
                run_ingest()
            pause()

        elif ch == "8":
            smart_path = os.path.join(PROJECT_DIR, "crawl_smart.py")
            if os.path.exists(smart_path):
                console.print("\n[bold]🚀 Running crawl_smart.py...[/bold]\n")
                os.system(f"cd {PROJECT_DIR} && python3 crawl_smart.py")
                if Confirm.ask("\n📦 Re-ingest?"):
                    run_ingest()
            else:
                console.print("[red]crawl_smart.py not found[/red]")
            pause()


# ══════════════════════════════════════════════════════════
#  INGEST
# ══════════════════════════════════════════════════════════

def run_ingest(mode="REPLACE"):
    """Run ingest_data.py."""
    console.print(f"\n[bold yellow]📦 Ingesting data (mode={mode})...[/bold yellow]\n")
    result = subprocess.run(
        ["python3", "ingest_data.py", mode],
        cwd=PROJECT_DIR,
        capture_output=True, text=True,
    )
    if result.stdout:
        console.print(result.stdout)
    if result.returncode != 0 and result.stderr:
        console.print(f"[red]{result.stderr}[/red]")
    else:
        console.print("[green]✅ Ingestion complete![/green]")


# ══════════════════════════════════════════════════════════
#  PROMPT MANAGEMENT
# ══════════════════════════════════════════════════════════

def get_system_prompt() -> str:
    """Read current system prompt from core_rag.py."""
    rag_file = os.path.join(PROJECT_DIR, "core_rag.py")
    with open(rag_file, "r", encoding="utf-8") as f:
        content = f.read()
    match = re.search(r'SYSTEM_PROMPT\s*=\s*"""\\\n?(.*?)"""', content, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r'SYSTEM_PROMPT\s*=\s*"""(.*?)"""', content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return "(Could not read prompt)"


def save_system_prompt(new_prompt: str):
    """Write system prompt to core_rag.py."""
    rag_file = os.path.join(PROJECT_DIR, "core_rag.py")
    with open(rag_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Replace the SYSTEM_PROMPT string
    pattern = r'(SYSTEM_PROMPT\s*=\s*"""\\\n?).*?(""")'
    replacement = f'SYSTEM_PROMPT = """\\\n{new_prompt}\n"""'
    new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

    if new_content == content:
        # Try without backslash
        pattern2 = r'(SYSTEM_PROMPT\s*=\s*""").*?(""")'
        replacement2 = f'SYSTEM_PROMPT = """\n{new_prompt}\n"""'
        new_content = re.sub(pattern2, replacement2, content, flags=re.DOTALL)

    with open(rag_file, "w", encoding="utf-8") as f:
        f.write(new_content)


def menu_prompt():
    while True:
        clear()
        console.print("\n📝 [bold cyan]PROMPT MANAGEMENT[/bold cyan]\n")

        prompt = get_system_prompt()
        console.print(Panel(prompt, title="[bold]Current System Prompt (core_rag.py)[/bold]",
                           border_style="green", width=80))
        console.print(f"  📏 Length: {len(prompt)} chars\n")

        console.print("[bold]Actions:[/bold]")
        console.print("  [1] ✏️  Edit prompt (opens nano)")
        console.print("  [2] 📋 Load preset prompt")
        console.print("  [3] 💾 Export to file")
        console.print("  [4] 📂 Import from file")
        console.print("  [0] ← Back")

        ch = Prompt.ask("\n[bold]Choose[/bold]", choices=["0","1","2","3","4"], default="0")

        if ch == "0":
            break

        elif ch == "1":
            tmp = "/tmp/ai_brain_prompt.txt"
            with open(tmp, "w") as f:
                f.write(prompt)
            os.system(f"nano {tmp}")
            with open(tmp, "r") as f:
                new = f.read().strip()
            if new and new != prompt:
                save_system_prompt(new)
                console.print("[green]✅ Prompt updated in core_rag.py![/green]")
                console.print("[yellow]⚠️  Restart Celery worker to apply[/yellow]")
            pause()

        elif ch == "2":
            presets = {
                "1": ("Concise + Links", """\
You are the BWK AI assistant. Rules:
1. Answer in the SAME LANGUAGE as the question.
2. Brief 1-2 sentence description per vendor.
3. Always include BWK detail page link.
4. Include WhatsApp if available.
5. Keep SHORT. If no info, direct to https://baliwithkidz.com

Konteks:
{context}

Sumber:
{sources}"""),
                "2": ("Detailed + Friendly", """\
You are a friendly AI assistant for BaliWithKidz — family travel in Bali.

RULES:
1. Answer ONLY from context. Same language as question.
2. For each vendor: name, description, why good for families, contact, BWK link.
3. Be warm and enthusiastic!
4. If unsure, direct to https://baliwithkidz.com

Konteks:
{context}

Sumber:
{sources}"""),
                "3": ("Bahasa Indonesia Only", """\
Kamu asisten AI BaliWithKidz. SELALU jawab Bahasa Indonesia.

Aturan:
1. Jawab HANYA dari konteks.
2. Untuk setiap layanan: nama, deskripsi singkat, kontak, link BWK.
3. Jika tidak ada info: "Silakan kunjungi https://baliwithkidz.com"
4. Sertakan URL detail jika tersedia (format: 🔗 Detail: <url>).

Konteks:
{context}

Sumber:
{sources}"""),
            }
            console.print("\n[bold]Presets:[/bold]")
            for k, (name, _) in presets.items():
                console.print(f"  [{k}] {name}")
            pc = Prompt.ask("Choose", choices=list(presets.keys()) + ["0"], default="0")
            if pc in presets:
                save_system_prompt(presets[pc][1])
                console.print(f"[green]✅ Applied: {presets[pc][0]}[/green]")
            pause()

        elif ch == "3":
            fp = Prompt.ask("Save to", default=os.path.join(PROJECT_DIR, "prompt_backup.txt"))
            with open(fp, "w") as f:
                f.write(prompt)
            console.print(f"[green]✅ Saved to {fp}[/green]")
            pause()

        elif ch == "4":
            fp = Prompt.ask("Load from", default=os.path.join(PROJECT_DIR, "prompt_backup.txt"))
            if os.path.exists(fp):
                with open(fp, "r") as f:
                    new = f.read().strip()
                save_system_prompt(new)
                console.print(f"[green]✅ Imported![/green]")
            else:
                console.print(f"[red]Not found: {fp}[/red]")
            pause()


# ══════════════════════════════════════════════════════════
#  DATABASE MANAGEMENT
# ══════════════════════════════════════════════════════════

def menu_database():
    while True:
        clear()
        console.print("\n📊 [bold cyan]DATABASE MANAGEMENT[/bold cyan]\n")

        txt_files = sorted(glob.glob(os.path.join(DATA_DIR, "*.txt")))

        table = Table(box=box.ROUNDED, title=f"Data Files ({len(txt_files)})")
        table.add_column("#", width=4)
        table.add_column("Filename", style="cyan", max_width=40)
        table.add_column("Size", style="yellow", justify="right", width=10)
        table.add_column("Modified", style="dim", width=18)

        for i, fp in enumerate(txt_files, 1):
            fname = os.path.basename(fp)
            size = os.path.getsize(fp)
            mtime = datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%Y-%m-%d %H:%M")
            sz = f"{size:,} B" if size < 1024 else f"{size/1024:.1f} KB"
            table.add_row(str(i), fname, sz, mtime)

        console.print(table)

        # FAISS info
        config = load_yaml_config()
        vs_path = os.path.join(PROJECT_DIR, config.get("vector_store_path", "db/faiss_index"))
        if os.path.exists(vs_path):
            try:
                total_size = sum(os.path.getsize(os.path.join(dp, f))
                                for dp, _, fn in os.walk(vs_path) for f in fn)
                console.print(f"\n  💾 FAISS store: {vs_path} ({total_size/1024/1024:.1f} MB)")
            except:
                console.print(f"\n  💾 FAISS store: {vs_path}")
        else:
            console.print(f"\n  ⚠️  FAISS index not found at {vs_path}")

        console.print("\n[bold]Actions:[/bold]")
        console.print("  [1] 📦 Re-ingest (REPLACE)")
        console.print("  [2] ➕ Re-ingest (APPEND)")
        console.print("  [3] 👁️  Preview file")
        console.print("  [4] 🗑️  Delete file")
        console.print("  [5] 🗑️  Clear ALL data + FAISS")
        console.print("  [0] ← Back")

        ch = Prompt.ask("\n[bold]Choose[/bold]", choices=["0","1","2","3","4","5"], default="0")

        if ch == "0":
            break
        elif ch == "1":
            run_ingest("REPLACE")
            pause()
        elif ch == "2":
            run_ingest("APPEND")
            pause()
        elif ch == "3":
            idx = IntPrompt.ask("File #", default=1)
            if 1 <= idx <= len(txt_files):
                with open(txt_files[idx-1], "r", encoding="utf-8") as f:
                    content = f.read()[:2000]
                console.print(Panel(content, title=os.path.basename(txt_files[idx-1]),
                                   border_style="green", width=80))
            pause()
        elif ch == "4":
            idx = IntPrompt.ask("File # to delete", default=1)
            if 1 <= idx <= len(txt_files):
                if Confirm.ask(f"Delete [red]{os.path.basename(txt_files[idx-1])}[/red]?"):
                    os.remove(txt_files[idx-1])
                    console.print("[green]✅ Deleted[/green]")
            pause()
        elif ch == "5":
            if Confirm.ask("[red]⚠️  Delete ALL data files AND FAISS index?[/red]"):
                for f in txt_files:
                    os.remove(f)
                if os.path.exists(vs_path):
                    shutil.rmtree(vs_path)
                console.print("[green]✅ All cleared[/green]")
            pause()


# ══════════════════════════════════════════════════════════
#  SETTINGS
# ══════════════════════════════════════════════════════════

def menu_settings():
    while True:
        clear()
        console.print("\n⚙️  [bold cyan]SETTINGS (config.yaml)[/bold cyan]\n")

        config = load_yaml_config()

        table = Table(box=box.ROUNDED, title="Configuration")
        table.add_column("Setting", style="cyan", width=24)
        table.add_column("Value", style="yellow")

        table.add_row("LLM Provider", str(config.get("llm_provider", "")))
        table.add_row("LLM Model", str(config.get("llm_model", "")))
        table.add_row("LLM Base URL", str(config.get("llm_base_url", "")))
        table.add_row("LLM API Key", f"{'✅ Set' if config.get('llm_api_key') else '❌ Missing'}")
        table.add_row("Temperature", str(config.get("llm_temperature", 0.3)))
        table.add_row("Max Tokens", str(config.get("llm_max_tokens", 1024)))
        table.add_row("", "")
        table.add_row("Embedding Provider", str(config.get("embedding_provider", "")))
        table.add_row("Embedding Model", str(config.get("embedding_model", "")))
        table.add_row("Ollama URL", str(config.get("ollama_base_url", "")))
        table.add_row("", "")
        table.add_row("Vector Store", str(config.get("vector_store_path", "")))
        table.add_row("Chunk Size", str(config.get("chunk_size", 1000)))
        table.add_row("Chunk Overlap", str(config.get("chunk_overlap", 200)))
        table.add_row("Retrieval Top K", str(config.get("retrieval_top_k", 5)))
        table.add_row("", "")
        table.add_row("Telegram Token", f"{'✅ Set' if config.get('telegram_bot_token') else '❌'}")
        table.add_row("Server Port", str(config.get("server_port", 5000)))

        console.print(table)

        console.print("\n[bold]Actions:[/bold]")
        console.print("  [1] 🤖 Change LLM (provider/model/key)")
        console.print("  [2] 🧩 Change Embedding settings")
        console.print("  [3] 🌡️  Change Temperature / Tokens")
        console.print("  [4] 🔍 Change Retrieval settings")
        console.print("  [5] 🔑 Change Telegram token")
        console.print("  [6] 📝 Edit config.yaml directly (nano)")
        console.print("  [0] ← Back")

        ch = Prompt.ask("\n[bold]Choose[/bold]", choices=["0","1","2","3","4","5","6"], default="0")

        if ch == "0":
            break

        elif ch == "1":
            console.print("\n[bold]🤖 LLM Configuration[/bold]")
            providers = ["openrouter", "groq", "openai", "ollama"]
            console.print(f"  Providers: {', '.join(providers)}")
            config["llm_provider"] = Prompt.ask("  Provider", default=config.get("llm_provider", "openrouter"))
            config["llm_model"] = Prompt.ask("  Model", default=config.get("llm_model", ""))
            config["llm_base_url"] = Prompt.ask("  Base URL", default=config.get("llm_base_url", ""))
            key = Prompt.ask("  API Key (Enter to keep)", default="")
            if key:
                config["llm_api_key"] = key
            save_yaml_config(config)
            console.print("[green]✅ LLM settings updated![/green]")
            pause()

        elif ch == "2":
            console.print("\n[bold]🧩 Embedding Configuration[/bold]")
            config["embedding_provider"] = Prompt.ask("  Provider (ollama/openai)", default=config.get("embedding_provider", "ollama"))
            config["embedding_model"] = Prompt.ask("  Model", default=config.get("embedding_model", "nomic-embed-text"))
            if config["embedding_provider"] == "ollama":
                config["ollama_base_url"] = Prompt.ask("  Ollama URL", default=config.get("ollama_base_url", "http://localhost:11434"))
            save_yaml_config(config)
            console.print("[green]✅ Updated! Run re-ingest to apply.[/green]")
            pause()

        elif ch == "3":
            config["llm_temperature"] = float(Prompt.ask("  Temperature (0.0-1.0)", default=str(config.get("llm_temperature", 0.3))))
            config["llm_max_tokens"] = int(Prompt.ask("  Max Tokens", default=str(config.get("llm_max_tokens", 1024))))
            save_yaml_config(config)
            console.print("[green]✅ Updated![/green]")
            pause()

        elif ch == "4":
            config["retrieval_top_k"] = int(Prompt.ask("  Retrieval Top K", default=str(config.get("retrieval_top_k", 5))))
            config["rerank_top_k"] = int(Prompt.ask("  Rerank Top K", default=str(config.get("rerank_top_k", 3))))
            config["chunk_size"] = int(Prompt.ask("  Chunk Size", default=str(config.get("chunk_size", 1000))))
            config["chunk_overlap"] = int(Prompt.ask("  Chunk Overlap", default=str(config.get("chunk_overlap", 200))))
            save_yaml_config(config)
            console.print("[green]✅ Updated! Run re-ingest for chunk changes.[/green]")
            pause()

        elif ch == "5":
            token = Prompt.ask("  Telegram Bot Token", default=config.get("telegram_bot_token", ""))
            config["telegram_bot_token"] = token
            save_yaml_config(config)
            console.print("[green]✅ Token updated![/green]")
            pause()

        elif ch == "6":
            os.system(f"nano {CONFIG_FILE}")
            console.print("[green]✅ Restart services to apply changes[/green]")
            pause()


# ══════════════════════════════════════════════════════════
#  TEST QUERY
# ══════════════════════════════════════════════════════════

def menu_test():
    config = load_yaml_config()
    port = config.get("server_port", 5000)

    while True:
        clear()
        console.print("\n🧪 [bold cyan]TEST QUERY[/bold cyan]")
        console.print(f"[dim]API: http://localhost:{port} | Type 'quit' to exit[/dim]\n")

        query = Prompt.ask("🗣️  Question")
        if query.lower() in ["quit", "exit", "q", "0"]:
            break

        console.print("\n⏳ Processing...\n")

        try:
            resp = requests.post(
                f"http://localhost:{port}/api/query",
                json={"query": query},
                timeout=60,
            )
            if resp.status_code == 200:
                data = resp.json()
                answer = data.get("data", {}).get("answer", data.get("answer", "No answer"))
                sources = data.get("data", {}).get("sources", data.get("sources", []))

                console.print(Panel(
                    Markdown(answer),
                    title="[bold green]🤖 AI Response[/bold green]",
                    border_style="green", width=80,
                ))
                if sources:
                    console.print(f"\n📚 Sources: {', '.join(str(s) for s in sources)}")
            else:
                console.print(f"[red]Error {resp.status_code}: {resp.text[:300]}[/red]")

        except requests.exceptions.ConnectionError:
            console.print("[red]❌ API not running! Start services first.[/red]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

        pause()


# ══════════════════════════════════════════════════════════
#  SERVICE MANAGEMENT
# ══════════════════════════════════════════════════════════

def menu_services():
    while True:
        clear()
        console.print("\n🚀 [bold cyan]SERVICE MANAGEMENT[/bold cyan]\n")
        show_status()

        console.print("\n[bold]Actions:[/bold]")
        console.print("  [1] ▶️  Start ALL services")
        console.print("  [2] ⏹️  Stop ALL services")
        console.print("  [3] 🔄 Restart ALL")
        console.print("  [4] 📋 API logs")
        console.print("  [5] 📋 Celery logs")
        console.print("  [6] 🌐 Set Telegram webhook")
        console.print("  [0] ← Back")

        ch = Prompt.ask("\n[bold]Choose[/bold]", choices=["0","1","2","3","4","5","6"], default="0")

        if ch == "0":
            break

        elif ch == "1":
            start_sh = os.path.join(PROJECT_DIR, "start.sh")
            if os.path.exists(start_sh):
                os.system(f"bash {start_sh}")
            else:
                config = load_yaml_config()
                port = config.get("server_port", 5000)
                console.print("Starting Celery worker...")
                os.system(f"cd {PROJECT_DIR} && nohup celery -A tasks worker --loglevel=info --concurrency=2 > /tmp/celery_worker.log 2>&1 &")
                time.sleep(3)
                console.print("Starting API server...")
                os.system(f"cd {PROJECT_DIR} && nohup python3 -m uvicorn api_server:app --host 0.0.0.0 --port {port} > /tmp/api_server.log 2>&1 &")
                time.sleep(3)
                console.print("[green]✅ Services started![/green]")
            pause()

        elif ch == "2":
            os.system("pkill -f 'celery.*worker' 2>/dev/null")
            os.system("pkill -f 'uvicorn.*api_server' 2>/dev/null")
            console.print("[green]✅ Stopped[/green]")
            pause()

        elif ch == "3":
            os.system("pkill -f 'celery.*worker' 2>/dev/null; pkill -f 'uvicorn.*api_server' 2>/dev/null")
            time.sleep(2)
            config = load_yaml_config()
            port = config.get("server_port", 5000)
            os.system(f"cd {PROJECT_DIR} && nohup celery -A tasks worker --loglevel=info --concurrency=2 > /tmp/celery_worker.log 2>&1 &")
            time.sleep(3)
            os.system(f"cd {PROJECT_DIR} && nohup python3 -m uvicorn api_server:app --host 0.0.0.0 --port {port} > /tmp/api_server.log 2>&1 &")
            time.sleep(3)
            console.print("[green]✅ Restarted![/green]")
            pause()

        elif ch == "4":
            os.system("tail -40 /tmp/api_server.log 2>/dev/null || echo 'No log file'")
            pause()

        elif ch == "5":
            os.system("tail -40 /tmp/celery_worker.log 2>/dev/null || echo 'No log file'")
            pause()

        elif ch == "6":
            config = load_yaml_config()
            token = config.get("telegram_bot_token", "")
            if not token:
                console.print("[red]No Telegram token in config.yaml[/red]")
            else:
                server_url = Prompt.ask("Server URL (https://)", default="https://your-domain.com")
                wh_url = f"{server_url}/webhook/telegram"
                r = requests.get(f"https://api.telegram.org/bot{token}/setWebhook?url={wh_url}")
                console.print(f"\nResponse: {r.json()}")
            pause()


# ══════════════════════════════════════════════════════════
#  MAIN MENU
# ══════════════════════════════════════════════════════════

def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    while True:
        show_header()
        show_status()

        console.print("\n[bold]📋 MAIN MENU[/bold]\n")
        console.print("  [1] 🕷️  Crawler        — Add sites, crawl, manage")
        console.print("  [2] 📝 Prompt         — Edit AI system prompt")
        console.print("  [3] 📊 Database       — Data files, FAISS, ingest")
        console.print("  [4] ⚙️  Settings       — LLM, embedding, config.yaml")
        console.print("  [5] 🧪 Test Query     — Test AI responses")
        console.print("  [6] 🚀 Services       — Start/stop/restart")
        console.print("  [0] 🚪 Exit")

        ch = Prompt.ask("\n[bold]Choose[/bold]", choices=["0","1","2","3","4","5","6"], default="0")

        if ch == "0":
            console.print("\n👋 [bold]Goodbye![/bold]\n")
            break
        elif ch == "1":
            menu_crawler()
        elif ch == "2":
            menu_prompt()
        elif ch == "3":
            menu_database()
        elif ch == "4":
            menu_settings()
        elif ch == "5":
            menu_test()
        elif ch == "6":
            menu_services()


if __name__ == "__main__":
    main()
