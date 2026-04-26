---
Název: Infrastruktura BrogiASIST
Soubor: docs/brogiasist-infrastructure-v1.md
Verze: 4.0
Poslední aktualizace: 2026-04-26
Popis: Fyzické stroje, sítě, DEV stack (reálný), PROD stack (VM 103 brogiasist na pve01), rozdíly
Změněno v: 4.0 — PROD opravena: NE Forpsi VPS, ale Proxmox VM 103 v LAN. Smazány zastaralé reference na os01/forpsi-root.
---

# Infrastruktura — BrogiASIST

---

## Fyzické stroje a VMs

| Stroj | Hostname | IP (LAN) | OS | Role |
|---|---|---|---|---|
| MacBook Pro | Paja-MacBook-Pro | 10.55.2.73 | macOS | **DEV** — vývoj, Claude Desktop |
| Mac Studio | PajaAppleStudio | 10.55.2.117 | macOS 26.3 | **PROD Apple Bridge** — OmniFocus, Notes, Reminders, Files |
| Proxmox host | pve01 | 10.55.2.201 | Proxmox VE 9.1 | **PROD hypervizor** — hostuje VM 103 |
| **VM 103 (PROD)** | **brogiasist** | **10.55.2.231** | **Ubuntu 24.04.4 LTS** | **PROD server** — Docker stack, DB, AI, scheduler |
| Synology NAS | — | LAN | DSM | Sdílené úložiště, zálohy (SynologyDrive) |

## Sítě

| Síť | Rozsah | Kdo vidí koho |
|---|---|---|
| LAN domácí | 10.55.2.0/24 | MacBook ↔ Apple Studio ↔ pve01 ↔ VM 103 — vše navzájem |
| Gateway | 10.55.2.254 | router/firewall |
| Veřejný přístup VM 103 | ❌ žádný | pouze interní LAN, žádný port forwarding |

## SSH přístupy

```bash
# VM 103 brogiasist (PROD)
ssh pavel@10.55.2.231           # default klíč ~/.ssh/id_ed25519, sudo NOPASSWD

# Proxmox host pve01 (správa VM)
ssh root@10.55.2.201            # default klíč

# Apple Studio (macOS)
ssh dxpavel@10.55.2.117
```

---

## DEV — reálný stav (MacBook Pro)

### Docker Compose stack

Projekt: `/Users/pavel/SynologyDrive/001 DXP/009 BrogiASIST/`
Spuštění: `docker compose up -d`

| Kontejner | Image | Port host:container | Účel |
|---|---|---|---|
| `brogi_postgres` | postgres:16 | **5433**:5432 | PostgreSQL (5433 kvůli konfliktu s lokálním PG) |
| `brogi_chromadb` | chromadb/chroma | 8000:8000 | ChromaDB — action learning |
| `brogi_dashboard` | FastAPI build | 9000:9000 | WebUI dashboard |
| `brogi_scheduler` | FastAPI build | 9001:9001 | IMAP IDLE + scheduler + TG callback |

### Služby mimo Docker (na MacBook hostu)

| Služba | Port | Autostart | URL z kontejnerů |
|---|---|---|---|
| Apple Bridge (FastAPI) | 9100 | launchd `cz.brogiasist.apple-bridge` | `http://host.docker.internal:9100` |
| Ollama + Llama3.2-vision:11b | 11434 | manuálně / launchd | `http://host.docker.internal:11434` |
| Ollama model nomic-embed-text | — | součást Ollama | totéž |

### Sdílené složky (bind mounts)

| Host cesta | Container cesta | Účel |
|---|---|---|
| `/Users/pavel/Desktop/OmniFocus` | `/app/attachments` | Přílohy emailů (DEV only) |
| `./logs` | `/app/logs` | Logy scheduleru |

### Klíčové ENV hodnoty (DEV)

```env
APPLE_BRIDGE_URL=http://host.docker.internal:9100
OLLAMA_URL=http://host.docker.internal:11434
CHROMA_HOST=chromadb
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
```

