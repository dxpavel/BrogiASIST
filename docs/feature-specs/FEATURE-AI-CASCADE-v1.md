---
Název: FEATURE-AI-CASCADE-v1
Soubor: docs/feature-specs/FEATURE-AI-CASCADE-v1.md
Verze: 1.0
Datum vytvoření: 2026-05-04
Autor: Pavel + Brogi (chat session)
Status: SPEC-READY (čeká na implementaci ve 2 sessions)
Branch: session/2026-05-04-m2-m3-m4 → bude nová pro implementaci
Předchází: M3 (STATUS column), M4 (decision_rules editor) — hotové ve stejné session
---

# FEATURE: AI Cascade — Llama → Claude → učení

## 1. CÍL (jedna věta)

Klasifikovat příchozí emaily ve **třech vrstvách** tak, aby:

1. Deterministická pravidla (decision_rules) odfiltrovala jasné případy (header X-Brogi-Auto, List-Id, multipart/encrypted, …) BEZ AI calls
2. **Llama 3.2** (lokální Ollama) klasifikovala zbytek a vrátila confidence; pokud confidence ≥ threshold (default 0.90) → trust
3. Pokud Llama confidence < threshold → eskalace na **Claude Haiku 4.5** (cloud API), který provede „celý pre-návrh" (typ, task_status, topics, suggested_action, suggested_task_title/due) a zapíše to do **Chroma `email_actions`** pro budoucí decision_rules `chroma_match` reuse

Cílová UX: Pavel v TG vidí pre-vyplněnou notifikaci s doporučenou akcí, klikne **✓ Potvrdit** (= aplikuj pre-návrh) nebo zvolí jiný button (= override + nauč se).

---

## 2. ARCHITEKTURA (high-level diagram)

```
┌──────────────────────────────────────────────────────────────────┐
│  IMAP IDLE / scan → ingest_email.py → email_messages (status=new)│
└─────────────────────────────────┬────────────────────────────────┘
                                  ▼
                  ┌─────────────────────────────┐
                  │ classify_emails.py          │
                  │ classify_new_emails()       │
                  └──────────────┬──────────────┘
                                 ▼
        ┌────────────────────────────────────────────────────┐
        │ decision_engine.evaluate_email()                   │
        │  • header rules (priority 5–40)                    │
        │  • subject/body keyword [NEW M5-L]                 │
        │  • group rules (50, 70)                            │
        │  • chroma_match (60) ←── učení z Claude verdiktů   │
        │  • sender (custom)                                 │
        │  • ai_fallback (80) → run_llama                    │
        └──────────────┬─────────────────────────────────────┘
                       ▼
        ┌────────────────────────────────────────┐
        │ Llama (Ollama llama3.2-vision:11b)     │
        │ vrátí: typ, task_status, is_spam,      │
        │        confidence, reason              │
        └──────────────┬─────────────────────────┘
                       │
              confidence < 0.90?
            ┌──────────┴──────────┐
            ▼ YES                 ▼ NO
   ┌────────────────────┐   ┌────────────────────┐
   │ Claude Haiku 4.5   │   │ Trust Llama        │
   │ pre-návrh (5 polí) │   │ → write DB         │
   │ → write DB+Chroma  │   │ → notify TG        │
   └─────────┬──────────┘   └────────────────────┘
             ▼
   ┌────────────────────────────────────┐
   │ TG notify s pre-návrhem            │
   │ "🤖 Claude: ÚKOL · 2of · "Title""  │
   │ [✓ Potvrdit] [2rem] [2cal] [2skip] │
   └────────────────────────────────────┘
```

---

## 3. LLAMA VRSTVA (session 2 — „Llama refinement")

### 3.1 Nové decision_rules condition types

| condition_type | Operátory | Příklad |
|---|---|---|
| `subject` | `contains`, `starts_with`, `ends_with`, `equals`, `regex` | `{"value":"faktura","operator":"contains","case_insensitive":true}` |
| `body` | `contains`, `regex` | `{"value":"\\[BrogiASIST-auto\\]","operator":"regex"}` |

**Engine implementace:** `services/ingest/decision_engine.py` — přidat `_eval_subject()` a `_eval_body()`. Body se bere z `email.body_text` (max 2000 znaků pro performance).

**UI:** rozšířit select v `pravidla.html` modalu o `subject` a `body`.

### 3.2 Confidence threshold escalation

V `services/ingest/classify_emails.py:classify_new_emails`:

