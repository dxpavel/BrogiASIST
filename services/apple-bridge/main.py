from __future__ import annotations  # Python 3.9 kompat (PROD na Apple Studio) — `str | None` syntax

import base64
import json
import os
import re
import select
import signal
import sqlite3
import time
import urllib.parse
import caldav
from datetime import datetime, timezone, timedelta, date
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI(title="BrogiASIST Apple Bridge", version="1.1")

# Cílová složka pro přílohy přijaté přes base64 z scheduleru.
# Stejná lokace funguje na DEV (MacBook) i PROD (Apple Studio).
ATTACHMENTS_BASE_DIR = os.path.expanduser("~/Desktop/BrogiAssist")

CALDAV_URL = "https://caldav.icloud.com"
CALDAV_USER = os.getenv("ICLOUD_USER", "dxpavel@me.com")
CALDAV_PASS = os.getenv("ICLOUD_PASSWORD", "oqjf-qiul-pmiw-eoib")
CALDAV_SKIP = {"Garmin Connect", "Siri Suggestions", "Birthdays", "Narozeniny",
               "Scheduled Reminders", "České svátky", "české svátky",
               "České státní svátky", "Kalendář bez názvu"}


_OSASCRIPT_PATH = "/usr/bin/osascript"


def _spawn_osascript(args: list[str], timeout: int) -> tuple[int, str, str]:
    """Spustí osascript přes os.posix_spawn() místo subprocess.run().

    Důvod: macOS bug (BUG-008) — fork() v multi-threaded Python procesu
    (uvicorn + FastAPI threadpool) způsobuje SIGSEGV v Network.framework
    atfork hook. posix_spawn je atomický syscall, neforkuje, neprovádí
    kopii address space → atfork hooks se nevolají → bug se neprojeví.

    Return: (returncode, stdout, stderr) — kompatibilní s subprocess.CompletedProcess.
    """
    stdout_r, stdout_w = os.pipe()
    stderr_r, stderr_w = os.pipe()
    file_actions = [
        (os.POSIX_SPAWN_DUP2, stdout_w, 1),
        (os.POSIX_SPAWN_CLOSE, stdout_r),
        (os.POSIX_SPAWN_DUP2, stderr_w, 2),
        (os.POSIX_SPAWN_CLOSE, stderr_r),
    ]
    try:
        pid = os.posix_spawn(_OSASCRIPT_PATH, args, os.environ, file_actions=file_actions)
    except OSError:
        for fd in (stdout_r, stdout_w, stderr_r, stderr_w):
            try: os.close(fd)
            except OSError: pass
        raise

    os.close(stdout_w)
    os.close(stderr_w)

    deadline = time.monotonic() + timeout
    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []
    open_fds = {stdout_r, stderr_r}

    try:
        while open_fds:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                try: os.kill(pid, signal.SIGKILL)
                except ProcessLookupError: pass
                os.waitpid(pid, 0)
                raise TimeoutError(f"osascript timed out after {timeout}s")

            ready, _, _ = select.select(list(open_fds), [], [], remaining)
            if not ready:
                continue
            for fd in ready:
                data = os.read(fd, 65536)
                if not data:
                    open_fds.discard(fd)
                    os.close(fd)
                    continue
                if fd == stdout_r:
                    stdout_chunks.append(data)
                else:
                    stderr_chunks.append(data)
        _, status = os.waitpid(pid, 0)
        returncode = os.waitstatus_to_exitcode(status)
    finally:
        for fd in open_fds:
            try: os.close(fd)
            except OSError: pass

    stdout = b"".join(stdout_chunks).decode("utf-8", errors="replace")
    stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")
    return (returncode, stdout, stderr)


def run_applescript(script: str, timeout: int = 30) -> str:
    rc, out, err = _spawn_osascript(["osascript", "-e", script], timeout)
    if rc != 0:
        raise RuntimeError(err.strip())
    return out.strip()


def run_jxa(script: str, timeout: int = 90) -> any:
    rc, out, err = _spawn_osascript(["osascript", "-l", "JavaScript", "-e", script], timeout)
    if rc != 0:
        raise RuntimeError(err.strip())
    return json.loads(out.strip())


@app.get("/health")
def health():
    return {"ok": True, "ts": datetime.now().isoformat()}


