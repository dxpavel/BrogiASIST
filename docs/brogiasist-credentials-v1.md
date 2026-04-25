---
Název: Credentials BrogiMatAssistance
Soubor: docs/brogimat-assistance-credentials-v1.md
Verze: 3.0
Poslední aktualizace: 2026-04-22
Popis: Všechny přístupy, tokeny, hesla — kompletní inventura
---

⚠️ Tento soubor obsahuje citlivé údaje. Nesdílet, nezálohovat do cloudu. Gitignorováno.

# Credentials — BrogiASIST

---

## IMAP — emailové účty

| Účet | Host | Port | Šifrování | User | Heslo / Token | Status |
|---|---|---|---|---|---|---|
| brogi@dxpsolutions.cz | mail.dxpsolutions.cz | 993 | SSL | brogi | xySren-ryhco5-hadkun | ✅ |
| pavel@dxpsolutions.cz | mail.dxpsolutions.cz | 993 | SSL | pdrexler | KozaDojiKrev666 | ✅ |
| support@dxpsolutions.cz | mail.dxpsolutions.cz | 993 | SSL | support | kahtu3-zUbhyf-pesmuk | ✅ |
| servicedesk@dxpsolutions.cz | mail.dxpsolutions.cz | 993 | SSL | servicedesk | cytdy8-Tehtij-rejpej | ✅ |
| dxpavel@gmail.com | imap.gmail.com | 993 | SSL | dxpavel@gmail.com | iiekgjkcuxddrisu (App PW) | ✅ |
| dxpavel@icloud.com | imap.mail.me.com | 993 | SSL | dxpavel | oqjf-qiul-pmiw-eoib (App PW) | ✅ |
| padre@seznam.cz | imap.seznam.cz | 993 | SSL | padre@seznam.cz | EVEX | ✅ |
| postapro@dxpavel.cz | imap.forpsi.com | 143 | STARTTLS | postapro@dxpavel.cz | DxPavelHeslo2217 | ✅ |
| zamecnictvi.rozdalovice@gmail.com | imap.gmail.com | 993 | SSL | zamecnictvi.rozdalovice@gmail.com | jgqsbwquwmeazmti (App PW) | ✅ |

---

## RSS — The Old Reader

| Parametr | Hodnota |
|---|---|
| URL | https://theoldreader.com |
| API base | https://theoldreader.com/reader/api/0/ |
| User | dxpavel |
| Heslo | KoLeDi35 |
| Počet feedů | 20 |
| Auth | POST /accounts/ClientLogin → token |

---

## YouTube

| Parametr | Hodnota |
|---|---|
| Client ID | 469656228708-ni8167k79laco1skpe2d13qr0sd24rf2.apps.googleusercontent.com |
| Client Secret | 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 |
| Refresh Token | 1//03fCsUKPOc7y4CgYIARAAGAMSNwF-L9IruA2_r-1MFLxzznCT77IKZoEC2xvb9ETWFvlf73HpQ8PfS_sUPo6GEihVD_x4PP8c9zU |
| OAuth typ | Desktop app — "BrogiASIST" |
| Project | gen-lang-client-0947843180 |
| Scope | youtube.readonly |
| Počet odběrů | 171 kanálů |
| JSON client secret | ~/Downloads/client_secret_469656228708-...json |

---

## MantisBT

| Parametr | Hodnota |
|---|---|
| URL | https://servicedesk.dxpavel.cz |
| API base | https://servicedesk.dxpavel.cz/api/rest/ |
| Verze | 2.27.1 |
| API token | nj60BIAOPJFNCXR3NxgHVKuv-j9TB6ux |
| Auth header | `Authorization: nj60BIAOPJFNCXR3NxgHVKuv-j9TB6ux` (bez Bearer!) |
| Projekty | DXP_PHOTOSPACE, DXP_SERVICEDESK, DXP_SOLUTIONS |
| User | BROGI (manager) |

---

## Telegram

| Parametr | Hodnota |
|---|---|
| BrogiNotify token | (v .env — TELEGRAM_BOT1_TOKEN) |
| BrogiAssist token | (v .env — TELEGRAM_BOT2_TOKEN) |
| Pavel chat_id | 7344601948 |
| Pavel username | @dxpavel |

---

## n8n (Synology)

| Parametr | Hodnota |
|---|---|
| URL | http://localhost:5678 |
| Účet | dxpavel@gmail.com |
| Heslo | rozqy4-cEhfyt-dytcih |
| License key | 0ce0a76e-28ae-4eb9-a786-fca209e2a8f4 |
| API key | eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlYTY2NTc4Ni1mMWRiLTRkNmYtOTQ4OS0wZGY3ZGMzOWYzNjciLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiMDYxYzNmM2YtZDhhZi00NzU1LTg0MGMtYzBlYTg3MGFmOWQxIiwiaWF0IjoxNzcyMjczMzE3fQ.jZHXaNBR8gXMss0UqFyng7mgpzYMzAQJvHkcYpOwA-8 |

---

## Webhook bridge (Mac Studio)

| Parametr | Hodnota |
|---|---|
| IP | 10.55.2.117 |
| Port | 8765 |
| Token | brogi-secret-2026 |
| Health | http://10.55.2.117:8765/health |
| Task endpoint | POST http://10.55.2.117:8765/task |

---

## SSH — Mac Studio (PROD)

| Parametr | Hodnota |
|---|---|
| Host | 10.55.2.117 |
| User | dxpavel |
| SSH Key | ~/.ssh/id_ed25519 |
| Příkaz | `ssh -i ~/.ssh/id_ed25519 dxpavel@10.55.2.117` |
| Status | ✅ Testováno 2026-04-07 |

---

## WordPress REST API

### dxpsolutions.cz
| Parametr | Hodnota |
|---|---|
| URL | https://dxpsolutions.cz |
| REST endpoint | https://dxpsolutions.cz/wp-json/wp/v2 |
| Username | BROGIAI |
| Application Password | WbJP U3ef vS7j ZPN0 haj0 sYmd |
| Auth header | `Authorization: Basic QlJPR0lBSTpXYkpQIFUzZWYgdlM3aiBaUE4wIGhhajAgc1ltZA==` |

### zamecnictvi-rozdalovice.cz
| Parametr | Hodnota |
|---|---|
| URL | https://www.zamecnictvi-rozdalovice.cz |
| REST endpoint | https://www.zamecnictvi-rozdalovice.cz/wp-json/wp/v2 |
| Username | BROGIAI |
| Application Password | 8gyO J1tp 1QAk Z9EC I87N y2nP |
| Auth header | `Authorization: Basic QlJPR0lBSTg4Z3lPIEoxdHAgMVFBayBaOUVDIEk4N04geTJuUA==` |

---

## WordPress — oprávnění asistenta

| Akce | Asistent | Pavel |
|---|---|---|
| Čtení příspěvků | ✅ | ✅ |
| Vytvoření / editace DRAFT | ✅ | ✅ |
| Přidání obrázků, tagů, kategorií | ✅ | ✅ |
| **Publikace** | ❌ ZAKÁZÁNO | ✅ pouze Pavel |
| Smazání | ❌ | ✅ |