### Git

| Větev | Účel |
|---|---|
| `main` | stabilní základ |
| `0.0.1` | první verze |
| `0.1.0` | aktuální DEV (klasifikace, Chroma WebUI, Claude spam, kontakty) |
| `1` | vývoj příloh base64 + PROD příprava |

---

## PROD — VM 103 brogiasist na pve01

### Architektura

```
VM 103 brogiasist (10.55.2.231)              PajaAppleStudio (10.55.2.117)
═══════════════════════════════              ══════════════════════════════
Docker Compose stack:                         Apple Bridge (FastAPI, launchd)
  PostgreSQL                                    → OmniFocus
  ChromaDB                                      → Apple Notes
  Dashboard (WebUI)                             → Apple Reminders
  Scheduler (IMAP, TG, classify)                → ~/Desktop/BrogiAssist/ (přílohy)
Ollama (systemd):                             Beszel agent monitoring (oba stroje)
  llama3.2-vision:11b                         → reportuje do Hub na VM 101
  nomic-embed-text
Beszel agent (Docker, port 45876)
```

### VM 103 specs (vytvořeno 2026-04-26)

| Parametr | Hodnota |
|---|---|
| **VM ID** | 103 (na pve01) |
| **Hostname** | brogiasist |
| **OS** | Ubuntu 24.04.4 LTS (cloud-init z `noble-server-cloudimg-amd64.img`) |
| **vCPU** | 4 (cputype=host) |
| **RAM** | 16 GB |
| **Disk 0** (system) | 80 GB na `local-lvm` (scsi0, discard, ssd) — `/` 77G, `/boot` 881M, `/boot/efi` 105M |
| **Disk 1** (backup) | 100 GB na `local-lvm` (scsi1, discard, ssd) — ext4, mount `/mnt/backup`, owner pavel:pavel, persistent v `/etc/fstab` |
| **Síť** | net0 virtio na `vmbr0`, firewall=1, MAC `BC:24:11:95:A9:93` |
| **IP / GW / DNS** | 10.55.2.231/24 / 10.55.2.254 / 10.55.2.254 (cloud-init) |
| **User** | pavel (sudo NOPASSWD) + 4 SSH klíče (root@pve01, lukas, V1_SSC Ansible, pavel@Paja-MacBook-Pro) |
| **Onboot** | ano |
| **QEMU agent** | enabled |
| **Veřejný expose** | ❌ žádný (jen LAN) |

### VM 103 — Docker Compose stack (PROD BrogiASIST)

| Kontejner | Port host:container | Poznámka |
|---|---|---|
| `postgres` | **5432**:5432 | standardní port (žádný konflikt s DEV) |
| `chromadb` | 8000:8000 | stejné jako DEV |
| `dashboard` | 9000:9000 | interní LAN (žádný proxy zatím) |
| `scheduler` | 9001:9001 | interní |
| `beszel-agent` | host network 45876 | monitoring → reportuje do VM 101 Beszel Hub (compose v `/home/pavel/brogiasist-monitoring/`) |

### VM 103 — mimo Docker

| Služba | Port | Způsob spuštění |
|---|---|---|
| Ollama | 11434 | systemd service (`systemctl start ollama`) — instalovat přes `curl -fsSL https://ollama.com/install.sh | sh` |

### PajaAppleStudio — Apple Bridge (PROD)

| Parametr | Hodnota |
|---|---|
| Umístění | `~/brogiasist-bridge/` |
| Port | 9100 |
| Autostart | launchd `cz.brogiasist.apple-bridge` |
| Python | 3.9.6 (⚠️ nutná kompatibilita — bez `str\|None` syntax) |
| Přílohy složka | `~/Desktop/BrogiAssist/` |
| Full Disk Access | nutný pro Terminal/Python (Calendar, Contacts) |

### Klíčové ENV hodnoty (PROD — rozdíly od DEV)