@app.get("/omnifocus/tasks")
def omnifocus_tasks():
    """Vrátí aktivní (nedokončené) tasky z OmniFocus — bulk property fetch."""
    script = """
const of2 = Application('OmniFocus');
const doc = of2.defaultDocument;
const activeTasks = doc.flattenedTasks.whose({completed: false});
const ids       = activeTasks.id();
const names     = activeTasks.name();
const flags     = activeTasks.flagged();
const inboxes   = activeTasks.inInbox();
const dues      = activeTasks.dueDate();
const defers    = activeTasks.deferDate();
const modifieds = activeTasks.modificationDate();
const now = new Date();
const result = [];
for (let i = 0; i < ids.length; i++) {
  let due    = dues[i]      ? dues[i].toISOString()      : null;
  let defer  = defers[i]    ? defers[i].toISOString()    : null;
  let mod    = modifieds[i] ? modifieds[i].toISOString() : null;
  let status = 'available';
  if (due && new Date(due) < now) status = 'overdue';
  else if (due) status = 'due_soon';
  result.push({id: ids[i], name: names[i], flagged: flags[i],
    in_inbox: inboxes[i], due_at: due, defer_at: defer,
    modified_at: mod, status: status});
}
JSON.stringify(result);
"""
    try:
        tasks = run_jxa(script)
        return {"ok": True, "count": len(tasks), "tasks": tasks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/omnifocus/task/{task_id}")
def omnifocus_task_get(task_id: str):
    """Fetch konkrétní OF task podle ID. Pro threading TG flow (sekce 8 spec):
    když přijde nový email v threadu s of_task_id → bot zobrazí "Update existující
    OF task X" + tlačítka [Otevřít OF / Append do notes / Nový task / Skip]."""
    tid_js = json.dumps(task_id)
    script = f"""
const of2 = Application('OmniFocus');
const doc = of2.defaultDocument;
let task;
try {{
  task = doc.flattenedTasks.whose({{id: {tid_js}}})[0];
  if (!task) throw new Error('not_found');
  const props = {{
    id: task.id(),
    name: task.name(),
    note: task.note() || '',
    completed: task.completed(),
    flagged: task.flagged(),
    in_inbox: task.inInbox(),
    due_at:    task.dueDate()    ? task.dueDate().toISOString()    : null,
    defer_at:  task.deferDate()  ? task.deferDate().toISOString()  : null,
    modified_at: task.modificationDate() ? task.modificationDate().toISOString() : null,
  }};
  JSON.stringify({{ok: true, task: props}});
}} catch (e) {{
  JSON.stringify({{ok: false, error: String(e.message || e), task_id: {tid_js}}});
}}
"""
    try:
        return run_jxa(script, timeout=15)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/omnifocus/task/{task_id}/append_note")
def omnifocus_task_append_note(task_id: str, body: dict):
    """Přidá řádek/blok textu k existující OF task notes.

    Použití: nový email v threadu s of_task_id → Pavel klikne "📎 Append do notes"
    → bot zavolá tento endpoint s text (subject + sender + krátký excerpt nového
    emailu), Pavel pak v OF vidí all updates v notes původního tasku.

    Body:
      text: str         — text k apendování (může obsahovat newlines)
      separator: str    — co vložit před text (default '\\n\\n────\\n')
    """
    tid_js = json.dumps(task_id)
    text = body.get("text", "") or ""
    separator = body.get("separator", "\n\n────\n")
    full_text_js = json.dumps(separator + text)
    script = f"""
const of2 = Application('OmniFocus');
const doc = of2.defaultDocument;
try {{
  const task = doc.flattenedTasks.whose({{id: {tid_js}}})[0];
  if (!task) throw new Error('task not found: ' + {tid_js});
  const oldNote = task.note() || '';
  task.note = oldNote + {full_text_js};
  JSON.stringify({{ok: true, task_id: task.id(), new_length: task.note().length}});
}} catch (e) {{
  JSON.stringify({{ok: false, error: String(e.message || e)}});
}}
"""
    try:
        return run_jxa(script, timeout=15)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/omnifocus/projects")
def omnifocus_projects():
    """Vrátí seznam projektů s jejich stavy."""
    script = """
const of = Application('OmniFocus');
const doc = of.defaultDocument;
const projects = doc.flattenedProjects();
const result = [];
for (let i = 0; i < projects.length; i++) {
    const p = projects[i];
    try {
        let due = null, modified = null;
        try { due = p.dueDate() ? p.dueDate().toISOString() : null; } catch(e) {}
        try { modified = p.modificationDate() ? p.modificationDate().toISOString() : null; } catch(e) {}
        result.push({
            id: p.id(),
            name: p.name(),
            status: p.status(),
            flagged: p.flagged(),
            due_at: due,
            modified_at: modified,
            task_count: p.tasks().length
        });
    } catch(e) {}
}
JSON.stringify(result);
"""
    try:
        projects = run_jxa(script)
        return {"ok": True, "count": len(projects), "projects": projects}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reminders/add")
def reminders_add(body: dict):
    """Přidá reminder do Apple Reminders (výchozí seznam).
    Vrací: {ok, name, id} — id potřebujeme pro budoucí undo (DELETE /reminders/{id}).
    """
    name         = body.get("name", "") or ""
    reminder_body = body.get("body", "") or ""
    list_name    = body.get("list", "Reminders")
    # json.dumps zajistí správné escapování \n, \t, uvozovek, unicode
    name_js      = json.dumps(name)
    body_js      = json.dumps(reminder_body)
    list_js      = json.dumps(list_name)
    script = f"""
const rm = Application('Reminders');
const lists = rm.lists.whose({{name: {list_js}}})();
const lst = lists.length > 0 ? lists[0] : rm.lists[0];
const r = rm.Reminder({{name: {name_js}, body: {body_js}}});
lst.reminders.push(r);
const rid = r.id();
JSON.stringify({{ok: true, name: {name_js}, id: rid}});
"""
    try:
        result = run_jxa(script)
        rid = result.get("id") if isinstance(result, dict) else None
        return {"ok": True, "name": name, "id": rid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/reminders/{reminder_id}")
def reminders_delete(reminder_id: str):
    """M2 undo: smaže reminder podle id (vrácený z /reminders/add)."""
    rid_js = json.dumps(reminder_id)
    script = f"""
const rm = Application('Reminders');
try {{
  const rems = rm.reminders.whose({{id: {rid_js}}})();
  if (rems.length === 0) {{
    JSON.stringify({{ok: false, error: 'reminder_not_found'}});
  }} else {{
    rm.delete(rems[0]);
    JSON.stringify({{ok: true, deleted: {rid_js}}});
  }}
}} catch(e) {{
  JSON.stringify({{ok: false, error: e.toString()}});
}}
"""
    try:
        result = run_jxa(script)
        if isinstance(result, dict) and not result.get("ok"):
            raise HTTPException(status_code=404, detail=result.get("error", "reminder delete failed"))
        return result if isinstance(result, dict) else {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/notes/{note_id}")
def notes_get(note_id: str):
    """Fetch konkrétní Apple Notes note podle id. Pro threading TG flow:
    když přijde nový email v threadu s asociovaným note, bot si ho dotahá
    a může zobrazit v TG nebo append text."""
    nid_js = json.dumps(note_id)
    script = f"""
const notes = Application('Notes');
try {{
  const n = notes.notes.whose({{id: {nid_js}}})[0];
  if (!n) throw new Error('not_found');
  const props = {{
    id: n.id(),
    name: n.name() || '',
    body: n.body() || '',
    creation_date:     n.creationDate()     ? n.creationDate().toISOString()     : null,
    modification_date: n.modificationDate() ? n.modificationDate().toISOString() : null,
  }};
  JSON.stringify({{ok: true, note: props}});
}} catch (e) {{
  JSON.stringify({{ok: false, error: String(e.message || e), note_id: {nid_js}}});
}}
"""
    try:
        return run_jxa(script, timeout=15)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/notes/{note_id}/append")
def notes_append(note_id: str, body: dict):
    """Přidá HTML/text k existující Apple Notes note.

    Apple Notes ukládá body jako HTML (nikoli plain text). Pro Apple-friendly
    append vložíme oddělovací <hr/> a text obalený v <div>. Pavel pak v Notes
    vidí klasický horizontal rule + nový blok.

    Body:
      text: str       — text k apendování (HTML escape se aplikuje, znaky < > &)
      separator: bool — zda vložit <hr/> před text (default: True)
    """
    text = body.get("text", "") or ""
    use_sep = body.get("separator", True)

    # HTML escape — Apple Notes tolerantně přijme plain text v body, ale safe je escape
    safe_text = (text.replace("&", "&amp;")
                     .replace("<", "&lt;")
                     .replace(">", "&gt;"))
    safe_text_html = safe_text.replace("\n", "<br/>")

    sep_html = "<hr/>" if use_sep else ""
    append_html = f'{sep_html}<div>{safe_text_html}</div>'

    nid_js = json.dumps(note_id)
    append_js = json.dumps(append_html)
    script = f"""
const notes = Application('Notes');
try {{
  const n = notes.notes.whose({{id: {nid_js}}})[0];
  if (!n) throw new Error('note not found: ' + {nid_js});
  const oldBody = n.body() || '';
  n.body = oldBody + {append_js};
  JSON.stringify({{ok: true, note_id: n.id(), new_length: n.body().length}});
}} catch (e) {{
  JSON.stringify({{ok: false, error: String(e.message || e)}});
}}
"""
    try:
        return run_jxa(script, timeout=15)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/notes/add")
def notes_add(body: dict):
    """Přidá novou poznámku do Apple Notes."""
    name        = body.get("name", "") or ""
    note_body   = body.get("body", "") or ""
    folder_name = body.get("folder", "") or ""
    name_js     = json.dumps(name)
    body_js     = json.dumps(note_body)
    if folder_name:
        folder_js = json.dumps(folder_name)
        script = f"""
const notes = Application('Notes');
const folders = notes.folders.whose({{name: {folder_js}}})();
const folder = folders.length > 0 ? folders[0] : notes.defaultAccount.folders[0];
const n = notes.Note({{name: {name_js}, body: {body_js}}});
folder.notes.push(n);
JSON.stringify({{ok: true, name: {name_js}}});
"""
    else:
        script = f"""
const notes = Application('Notes');
const n = notes.Note({{name: {name_js}, body: {body_js}}});
notes.defaultAccount.notes.push(n);
JSON.stringify({{ok: true, name: {name_js}}});
"""
    try:
        result = run_jxa(script)
        return {"ok": True, "name": name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _safe_filename(name: str) -> str:
    """Stejná sanitizace jako v ingest_email._safe_filename — ať soubory ladí."""
    name = re.sub(r"[^\w.\-]", "_", name or "")
    return name[:200] or "attachment"


def _save_inbound_attachments(email_id: str, files: list) -> list[str]:
    """Decode + uloží přílohy z base64 payloadu na disk.

    Vrací list absolutních cest k uloženým souborům (pro file:// linky).
    Adresář: ~/Desktop/BrogiAssist/<email_id>/<safe_filename>.
    """
    if not files or not email_id:
        return []
    target_dir = os.path.join(ATTACHMENTS_BASE_DIR, email_id)
    try:
        os.makedirs(target_dir, exist_ok=True)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"makedirs {target_dir} failed: {e}")

    saved: list[str] = []
    seen: set[str] = set()
    for f in files:
        fname = _safe_filename(f.get("filename", ""))
        # Deduplikace pokud více souborů má stejný safe filename
        if fname in seen:
            base, ext = os.path.splitext(fname)
            fname = f"{base}_{len(saved)+1}{ext}"
        seen.add(fname)
        b64 = f.get("content_base64", "")
        if not b64:
            continue
        try:
            data = base64.b64decode(b64, validate=True)
        except Exception as e:
            # Špatný base64 vyhodit — radši FAIL než tichý prázdný soubor.
            raise HTTPException(status_code=400, detail=f"base64 decode failed for {fname}: {e}")
        path = os.path.join(target_dir, fname)
        try:
            with open(path, "wb") as fd:
                fd.write(data)
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"write {path} failed: {e}")
        saved.append(path)
    return saved


def _jxa_attach_files(task_name: str, file_paths: list[str]) -> dict:
    """Pokus C — JXA `make new attachment` s detailním errorem.

    Najde poslední task v Inbox jménem task_name (heuristika — předpokládá single-user
    flow během 1 sekundy mezi vytvořením a attachem) a pokusí se přiložit soubory.
    Vrací {ok: bool, attached: int, errors: [str]}.
    """
    if not file_paths:
        return {"ok": True, "attached": 0, "errors": []}
    paths_js = json.dumps(file_paths)
    name_js = json.dumps(task_name)
    script = f"""
const of2 = Application('OmniFocus');
const doc = of2.defaultDocument;
ObjC.import('Foundation');
const wantedName = {name_js};
const paths = {paths_js};
const inbox = doc.inboxTasks;
let target = null;
for (let i = inbox.length - 1; i >= 0 && i > inbox.length - 50; i--) {{
  try {{
    if (inbox[i].name() === wantedName) {{ target = inbox[i]; break; }}
  }} catch(e) {{}}
}}
if (!target) {{
  JSON.stringify({{ok: false, attached: 0, errors: ['task not found in inbox']}});
}} else {{
  let attached = 0;
  let errors = [];
  for (const fp of paths) {{
    try {{
      const att = of2.FileAttachment({{file: Path(fp)}});
      target.attachments.push(att);
      attached++;
    }} catch(e1) {{
      try {{
        of2.make({{new: 'fileAttachment', at: target.attachments,
                   withProperties: {{file: Path(fp)}}}});
        attached++;
      }} catch(e2) {{
        errors.push(fp.split('/').pop() + ': ' + (e2.message || String(e2)));
      }}
    }}
  }}
  JSON.stringify({{ok: attached === paths.length, attached: attached, errors: errors}});
}}
"""
    try:
        return run_jxa(script)
    except Exception as e:
        return {"ok": False, "attached": 0, "errors": [f"JXA exec: {e}"]}


def _applescript_attach_files(task_name: str, file_paths: list[str]) -> dict:
    """Pokus B — AppleScript `make new attachment` jako fallback po JXA.

    AppleScript pracuje s OmniFocus přes `tell application` syntaxi. Pro file
    attachment vyžaduje Mac alias / path string.
    """
    if not file_paths:
        return {"ok": True, "attached": 0, "errors": []}
    # Eskapovaný AppleScript string + POSIX file
    safe_name = task_name.replace('"', '\\"')
    attached = 0
    errors: list[str] = []
    for fp in file_paths:
        safe_fp = fp.replace('"', '\\"')
        script = f'''
tell application "OmniFocus"
    tell default document
        set theTasks to (every inbox task whose name is "{safe_name}")
        if (count of theTasks) is 0 then
            return "ERR: task not found"
        end if
        set theTask to last item of theTasks
        try
            tell theTask
                make new attachment with properties {{file name:POSIX file "{safe_fp}"}}
            end tell
            return "OK"
        on error errMsg
            return "ERR: " & errMsg
        end try
    end tell
end tell
'''
        try:
            out = run_applescript(script, timeout=20)
            if out.startswith("OK"):
                attached += 1
            else:
                errors.append(f"{os.path.basename(fp)}: {out}")
        except Exception as e:
            errors.append(f"{os.path.basename(fp)}: AppleScript exec: {e}")
    return {"ok": attached == len(file_paths), "attached": attached, "errors": errors}


@app.post("/omnifocus/add_task")
def omnifocus_add_task(body: dict):
    """Přidá task do OmniFocus inboxu.

    Body:
      name    : str               — název tasku
      note    : str               — poznámka
      flagged : bool              — flag (default false)
      email_id: str               — UUID emailu (pro adresář příloh)
      files   : list[dict]        — [{filename, content_base64, size_bytes}]

    Přílohy:
      1) Dekódují se a ukládají na ~/Desktop/BrogiAssist/<email_id>/<filename>
      2) Do note se přidají `file://` linky (vždy, jako spolehlivý fallback)
      3) Pokus připojit jako fyzickou přílohu OF tasku — kaskáda C → B:
         - C: JXA `make new attachment` s detailním errorem
         - B: AppleScript fallback pokud JXA selže
      Response obsahuje `attach_method` ('jxa'/'applescript'/'links_only')
      a `attach_errors` pro diagnostiku.
    """
    name     = body.get("name", "") or ""
    note     = body.get("note", "") or ""
    flagged  = "true" if body.get("flagged", False) else "false"
    email_id = body.get("email_id", "") or ""
    files    = body.get("files") or []

    saved_paths: list[str] = []
    if files:
        eid = email_id or "no_email_id"
        saved_paths = _save_inbound_attachments(eid, files)

    if saved_paths:
        links = "\n".join(
            f"📎 file://{urllib.parse.quote(p, safe='/')}" for p in saved_paths
        )
        note = (note + "\n\n─────\nPřílohy:\n" + links) if note else ("Přílohy:\n" + links)

    name_js = json.dumps(name)
    note_js = json.dumps(note)
    # H2: vrátit task.id() — potřebné pro persistenci of_task_id
    # v email_messages → threading detekce při replies.
    create_script = f"""
const of2 = Application('OmniFocus');
const doc = of2.defaultDocument;
const task = of2.Task({{name: {name_js}, note: {note_js}, flagged: {flagged}}});
doc.inboxTasks.push(task);
JSON.stringify({{ok: true, name: {name_js}, task_id: task.id()}});
"""
    created_task_id = None
    try:
        result = run_jxa(create_script)
        if isinstance(result, dict):
            created_task_id = result.get("task_id")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Pokus o fyzickou přílohu (kaskáda C → B). file:// linky v note jsou už přidány.
    attach_method = "links_only"
    attach_errors: list[str] = []
    attached_count = 0
    if saved_paths:
        c = _jxa_attach_files(name, saved_paths)
        attached_count = c.get("attached", 0)
        attach_errors = c.get("errors", [])
        if c.get("ok"):
            attach_method = "jxa"
        else:
            # JXA selhal — zkusíme AppleScript pro nepřipojené
            unattached = saved_paths[attached_count:]
            b = _applescript_attach_files(name, unattached)
            if b.get("attached", 0) > 0:
                attached_count += b["attached"]
                attach_method = "applescript" if attached_count == len(saved_paths) else "mixed"
            attach_errors += [f"AS: {e}" for e in b.get("errors", [])]

    return {
        "ok": True,
        "name": name,
        "task_id": created_task_id,
        "attachments_saved": len(saved_paths),
        "attachments_attached": attached_count,
        "attach_method": attach_method,
        "attach_errors": attach_errors,
        "attachment_dir": os.path.join(ATTACHMENTS_BASE_DIR, email_id) if saved_paths else None,
    }


@app.get("/imessage/recent")
def imessage_recent(limit: int = 50):
    """Vrátí posledních N iMessage zpráv."""
    script = f"""
tell application "Messages"
    set msgs to messages of (first chat whose id is not missing value)
    -- fallback: přes DB
end tell
"""
    # iMessage přes AppleScript je omezený — lepší přes sqlite přímo
    import os, sqlite3
    db_path = os.path.expanduser("~/Library/Messages/chat.db")
    if not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail="chat.db nenalezeno")
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute("""
            SELECT
                m.guid,
                m.text,
                m.date/1000000000 + 978307200 as ts,
                m.is_from_me,
                h.id as contact
            FROM message m
            LEFT JOIN handle h ON m.handle_id = h.rowid
            ORDER BY m.date DESC
            LIMIT ?
        """, (limit,))
        rows = cur.fetchall()
        conn.close()
        messages = [
            {
                "guid": r[0],
                "text": r[1],
                "sent_at": datetime.fromtimestamp(r[2]).isoformat() if r[2] else None,
                "is_from_me": bool(r[3]),
                "contact": r[4]
            }
            for r in rows if r[1]
        ]
        return {"ok": True, "count": len(messages), "messages": messages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/notes/all")
def notes_all():
    """Vrátí všechny Apple Notes (id, name, body, folder, dates)."""
    script = """
const notes = Application('Notes');
const allNotes = notes.notes();
const result = [];
for (let i = 0; i < allNotes.length; i++) {
  const n = allNotes[i];
  try {
    let mod = null, created = null;
    try { mod     = n.modificationDate() ? n.modificationDate().toISOString() : null; } catch(e) {}
    try { created = n.creationDate()     ? n.creationDate().toISOString()     : null; } catch(e) {}
    result.push({
      id: n.id(), name: n.name() || '',
      body: (n.body() || '').substring(0, 2000),
      modified_at: mod, created_at: created
    });
  } catch(e) {}
}
JSON.stringify(result);
"""
    try:
        items = run_jxa(script)
        return {"ok": True, "count": len(items), "notes": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/reminders/all")
def reminders_all():
    """Vrátí nedokončené Reminders ze všech seznamů."""
    script = """
const rm = Application('Reminders');
const lists = rm.lists();
const result = [];
for (let i = 0; i < lists.length; i++) {
  const l = lists[i];
  const listName = l.name();
  const items = l.reminders();
  for (let j = 0; j < items.length; j++) {
    const r = items[j];
    try {
      const completed = r.completed();
      let due = null, remind = null, mod = null;
      try { due    = r.dueDate()            ? r.dueDate().toISOString()            : null; } catch(e) {}
      try { remind = r.remindMeDate()       ? r.remindMeDate().toISOString()       : null; } catch(e) {}
      try { mod    = r.modificationDate()   ? r.modificationDate().toISOString()   : null; } catch(e) {}
      result.push({id: r.id(), name: r.name(), list: listName, body: r.body() || null,
        flagged: r.flagged(), completed: completed,
        due_at: due, remind_at: remind, modified_at: mod});
    } catch(e) {}
  }
}
JSON.stringify(result);
"""
    try:
        items = run_jxa(script)
        return {"ok": True, "count": len(items), "reminders": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/contacts/all")
def contacts_all():
    """Vrátí kontakty + jejich skupiny přes JXA volání Contacts.app.

    Proč JXA a ne sqlite3 přímo?
    macOS launchd-spawned procesy nedědí Full Disk Access (na rozdíl od
    Terminal-spawned). Sqlite3 read DB v ~/Library/Application Support/
    AddressBook/ vyžaduje FDA → padá s PermissionError pro Bridge.
    JXA `Application('Contacts')` používá AppleEvents (= "Automation"
    permission), kterou Bridge má (stejná cesta funguje pro OmniFocus,
    Notes, Calendar, Reminders).

    Při prvním volání macOS vyhodí dialog "Apple Bridge requests Contacts
    access" — uživatel klikne Allow → funguje dál bez ptaní.
    """
    # JXA — skupiny + per-kontakt emails/phones (label+value).
    # Per-kontakt JXA call ~187 ms × 1180 kontaktů ≈ 230 s + overhead.
    # Timeout 600 s = ~2.6× rezerva.
    # Důvod načítat emails/phones zde (a ne nechávat na sqlite ingest):
    # launchd-spawned Bridge nemá Full Disk Access → sqlite read padá.
    script = r'''
const contacts = Application('Contacts');
contacts.includeStandardAdditions = false;

const groupMap = {};
const groups = contacts.groups();
for (let i = 0; i < groups.length; i++) {
    const g = groups[i];
    let gname;
    try { gname = g.name(); } catch (e) { continue; }
    if (!gname) continue;
    let memIds;
    try { memIds = g.people().map(p => p.id()); } catch (e) { continue; }
    for (let j = 0; j < memIds.length; j++) {
        const pid = memIds[j];
        if (!groupMap[pid]) groupMap[pid] = [];
        groupMap[pid].push(gname);
    }
}

function safeList(getter) {
    let arr = [];
    try { arr = getter(); } catch (e) { return []; }
    const out = [];
    for (let k = 0; k < arr.length; k++) {
        const item = arr[k];
        let lbl = null, val = null;
        try { lbl = item.label() || null; } catch (e) {}
        try { val = item.value() || null; } catch (e) {}
        if (val) out.push({label: lbl, value: val});
    }
    return out;
}

const result = [];
const people = contacts.people();
for (let i = 0; i < people.length; i++) {
    const p = people[i];
    let pid;
    try { pid = p.id(); } catch (e) { continue; }
    let first = null, last = null, org = null;
    try { first = p.firstName() || null; } catch (e) {}
    try { last = p.lastName() || null; } catch (e) {}
    try { org = p.organization() || null; } catch (e) {}
    const emails = safeList(() => p.emails());
    const phones = safeList(() => p.phones());
    result.push({
        id: pid,
        first: first,
        last: last,
        org: org,
        modified_at: null,
        emails: emails,
        phones: phones,
        groups: groupMap[pid] || [],
    });
}
JSON.stringify(result);
'''
    try:
        contacts_data = run_jxa(script, timeout=600)
        if not isinstance(contacts_data, list):
            return JSONResponse({
                "ok": False, "error": "jxa_unexpected_type",
                "message": f"JXA vrátilo {type(contacts_data).__name__}, čekal jsem list",
                "count": 0, "contacts": [],
            })
        return {"ok": True, "count": len(contacts_data), "contacts": contacts_data}
    except RuntimeError as e:
        msg = str(e)
        # "Not authorised to send Apple events" = Pavel ještě nedovolil
        if "authoris" in msg.lower() or "1743" in msg or "permission" in msg.lower():
            return JSONResponse({
                "ok": False, "error": "no_automation_permission",
                "message": "Bridge nemá AppleEvents permission pro Contacts. Při prvním volání macOS dialog → Allow. Pokud byl odmítnut: System Settings → Privacy & Security → Automation → Apple Bridge → zaškrtni Contacts.",
                "count": 0, "contacts": [],
            })
        raise HTTPException(status_code=500, detail=msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


### REMOVED 2026-05-04 (L2): /contacts/all_sqlite legacy fallback ###
# Důvod: launchd-spawned Bridge nedostával FDA (TCC limitations), endpoint
# vždy vracel error='no_fda'. JXA primary `/contacts/all` přes Contacts.app
# AppleEvents funguje (separátní permission) a poskytuje stejná data
# (id/first/last/org/modified_at/emails/phones/groups). Sqlite čtení nikdy
# v PROD provozu nepoužito → smazáno. Lessons sekce 36 (TCC FDA) zůstává.


def _dt_to_iso(dt) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    # date (all-day)
    return dt.isoformat()


@app.get("/calendar/events")
def calendar_events(days: int = 60):
    """Vrátí události z iCloud Calendar přes CalDAV API."""
    try:
        client = caldav.DAVClient(url=CALDAV_URL, username=CALDAV_USER, password=CALDAV_PASS)
        principal = client.principal()
        calendars = principal.calendars()
        now = datetime.now(tz=timezone.utc)
        future = now + timedelta(days=days)
        events = []
        for cal in calendars:
            try:
                cal_name = cal.get_display_name() or ""
                if cal_name in CALDAV_SKIP:
                    continue
                cal_events = cal.search(start=now, end=future, event=True, expand=True)
                for ev in cal_events:
                    try:
                        ical = ev.icalendar_instance
                        for component in ical.walk():
                            if component.name != "VEVENT":
                                continue
                            uid = str(component.get("UID", ""))
                            summary = str(component.get("SUMMARY", "(bez názvu)"))
                            location_raw = component.get("LOCATION")
                            location = str(location_raw) if location_raw else None
                            dtstart_prop = component.get("DTSTART")
                            dtend_prop = component.get("DTEND")
                            dtstart = dtstart_prop.dt if dtstart_prop else None
                            dtend = dtend_prop.dt if dtend_prop else None
                            if dtstart is None:
                                continue
                            all_day = isinstance(dtstart, date) and not isinstance(dtstart, datetime)
                            start_iso = _dt_to_iso(dtstart)
                            source_id = f"{uid}_{start_iso}" if uid else start_iso
                            events.append({
                                "id": source_id,
                                "summary": summary,
                                "calendar": cal_name,
                                "start_at": start_iso,
                                "end_at": _dt_to_iso(dtend),
                                "all_day": all_day,
                                "location": location,
                            })
                    except Exception:
                        pass
            except Exception:
                pass
        events.sort(key=lambda e: e["start_at"] or "")
        return {"ok": True, "count": len(events), "events": events}
    except Exception as e:
        return {"ok": False, "error": str(e), "events": []}


@app.post("/calendar/add")
def calendar_add(body: dict):
    """Přidá událost do iCloud Calendar přes CalDAV. Hledá kalendář dle jména, fallback na první."""
    import uuid
    from icalendar import Calendar as ICal, Event as ICalEvent
    from datetime import date as date_type

    name      = body.get("name", "(bez názvu)")
    notes     = body.get("notes", "")
    cal_name  = body.get("calendar", "PAJA")
    start_iso = body.get("start_iso")   # ISO datetime string nebo None
    end_iso   = body.get("end_iso")
    all_day   = body.get("all_day", False)

    try:
        # Parsuj datumy
        if start_iso:
            if "T" in str(start_iso):
                start_dt = datetime.fromisoformat(str(start_iso).replace("Z", "+00:00"))
                end_dt   = datetime.fromisoformat(str(end_iso).replace("Z", "+00:00")) if end_iso else start_dt + timedelta(hours=1)
            else:
                from datetime import date as date_type
                start_dt = date_type.fromisoformat(str(start_iso))
                end_dt   = date_type.fromisoformat(str(end_iso)) if end_iso else date_type(start_dt.year, start_dt.month, start_dt.day + 1)
                all_day  = True
        else:
            start_dt = date.today()
            end_dt   = date_type(start_dt.year, start_dt.month, start_dt.day)
            all_day  = True

        # Sestav iCal
        cal = ICal()
        cal.add("prodid", "-//BrogiASIST//EN")
        cal.add("version", "2.0")
        ev = ICalEvent()
        ev.add("uid", str(uuid.uuid4()) + "@brogiasist")
        ev.add("summary", name)
        if notes:
            ev.add("description", notes)
        ev.add("dtstart", start_dt)
        ev.add("dtend", end_dt)
        ev.add("dtstamp", datetime.now(tz=timezone.utc))
        cal.add_component(ev)
        ical_bytes = cal.to_ical()

        # Najdi cílový kalendář
        client = caldav.DAVClient(url=CALDAV_URL, username=CALDAV_USER, password=CALDAV_PASS)
        principal = client.principal()
        calendars = principal.calendars()
        target = None
        for c in calendars:
            if (c.get_display_name() or "") == cal_name:
                target = c
                break
        if target is None and calendars:
            target = calendars[0]
        if target is None:
            raise HTTPException(status_code=500, detail="Žádný kalendář nenalezen")

        target.save_event(ical_bytes)
        # M2 undo: vrátit UID — undo pak smaže event přes DELETE /calendar/{uid}
        event_uid = str(ev.get("uid"))
        return {"ok": True, "calendar": cal_name, "name": name, "id": event_uid}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/calendar/{event_uid}")
def calendar_delete(event_uid: str):
    """M2 undo: smaže event z iCloud Calendar přes CalDAV podle UID
    (vrácený z /calendar/add). Hledá ve všech kalendářích — UID je globálně unikátní."""
    try:
        client = caldav.DAVClient(url=CALDAV_URL, username=CALDAV_USER, password=CALDAV_PASS)
        principal = client.principal()
        for c in principal.calendars():
            try:
                ev = c.event_by_uid(event_uid)
                ev.delete()
                return {"ok": True, "deleted": event_uid, "calendar": c.get_display_name()}
            except Exception:
                continue
        raise HTTPException(status_code=404, detail=f"Event UID '{event_uid}' nenalezen v žádném kalendáři")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/omnifocus/task/{task_id}")
def omnifocus_task_delete(task_id: str):
    """M2 undo: smaže OmniFocus task podle id (vrácený z /omnifocus/add_task).
    Pokud delete selže (TCC, JXA limitation), fallback na markComplete."""
    tid_js = json.dumps(task_id)
    script = f"""
const of = Application('OmniFocus');
const doc = of.defaultDocument;
try {{
  const tasks = doc.flattenedTasks.whose({{id: {tid_js}}})();
  if (tasks.length === 0) {{
    JSON.stringify({{ok: false, error: 'task_not_found'}});
  }} else {{
    try {{
      of.delete(tasks[0]);
      JSON.stringify({{ok: true, deleted: {tid_js}, method: 'delete'}});
    }} catch(de) {{
      tasks[0].markComplete();
      JSON.stringify({{ok: true, deleted: {tid_js}, method: 'markComplete', delete_error: de.toString()}});
    }}
  }}
}} catch(e) {{
  JSON.stringify({{ok: false, error: e.toString()}});
}}
"""
    try:
        result = run_jxa(script)
        if isinstance(result, dict) and not result.get("ok"):
            raise HTTPException(status_code=404, detail=result.get("error", "OF task delete failed"))
        return result if isinstance(result, dict) else {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9100)
