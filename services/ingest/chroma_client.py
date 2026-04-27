"""
BrogiASIST — ChromaDB klient (přímé HTTP volání přes httpx, bez chromadb balíčku)
Embeddingy přes Ollama nomic-embed-text.
"""
import os
import logging
import httpx

log = logging.getLogger(__name__)

OLLAMA_URL  = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
CHROMA_HOST = os.getenv("CHROMA_HOST", "brogi_chromadb")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
EMBED_MODEL = "nomic-embed-text"

TENANT   = "default_tenant"
DATABASE = "default_database"

AUTO_THRESHOLD_COUNT = 3
AUTO_THRESHOLD_DIST  = 0.15  # cosine distance (nižší = podobnější)


def _base() -> str:
    return f"http://{CHROMA_HOST}:{CHROMA_PORT}/api/v2/tenants/{TENANT}/databases/{DATABASE}"


def _embed(text: str) -> list[float]:
    r = httpx.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": EMBED_MODEL, "input": text},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["embeddings"][0]


def _doc_text(from_addr: str, subject: str, body: str) -> str:
    return f"{from_addr or ''} {subject or ''} {(body or '')[:400]}".strip()


def _get_or_create_collection(name: str) -> str:
    """Vrátí ID kolekce, vytvoří pokud neexistuje."""
    url = f"{_base()}/collections"
    r = httpx.post(
        url,
        json={"name": name, "metadata": {"hnsw:space": "cosine"}},
        timeout=10,
    )
    if r.status_code in (200, 201):
        return r.json()["id"]
    if r.status_code in (409, 422):
        # Kolekce již existuje — načti ji
        r2 = httpx.get(f"{url}/{name}", timeout=10)
        r2.raise_for_status()
        return r2.json()["id"]
    r.raise_for_status()


def _count(col_id: str) -> int:
    r = httpx.get(f"{_base()}/collections/{col_id}/count", timeout=10)
    r.raise_for_status()
    return int(r.json())


def _upsert(col_id: str, ids, embeddings, documents, metadatas):
    r = httpx.post(
        f"{_base()}/collections/{col_id}/upsert",
        json={"ids": ids, "embeddings": embeddings, "documents": documents, "metadatas": metadatas},
        timeout=30,
    )
    r.raise_for_status()


def _query(col_id: str, query_embeddings, n_results, include) -> dict:
    r = httpx.post(
        f"{_base()}/collections/{col_id}/query",
        json={"query_embeddings": query_embeddings, "n_results": n_results, "include": include},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def store_email_action(
    email_id: str,
    from_addr: str,
    subject: str,
    body: str,
    action: str,
    typ: str = "",
    firma: str = "",
    mailbox: str = "",
    ai_confidence: float | None = None,
    task_status: str = "",
    timestamp: str = "",
    human_corrected: bool = False,
):
    """
    Uloží email + akci do ChromaDB po provedení akce.

    Metadata umožňují zpětnou analýzu: kdo (mailbox, from_addr), kdy (timestamp),
    co (action, task_status), proč (ai_confidence, typ, firma),
    a zda Pavel přepsal AI klasifikaci (human_corrected).
    """
    from datetime import datetime, timezone
    try:
        col_id = _get_or_create_collection("email_actions")
        text = _doc_text(from_addr, subject, body)
        embedding = _embed(text)
        meta = {
            "action": action,
            "typ": typ or "",
            "firma": firma or "",
            "mailbox": mailbox or "",
            "from_addr": from_addr or "",
            "subject": (subject or "")[:200],
            "task_status": task_status or "",
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
            "human_corrected": bool(human_corrected),
        }
        if ai_confidence is not None:
            meta["ai_confidence"] = float(ai_confidence)
        _upsert(col_id, [str(email_id)], [embedding], [text], [meta])
        log.info(f"chroma store: email_id={email_id} action={action} mailbox={mailbox} typ={typ}")
    except Exception as e:
        log.error(f"chroma store_email_action: {e}")


def find_repeat_action(from_addr: str, subject: str, body: str, n_results: int = 10) -> str | None:
    """Backward-compat wrapper — vrací jen action (None pokud nematch)."""
    res = find_repeat_action_with_score(from_addr, subject, body, n_results)
    return res[0] if res else None


def find_repeat_action_with_score(
    from_addr: str, subject: str, body: str, n_results: int = 10
) -> tuple[str, int, int] | None:
    """
    Hledá podobné emaily v ChromaDB.
    Vrátí (action, match_count, total_neighbors) pokud >= AUTO_THRESHOLD_COUNT
    podobných emailů (cosine ≤ AUTO_THRESHOLD_DIST) mělo stejnou akci, jinak None.

    `match_count` = kolik z `total_neighbors` mělo zvolenou action — slouží
    pro výpočet „confidence" (match_count / total_neighbors).
    """
    try:
        col_id = _get_or_create_collection("email_actions")
        count = _count(col_id)
        if count < AUTO_THRESHOLD_COUNT:
            return None

        text = _doc_text(from_addr, subject, body)
        embedding = _embed(text)
        results = _query(col_id, [embedding], min(n_results, count), ["metadatas", "distances"])

        if not results.get("ids") or not results["ids"][0]:
            return None

        action_counts: dict[str, int] = {}
        total_close = 0
        for meta, dist in zip(results["metadatas"][0], results["distances"][0]):
            if dist <= AUTO_THRESHOLD_DIST:
                total_close += 1
                a = meta.get("action", "")
                if a:
                    action_counts[a] = action_counts.get(a, 0) + 1

        for action, cnt in action_counts.items():
            if cnt >= AUTO_THRESHOLD_COUNT:
                log.info(f"chroma pattern: action={action} count={cnt}/{total_close}")
                return (action, cnt, total_close)

    except Exception as e:
        log.error(f"chroma find_repeat_action: {e}")
    return None