```env
APPLE_BRIDGE_URL=http://10.55.2.117:9100      # Apple Studio IP (Linux ↔ macOS přes LAN)
OLLAMA_URL=http://172.17.0.1:11434             # Ollama běží na VM 103 host, dosažitelný z Dockeru přes docker0 bridge
CHROMA_HOST=chromadb
POSTGRES_HOST=postgres
POSTGRES_PORT=5432                             # standardní (ne 5433)
ATTACHMENTS_DIR=/app/attachments               # lokální Linux volume na VM 103, NE bind mount Mac plochy
```

> Pozn.: na Linuxu `host.docker.internal` defaultně neexistuje. Použij `172.17.0.1` (IP docker0 bridge) nebo přidej `--add-host=host.docker.internal:host-gateway` do compose.

---

## DEV vs PROD — rozdíly

| Parametr | DEV (MacBook) | PROD (VM 103 brogiasist) |
|---|---|---|
| Docker host | localhost | 10.55.2.231 (LAN) |
| Apple Bridge | MacBook host (`host.docker.internal:9100`) | Apple Studio (`10.55.2.117:9100`) |
| Ollama | MacBook host (`host.docker.internal:11434`) | VM 103 host (`172.17.0.1:11434`) |
| PostgreSQL ext. port | **5433** (conflict fix) | **5432** (standard) |
| Přílohy | bind mount `/Users/pavel/Desktop/OmniFocus` | base64 přes API + lokální `/app/attachments` volume na VM 103 |
| Apple Bridge location | MacBook (stejný stroj jako Docker) | Apple Studio (jiný stroj v LAN) |
| 24/7 provoz | ❌ Mac se uspí | ✅ VM na Proxmoxu |
| Python na Bridge hostu | 3.12+ (MacBook) | 3.9.6 (Apple Studio) — ⚠️ kompatibilita |
| Backup storage | ručně na Synology | Disk 1 `/mnt/backup` (100 GB) — PG dumps, ChromaDB exporty, archive |
| Monitoring | žádný | Beszel agent → VM 101 Hub |

---

## SQL migrace

Soubory v `sql/` — spouštět v pořadí při fresh instalaci:

| Soubor | Obsah |
|---|---|
| `001_init.sql` | Základní tabulky (actions, sessions, config, sources) |
| `002_email.sql` | `email_messages` |
| `003_rss.sql` | `rss_articles` |
| `004_youtube.sql` | `youtube_videos` |
| `005_mantis.sql` | `mantis_issues` |
| `006_omnifocus.sql` | `omnifocus_tasks` |
| `007_apple_apps.sql` | `apple_notes`, `apple_reminders`, `apple_contacts`, `calendar_events` |
| `008_classification.sql` | `classification_rules`, `attachments` |
| `009_topics.sql` | `topics`, `topic_signals`, `topic_intersections` |
| `010_imap_status.sql` | `imap_status` |
| `011_claude_sender_verdicts.sql` | `claude_sender_verdicts` ⚠️ SOUBOR CHYBÍ — nutno vytvořit |

⚠️ Tabulka `claude_sender_verdicts` byla na DEV vytvořena ručně přes psql — SQL soubor neexistuje. Vytvořit před PROD migrací.

---

## Testovací příkazy

```bash
# DEV — health checks
curl http://localhost:9100/health          # Apple Bridge
curl http://localhost:9000/               # Dashboard
docker logs brogi_scheduler --tail 20     # Scheduler logy

# PROD — health checks (po nasazení)
curl http://10.55.2.117:9100/health                              # Apple Bridge na Apple Studiu
ssh pavel@10.55.2.231 'docker logs brogiasist_scheduler --tail 20'

# SSH přístupy
ssh pavel@10.55.2.231                     # VM 103 brogiasist (PROD)
ssh root@10.55.2.201                      # pve01 (správa VM)
ssh dxpavel@10.55.2.117                   # Apple Studio
```
