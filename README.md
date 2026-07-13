# RedBeard Social Agent

**Semi-automatic social media content system for [RedBeard Risk](https://redbeardrisk.com)** — IT & cybersecurity for Arizona trade businesses (HVAC, plumbing, electrical, construction).

Designed to run reliably on a **Raspberry Pi 5**, generate post batches **twice per week**, and wait for **human approval** before anything goes near LinkedIn, Facebook, or Instagram.

> **v1 safety rule:** nothing is auto-posted. Generate → review in the local dashboard → export copy-paste packs → publish yourself.

---

## What it does

| Piece | Role |
|--------|------|
| **Grok / OpenAI-compatible LLM** | Writes posts in “The Beard” voice (practical, no jargon, slightly bold) |
| **4 content pillars** | Problem→Solution, Educational, Local/BTS, Opinion |
| **Batch planner** | Mixes pillars, platforms, and industries so batches don’t feel repetitive |
| **JSON storage** | Atomic writes on disk — no database required |
| **Flask dashboard** | Approve / reject / bulk review on your LAN |
| **Cron + systemd** | Pi-native scheduling and always-on review UI |
| **Full logging** | Rotating logs under `data/logs/` |

### Platforms (draft copy only)

- LinkedIn  
- Facebook  
- Instagram  

### Content strategy

1. **Problem → Solution** — shop-floor pain, practical fix  
2. **Educational / How-To** — MFA, backups, offboarding, insurance questions  
3. **Local / Behind the Scenes** — Mesa, East Valley, Arizona trade life  
4. **Opinion / Contrarian** — “cousin IT,” MSP jargon, checkbox security  

Tone examples: see [`examples/sample_posts.md`](examples/sample_posts.md).

---

## Folder structure

```
redbeard-social-agent/
├── agent/
│   ├── cli.py                 # Click CLI entry
│   ├── config.py              # YAML + .env loader
│   ├── models.py              # Post / Batch models
│   ├── storage.py             # Atomic JSON storage
│   ├── logging_setup.py
│   ├── content/
│   │   ├── generator.py       # Batch generation
│   │   ├── pillars.py         # Mix planning + seed angles
│   │   └── prompts.py         # “The Beard” prompts
│   ├── llm/
│   │   └── client.py          # OpenAI-compatible client (Grok)
│   ├── scheduler/
│   │   └── jobs.py            # Cron-friendly jobs
│   ├── publishing/
│   │   └── exporter.py        # Approved → markdown/JSON packs
│   └── dashboard/
│       ├── app.py             # Flask review UI
│       ├── templates/
│       └── static/css/
├── config.yaml                # Behavior & brand
├── .env.example               # Secrets template
├── requirements.txt
├── main.py
├── scripts/
│   ├── setup_cron.sh
│   └── install_service.sh
├── systemd/
│   └── redbeard-dashboard.service
├── data/                      # Runtime (posts, logs, exports)
├── examples/sample_posts.md
├── tests/
└── README.md
```

---

## Raspberry Pi 5 — recommended hardware

| Item | Recommendation |
|------|----------------|
| **Board** | Raspberry Pi 5 (8 GB preferred) |
| **Storage** | **M.2 NVMe via official M.2 HAT+** (or compatible) — far more reliable than SD for 24/7 writes |
| **SD card** | Only for boot if needed; put project + `data/` on NVMe |
| **Power** | Official 27 W USB-C PSU |
| **Cooling** | Active cooler or case with fan (summer Arizona garages are not kind) |
| **Network** | Ethernet preferred for dashboard + API calls |

### Why NVMe / M.2 HAT

- Cron generation + rotating logs + JSON batches = constant small writes  
- SD cards wear out and corrupt; NVMe is the “set it on a shelf and forget it” option  
- Mount NVMe as root **or** keep OS on SD and project on `/mnt/nvme` — either works  

**Suggested layout (project on NVMe):**

```bash
# Example after NVMe is mounted at /mnt/nvme
sudo mkdir -p /mnt/nvme/apps
sudo chown $USER:$USER /mnt/nvme/apps
cd /mnt/nvme/apps
git clone <your-repo-url> redbeard-social-agent
# or scp/rsync the folder from your Mac
```

---

## Quick start (Pi 5 / any Linux or macOS)

### 1. System packages (Raspberry Pi OS Bookworm)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

### 2. Project + virtualenv

```bash
cd /path/to/redbeard-social-agent
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure secrets

```bash
cp .env.example .env
nano .env   # or vim / code
```

Minimum:

```env
XAI_API_KEY=xai-...
XAI_BASE_URL=https://api.x.ai/v1
XAI_MODEL=grok-2-latest
FLASK_SECRET_KEY=pick-a-long-random-string
DASHBOARD_PASSWORD=change-me
AUTO_POST_ENABLED=false
```

Get an xAI key: [https://console.x.ai/](https://console.x.ai/)

Optional OpenAI instead of Grok:

```env
USE_OPENAI=true
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

### 4. Brand / schedule settings

Edit `config.yaml` for industries, pillar weights, posts per batch, platform enable flags, and voice-related brand fields. Secrets stay in `.env`.

### 5. Smoke test (no API spend)

```bash
source .venv/bin/activate
python -m agent.cli generate --dry-run --count 6
python -m agent.cli list-batches
python -m agent.cli status
```

### 6. Real generation

```bash
python -m agent.cli generate
# or fewer posts while testing:
python -m agent.cli generate --count 6 --label "First real batch"
```

### 7. Review dashboard

```bash
python -m agent.cli dashboard
# → http://<pi-ip>:5050/
```

On the Pi itself: `http://127.0.0.1:5050/`  
From your laptop on the same LAN: `http://192.168.x.x:5050/`

Approve posts → **Export approved** → open the markdown pack under `data/exports/` → paste into LinkedIn / Facebook / Instagram.

---

## CLI reference

```bash
python -m agent.cli generate [--count N] [--label "..."] [--seed N] [--dry-run]
python -m agent.cli status
python -m agent.cli list-batches
python -m agent.cli export <batch_id>
python -m agent.cli approve <batch_id> <post_id>
python -m agent.cli reject <batch_id> <post_id>
python -m agent.cli dashboard [--host 0.0.0.0] [--port 5050]
```

Same commands work via `python main.py ...`.

---

## Cron (twice-weekly generation)

Default intent (also in `config.yaml`): **Monday & Thursday 08:00**, `America/Phoenix`.

```bash
chmod +x scripts/setup_cron.sh
./scripts/setup_cron.sh
crontab -l   # verify
```

Manual crontab sketch:

```cron
CRON_TZ=America/Phoenix
0 8 * * 1,4 cd /path/to/redbeard-social-agent && .venv/bin/python -m agent.cli generate >> data/logs/cron-generate.log 2>&1
```

Cron logs: `data/logs/cron-generate.log`  
App logs: `data/logs/agent.log`

---

## systemd (dashboard always on)

```bash
chmod +x scripts/install_service.sh
sudo ./scripts/install_service.sh
```

Useful commands:

```bash
sudo systemctl status redbeard-dashboard
sudo systemctl restart redbeard-dashboard
journalctl -u redbeard-dashboard -f
curl -s http://127.0.0.1:5050/health
```

The unit file template is `systemd/redbeard-dashboard.service` (placeholders filled by the install script).

---

## Workflow (production)

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│  Cron Mon/  │ ──► │  Grok writes │ ──► │  You review │ ──► │  Export MD/  │
│  Thu 08:00  │     │  draft batch │     │  dashboard  │     │  paste post  │
└─────────────┘     └──────────────┘     └─────────────┘     └──────────────┘
                              │
                              ▼
                     data/posts/batch_*.json
                     data/logs/agent.log
```

1. Cron runs `generate` twice a week  
2. Open dashboard on phone/laptop  
3. Approve keepers, reject duds (notes optional)  
4. Export approved → copy-paste to social networks  
5. (Future) optional API publishers under `agent/publishing/` — not in v1  

---

## Configuration map

| Setting | Where |
|---------|--------|
| API keys, dashboard password, ports | `.env` |
| Brand, pillars, platforms, batch size | `config.yaml` |
| Auto-post kill switch | `.env` → `AUTO_POST_ENABLED=false` **and** `config.yaml` → `safety` |

`require_human_approval: true` forces auto-post off even if someone flips the env var.

---

## Logging

- Logger name prefix: `redbeard.*`  
- Rotating file: 5 MB × 5 backups  
- Level: `LOG_LEVEL=INFO` (or `DEBUG` in `.env`)  

---

## Tests (no API key)

```bash
source .venv/bin/activate
pip install pytest   # optional
python -m pytest tests/ -q
# or without pytest:
python tests/test_models_storage.py   # if adapted; prefer pytest
```

```bash
python -m pytest tests/ -q
```

---

## Security notes (Pi on your LAN)

- Change `DASHBOARD_PASSWORD` and `FLASK_SECRET_KEY` before exposing beyond localhost  
- Prefer binding dashboard to LAN only; do **not** port-forward to the public internet without reverse proxy + TLS + stronger auth  
- Never commit `.env`  
- `AUTO_POST_ENABLED` must stay `false` until a tested publisher exists  

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `No LLM API key found` | Set `XAI_API_KEY` in `.env`; re-run from project root |
| Empty / weird JSON posts | Check `data/logs/agent.log`; confirm model name at console.x.ai |
| Dashboard not reachable | `DASHBOARD_HOST=0.0.0.0`, check Pi firewall, same Wi‑Fi/VLAN |
| Cron silent | `crontab -l`, check `data/logs/cron-generate.log`, ensure absolute paths + venv python |
| Permission errors on `data/` | `chown -R $USER:$USER data` |
| Clock / schedule wrong | `sudo timedatectl set-timezone America/Phoenix` and/or `CRON_TZ` |

---

## Future (not in v1)

- LinkedIn / Meta Graph API publishers (still gated by approval)  
- Image generation for Instagram  
- Multi-user review roles  
- SQLite if batch volume grows large  

---

## Example tone

See **[examples/sample_posts.md](examples/sample_posts.md)** for full LinkedIn / Facebook / Instagram samples in The Beard voice.

---

## License

Private use for RedBeard Risk unless you add a license file. Keep API keys and customer details out of git.

---

**Built for the shop, not the boardroom.**  
RedBeard Risk · Mesa / East Valley, Arizona · [redbeardrisk.com](https://redbeardrisk.com)