```python
CONFIDENCE_THRESHOLD = float(os.getenv("CLAUDE_VERIFY_THRESHOLD", "0.90"))

# po Llama call
if confidence < CONFIDENCE_THRESHOLD and not no_auto:
    claude_result = _claude_verify_full(from_addr, subject, body, llama_result, topics_catalog)
    if claude_result:
        # přepsat výsledek
        typ = claude_result["typ"]
        task_status = claude_result.get("task_status")
        topics = claude_result.get("topics", [])
        suggested_action = claude_result.get("suggested_action")
        suggested_task_title = claude_result.get("suggested_task_title")
        suggested_task_due = claude_result.get("suggested_task_due")
        confidence = claude_result.get("confidence", 0.95)
        ai_source = "claude"
        # uložit do Chroma pro budoucí chroma_match
        _learn_from_claude(email_id, from_addr, subject, body, claude_result)
```

### 3.3 Llama prompt — refinement (volitelně session 2)

Pokud zjistíme že Llama často vrací nesmysly, přidat:
- explicitnější rozdělení TYP s few-shot příklady
- omezení na `confidence` jen 0.0/0.5/0.9 (kategorické místo continuous)
- validation pass (post-call sanitize) — už máme z BUG-013

---

## 4. CLAUDE VRSTVA (session 3 — „Pre-návrh")

### 4.1 Kdy se Claude volá

Trigger: Llama `confidence < CLAUDE_VERIFY_THRESHOLD` (default 0.90)

**Opt-out flagy:**
- `decision_rules` může vrátit `no_claude_verify: true` (např. pro VIP skupiny — Pavel chce TG notify hned bez AI delay)
- Email má flag `is_personal=true` → skip Claude (osobní emaily klasifikuje Pavel ručně)

**Cache:** prvotní lookup do Chroma — pokud cosine < 0.10 s předchozím emailem od stejného sender s Claude verdiktem → reuse verdikt bez API call (úspora).

### 4.2 Claude prompt (česky, structured JSON return)

```python
CLAUDE_PROMPT_TEMPLATE = """Jsi pomocník Pavla pro klasifikaci emailů v systému BrogiASIST.

Llama 3.2 dala nízkou jistotu, potřebuju tvoje rozhodnutí.

ODESÍLATEL: {from_addr}
PŘEDMĚT: {subject}
OBSAH (prvních 1500 znaků):
{body}

LLAMA NÁVRH (nízká jistota {llama_confidence:.0%}):
typ={llama_typ}, task_status={llama_task_status}, is_spam={llama_is_spam}
reason: {llama_reason}

PAVLOVY KATEGORIE (topics — tagy které Pavel definoval v admin/topics):
{topics_catalog}

PRAVIDLA TYPU (vyber přesně jeden):
- ÚKOL: někdo na mě v obsahu čeká nebo ode mě něco očekává
- DOKLAD: faktura/účtenka/proforma/potvrzení platby
- NABÍDKA: marketing s explicitním call-to-action koupit/zkusit
- NOTIFIKACE: shrnutí/oznámení o stavu, bez vyžadované akce ode mě
- POZVÁNKA: kalendářová událost / meeting / event
- INFO: novinky / changelog / blog post bez akce
- ERROR: bounce / delivery failure / tech error
- LIST: mailing list (List-Id header detect už proběhl)
- ENCRYPTED: zašifrovaný (multipart/encrypted detect už proběhl)

PRAVIDLA AKCE (vyber jeden suggested_action):
- 2of:     vytvoř OmniFocus task (pro ÚKOL/DOKLAD pokud potřeba follow-up)
- 2rem:    vytvoř Apple Reminder (pro krátkodobé připomínky)
- 2cal:    vytvoř kalendářovou událost (pro POZVÁNKA)
- 2note:   uložit do Apple Notes (pro INFO/DOKLAD k archivaci)
- 2hotovo: označit jako hotové, přesunout do HOTOVO (pro NOTIFIKACE bez další akce)
- 2del:    rychle smazat (duplicita / šum, NEoznačí sender jako spam)
- 2spam:   označit sender jako spam (auto-trash budoucí maily od něj)
- 2unsub:  odhlásit z newsletteru (pro NABÍDKA / INFO s List-Unsubscribe)
- 2skip:   ponechat v inboxu, Pavel rozhodne ručně

VRÁT JEN VALIDNÍ JSON, žádný markdown, žádný úvod:
{{
  "typ": "<ÚKOL|DOKLAD|NABÍDKA|NOTIFIKACE|POZVÁNKA|INFO|ERROR>",
  "task_status": "<ČEKÁ-NA-ODPOVĚĎ|null>",
  "is_spam": <true|false>,
  "topics": ["<tag1>", "<tag2>"],
  "suggested_action": "<2of|2rem|2cal|2note|2hotovo|2del|2spam|2unsub|2skip>",
  "suggested_task_title": "<krátký název pro OF/REM, max 80 znaků|null>",
  "suggested_task_due": "<ISO date YYYY-MM-DD nebo null>",
  "confidence": <0.0-1.0>,
  "reason": "<1 věta proč>"
}}
"""
```

