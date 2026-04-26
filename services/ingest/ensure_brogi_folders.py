"""
BrogiASIST — Ensure BrogiASIST/ IMAP folder hierarchy
======================================================

Účel:
  Idempotentní vytvoření kompletní hierarchie `BrogiASIST/` (a subfolderů
  pro všechny typy a akce) na všech IMAP účtech v `ACCOUNTS`. Bez tohoto
  skriptu `imap_actions.move_to_brogi_folder()` selhával tiše na účtech
  kde subfoldery neexistovaly (BUG-004 + BUG-005, viz docs/BUGS.md).

Použití:
  docker cp services/ingest/ensure_brogi_folders.py brogi_scheduler:/app/
  docker exec brogi_scheduler python /app/ensure_brogi_folders.py

  # Pro nový IMAP účet — stačí ho přidat do ACCOUNTS a znovu spustit.
  # Skript je idempotentní (existující složky preskočí).

Per-host syntaxe (lesson #1):
  - Forpsi (imap.forpsi.com), Synology (mail.dxpsolutions.cz):
      prefix `INBOX.`, separator `.`  →  INBOX.BrogiASIST.HOTOVO
  - Gmail, iCloud, Seznam: bez prefixu, separator `/`  →  BrogiASIST/HOTOVO

Dlouhodobé řešení BUG-004:
  Tento skript je „mitigation" — opravdové řešení je per-host folder mapping
  v `imap_actions.move_to_brogi_folder()` + pre-flight check existence cíle.
  Až bude BUG-004 opraven v `imap_actions`, tento skript se může používat
  jen pro bootstrap nového účtu.
"""
import sys

sys.path.insert(0, "/app")
from ingest_email import ACCOUNTS, connect

SUBFOLDERS = [
    "HOTOVO", "CEKA",
    "NOTIFIKACE", "NEWSLETTER", "ESHOP", "POZVANKA",
    "FAKTURA", "POTVRZENI", "NABIDKA", "TODO", "INFO",
]

# Hosts kde je struktura `INBOX.foo.bar` místo `foo/bar`
DOTTED_HOSTS = {"imap.forpsi.com", "mail.dxpsolutions.cz"}


def brogi_path(host: str, sub: str) -> str:
    if host in DOTTED_HOSTS:
        return f"INBOX.BrogiASIST.{sub}"
    return f"BrogiASIST/{sub}"


def list_folders(m) -> set:
    typ, raw = m.list()
    out = set()
    for line in raw or []:
        s = line.decode() if isinstance(line, bytes) else line
        try:
            parts = s.rsplit(" ", 1)
            name = parts[-1].strip().strip('"')
            out.add(name)
        except Exception:
            pass
    return out


def main():
    total_created = 0
    total_existing = 0
    total_failed = 0
    for acc in ACCOUNTS:
        name = acc["name"]
        host = acc.get("host")
        if not host:
            print(f"  {name:40s} SKIP (no host in env)")
            continue
        print(f"\n=== {name}  ({host}) ===")
        try:
            m = connect(acc)
        except Exception as e:
            print(f"  CONNECT ERROR: {e}")
            total_failed += 1
            continue

        existing = list_folders(m)
        parent = "INBOX.BrogiASIST" if host in DOTTED_HOSTS else "BrogiASIST"

        # Parent
        if parent in existing:
            print(f"  parent {parent}: exists")
            total_existing += 1
        else:
            res = m.create(parent)
            ok = res[0] == "OK"
            print(f"  CREATE parent {parent}: {res[0]}")
            if ok:
                total_created += 1
            else:
                total_failed += 1

        # Subfoldery
        for sub in SUBFOLDERS:
            path = brogi_path(host, sub)
            if path in existing:
                print(f"  {path}: exists")
                total_existing += 1
            else:
                try:
                    res = m.create(path)
                    ok = res[0] == "OK"
                    print(f"  CREATE {path}: {res[0]}")
                    if ok:
                        total_created += 1
                    else:
                        total_failed += 1
                except Exception as e:
                    print(f"  CREATE {path}: ERROR {e}")
                    total_failed += 1
        m.logout()

    print(f"\n=== Souhrn: vytvořeno={total_created}, existovalo={total_existing}, failed={total_failed} ===")


if __name__ == "__main__":
    main()