### 4.3 Model + parametry

| Parametr | Hodnota | Důvod |
|---|---|---|
| Model | `claude-haiku-4-5` | rychlý, levný (~0.05 Kč/email), stačí pro klasifikaci |
| Fallback model | `claude-sonnet-4-6` | pro super-kontroverzní (volitelně, jen pokud Haiku vrátí nízký confidence) |
| max_tokens | 500 | structured JSON je krátký |
| temperature | 0.0 | deterministika |
| Anthropic SDK verze | použít existující `anthropic-version: 2023-06-01` jako v `_claude_verify_spam` |
| Prompt caching | použít cache `cache_control` pro topics_catalog (nemění se často) | šetří tokens při každém volání |

### 4.4 Topics catalog jako kontext

`topics` tabulka v DB (admin.html → topics CRUD už existuje). Před voláním Claude se načte celý seznam:

```sql
SELECT id, name, signals FROM topics WHERE active = TRUE;
```

Předáno do promptu ve formátu:
```
- FAKTURACE: faktura, proforma, vyúčtování
- FORPSI: forpsi.cz, doména, hosting
- DRON: DJI, dron, FPV
…
```

Claude pak vrací relevantní subset. Topics se ukládají jako `email_messages.topics jsonb` (nová migrace 016).

---

## 5. STORAGE / UČENÍ

### 5.1 Schema změny (migrace `sql/017_ai_cascade.sql`)

```sql
-- Pre-návrh fields v email_messages
ALTER TABLE email_messages
  ADD COLUMN IF NOT EXISTS topics             jsonb DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS suggested_action   varchar(16),
  ADD COLUMN IF NOT EXISTS suggested_task_title text,
  ADD COLUMN IF NOT EXISTS suggested_task_due  date,
  ADD COLUMN IF NOT EXISTS ai_source          varchar(16) DEFAULT 'llama';
                                              -- 'llama' | 'claude' | 'rule' | 'chroma'

-- Index pro rychlé lookup topics
CREATE INDEX IF NOT EXISTS idx_email_messages_topics
  ON email_messages USING gin(topics);

-- Případná tabulka pro auditní log Claude verdiktů (volitelné)
CREATE TABLE IF NOT EXISTS claude_typ_verdicts (
  id              SERIAL PRIMARY KEY,
  email_id        UUID REFERENCES email_messages(id) ON DELETE CASCADE,
  llama_typ       varchar(32),
  llama_confidence numeric(3,2),
  claude_typ      varchar(32),
  claude_response jsonb,
  api_cost_usd    numeric(8,6),
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_claude_typ_verdicts_email
  ON claude_typ_verdicts(email_id);
```

### 5.2 Chroma email_actions učení

Po každém Claude verdiktu zapsat do Chroma:
- ID: `email_id`
- Embedding: subject + body[:1000] (existující model)
- Metadata: `{"source": "claude_verify", "typ": ..., "suggested_action": ..., "topics": [...]}`

**Reuse v decision_engine `chroma_match`** (priority 60):
- threshold 0.10 (přísnější než aktuální 0.15) → high-confidence reuse
- pokud match → aplikovat metadata.suggested_action + topics → `apply_remembered`

### 5.3 Pavlův override = signál učení (okamžité, dual-track)

Když Pavel klikne **jiný** button než `suggested_action`:

**Track A — content-based učení (Chroma):**
- nahradit Chroma metadata novou hodnotou (`source="pavel_override"`)
- zvýšit weight (násobitel 2× pro vector search) aby override byl preferován
- důvod: **útočníci posílají stejný pattern z různých adres** → vector embedding matchne i nový sender

**Track B — sender-based učení (classification_rules):**
- přidat / update v `classification_rules`: `(mailbox, sender_email) → suggested_action`
- hit_count++ při každém potvrzení
- důvod: stejný legitní sender (např. forpsi@) má konzistentní akci

**Obě tracks běží paralelně, oba **okamžitě** (1 override = 1 zápis, žádné batching).**

Při budoucím emailu:
1. classification_rules sender match (rychlé, deterministické) → použij
2. jinak Chroma vector match → použij (i pokud sender nový!)
3. jinak Llama → Claude

---

## 6. UI FLOW (TG)

### 6.1 Aktuální TG layout (3×3, univerzální)

Z `notify_emails.py`:
```
[2of]    [2rem]    [2cal]
[2note]  [2hotovo] [2del]
[2spam]  [2unsub]  [2skip]
```

### 6.2 Nový layout s pre-návrhem

```
🤖 BrogiASIST · ÚKOL · DXPSOLUTIONS · ⏺ NOVÝ
Od: forpsi <noreply@forpsi.com>
Předmět: Proforma faktura — doména dxpsolutions.cz

[Body preview, 200 znaků]

🏷 Tagy: FAKTURACE · FORPSI
🤖 Claude doporučuje: 2of · "Zkontrolovat fakturu Forpsi 2026-04" (do 2026-05-10)
   confidence 0.92 · "Forpsi posílá proforma fakturu před vypršením domény"

[✓ Potvrdit (2of)]   [2rem]    [2cal]
[2note]              [2hotovo] [2del]
[2spam]              [2unsub]  [2skip]

ai_source: claude (escalated, Llama confidence: 0.65)
```

**„✓ Potvrdit"** = pre-vyplněný callback `email:confirm_suggested:<id>` → backend načte `suggested_action` z DB a aplikuje stejně jako klik na ten button — ALE s pre-vyplněnými fields (suggested_task_title, suggested_task_due).

### 6.3 Případy bez pre-návrhu

- Llama confidence ≥ 0.90 → standardní layout (žádný pre-návrh řádek, žádný „Potvrdit")
- decision_rules end (header_list, header_encrypted, …) → standardní layout per TYP
- AI cascade neproběhla (offline / timeout) → fallback Llama-only, log warning

---

## 7. CONFIG / ENV PROMĚNNÉ

```env
# AI cascade (M5)
CLAUDE_VERIFY_THRESHOLD=0.90
CLAUDE_VERIFY_MODEL=claude-haiku-4-5
CLAUDE_VERIFY_FALLBACK_MODEL=claude-sonnet-4-6
CLAUDE_VERIFY_FALLBACK_THRESHOLD=0.70
                          # pokud Haiku vrátí confidence < 0.70 → eskaluj na Sonnet
CLAUDE_VERIFY_BODY_MAX=1500    # max znaků body do promptu
CLAUDE_VERIFY_CACHE_TTL=86400  # 24h cache pro identické (email_id) verdikty
ANTHROPIC_API_KEY=sk-...       # (už máme z _claude_verify_spam)
```

---

## 8. SESSION 2 — implementační kroky (Llama)

| Krok | Co | Soubor | Náročnost |
|---|---|---|---|
| 1 | Engine `_eval_subject()` + `_eval_body()` s operátory contains/starts_with/regex | `services/ingest/decision_engine.py` | 30 min |
| 2 | UI select rozšíření o `subject` / `body` v modalu | `services/dashboard/templates/pravidla.html` | 10 min |
| 3 | Backend validace nového condition_type v POST/PUT | `services/dashboard/main.py:DecisionRuleIn` | 5 min |
| 4 | Smoke test: vytvořit pravidlo „subject contains 'faktura' → typ=DOKLAD" + ověřit fire | manuálně přes UI | 15 min |
| 5 | Confidence threshold logika (čte env, escaluje placeholder) — ALE Claude call ještě ne, jen log warning | `classify_emails.py` | 20 min |
| 6 | Sanitize lessons #42 (typ/task_status) + BUG-013 (confidence) — verify | `classify_emails.py` | review only |

**Sumár session 2: ~1.5 h.**

---

## 9. SESSION 3 — implementační kroky (Claude AI cascade)

| Krok | Co | Soubor | Náročnost |
|---|---|---|---|
| 1 | Migrace 016: `email_messages` ALTER (topics, suggested_*, ai_source) + `claude_typ_verdicts` | `sql/017_ai_cascade.sql` | 20 min |
| 2 | `_claude_verify_full()` funkce — API call, JSON parse, sanitize | `classify_emails.py` | 1 h |
| 3 | Topics catalog loader (cache 24h) | `classify_emails.py` | 30 min |
| 4 | Wire do `classify_new_emails`: trigger pokud confidence < threshold | `classify_emails.py` | 30 min |
| 5 | Chroma write `email_actions` s `source=claude_verify` | `chroma_client.py` (existing) | 30 min |
| 6 | TG message s pre-návrhem řádkem + ✓ Potvrdit button | `notify_emails.py` | 1 h |
| 7 | TG callback handler `email:confirm_suggested:<id>` | `telegram_callback.py` | 30 min |
| 8 | Dashboard: zobrazit topics + suggested_action v email tabulce | `index.html` + main.py SELECT | 30 min |
| 9 | Smoke test live: 5–10 reálných emailů projít cascade, verifikovat výsledek + cost (Anthropic dashboard) | manuálně | 30 min |
| 10 | Lessons learned + handoff | `docs/brogiasist-lessons-learned-v1.md` + handoff | 30 min |

**Sumár session 3: ~6 h.**

---

## 10. ROZHODNUTÍ (vyřešeno 2026-05-04)

| # | Otázka | Rozhodnutí |
|---|---|---|
| 1 | Topics catalog velikost | DEV má 14 topics (PROD řádově stejně) → prompt krátký, žádný cluster needed |
| 2 | Učení timing | **Okamžitě** — 1 override = 1 zápis. Učení podle uživatele (sender) **i podle obsahu** (vector embedding). Důvod: útočníci posílají stejný pattern z různých adres → matching na obsah, ne jen na sender. |
| 3 | Multilang | **CZ + EN** — Claude prompt mluví česky, ale akceptuje EN obsah (Claude umí oba). Žádné language detection nepotřeba. |
| 4 | Cost | **Monitoring stačí** — log per-email cost do `claude_typ_verdicts.api_cost_usd`, agregát v dashboardu. **Žádný hard limit.** |
| 5 | TTL pre-návrhu | **Žádný reset** — pre-návrh zůstává platný do první akce Pavla. Pokud Pavel zignoruje TG, příště otevře dashboard a klikne tam. |
| 6 | Backfill historických emailů | **Ne, neděláme.** Chroma se naplní organicky z nových emailů. |

---

## 11. RIZIKA

| Riziko | Pravděpodobnost | Mitigace |
|---|---|---|
| Anthropic API outage | low | fallback na Llama-only s log warning |
| Claude vrátí invalid JSON | medium | sanitize + retry 1× s lower temperature, pak fallback na Llama |
| Claude doporučí akci kterou Pavel nikdy neklikne (špatný prompt) | medium | iterate prompt po prvních 100 emailech, monitor override rate |
| API cost > budget | low | env limit + auto-degrade na Llama-only po dosažení |
| Chroma `email_actions` zaplevelena špatnými verdikty | medium | weight Pavlův override vyšší než auto-Claude, periodic Chroma audit (existuje `chroma_audit.py`) |
| Llama confidence dramaticky vyšší než reálná přesnost | high | porovnání Llama vs Claude na první 100 emailech → kalibrace threshold |

---

## 12. METRIKY ÚSPĚCHU

Po session 3, sledovat 14 dní:

| Metrika | Cíl |
|---|---|
| Override rate (Pavel klikl něco jiného než suggested_action) | < 20 % |
| Confirm rate (Pavel klikl ✓ Potvrdit) | > 60 % |
| Skip rate (Pavel zignoroval TG) | < 15 % |
| Claude API cost / měsíc | < 100 Kč |
| Llama → Claude eskalace ratio | 30–50 % (pokud > 50 → Llama prompt slabý, pokud < 20 → threshold příliš nízký) |
| Chroma `email_actions` size | rostoucí, > 200 records po měsíci |
| `chroma_match` hit rate v decision_engine | > 30 % (= učení reálně funguje) |

---

## 13. ZÁVISLOSTI / PŘEDPOKLADY

- **ANTHROPIC_API_KEY** musí být platný (existuje, používá se pro `_claude_verify_spam`)
- **OLLAMA_URL** musí být `http://ollama:11434` (per CLAUDE.md sekce 4)
- **ChromaDB `email_actions`** collection musí existovat (existuje, viz `chroma_client.py`)
- **`topics`** tabulka existuje + Pavel ji udržuje (admin.html)
- **`classification_rules`** tabulka existuje (sender memory) — bude použita jako sekundární učící store

---

## 14. CHANGELOG TOHOTO SOUBORU

| Datum | Verze | Změna |
|---|---|---|
| 2026-05-04 | 1.0 | Initial spec — 3-vrstvý cascade návrh, 2 implementační sessions |
| 2026-05-04 | 1.1 | Open otázky → Rozhodnutí (sekce 10): 14 topics OK, učení okamžité dual-track (content + sender), CZ+EN, cost jen monitoring, žádný TTL reset, žádný backfill |

---

> **Status:** SPEC-READY. Otevřené otázky v sekci 10 dořešit před session 3.
> Implementaci začít session 2 (Llama subject/body keyword + threshold logic).
> Session 3 je velký kus (~6 h), naplánovat jako samostatný blok.
