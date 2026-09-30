"""Local, reproducible entity index over the benchmark RDF graph."""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import RDF


KG_PREFIX = "https://wealth.example.org/kg/"
WM_PREFIX = "https://wealth.example.org/ontology/"
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*|[0-9]+")
EXACT_ID_RE = re.compile(
    r"\b(?:INV[- ]?\d{1,6}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
    re.I,
)
STOPWORDS = {
    "what", "which", "who", "where", "when", "how", "many", "much", "does", "did",
    "are", "was", "were", "for", "the", "and", "with", "from", "into", "that",
    "this", "their", "each", "per", "all", "show", "list", "give", "using", "across",
    "between", "related", "tables", "table", "investor", "investors", "value",
}


def local_name(uri: str) -> str:
    return uri.rsplit("/", 1)[-1].rsplit("#", 1)[-1]


def normalize_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def word_tokens(value: str) -> set[str]:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    value = value.replace("_", " ").replace("-", " ")
    return {token.lower() for token in TOKEN_RE.findall(value)}


def search_words(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return value.replace("_", " ").replace("-", " ")


def connect(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def build_index(graph_path: Path, index_path: Path) -> dict[str, int]:
    """Parse the RDF once; never ingest benchmark questions or answers."""
    graph_path = graph_path.resolve()
    index_path = index_path.resolve()
    if not graph_path.exists():
        raise FileNotFoundError(graph_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = index_path.with_suffix(index_path.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    graph = Graph()
    graph.parse(graph_path, format="turtle")
    conn = connect(temporary)
    try:
        conn.executescript(
            """
            PRAGMA journal_mode=OFF;
            PRAGMA synchronous=OFF;
            CREATE TABLE facts(subject TEXT NOT NULL, predicate TEXT NOT NULL,
                               object TEXT NOT NULL, is_uri INTEGER NOT NULL);
            CREATE TABLE nodes(uri TEXT PRIMARY KEY, search_text TEXT NOT NULL);
            CREATE TABLE ids(id TEXT NOT NULL, uri TEXT NOT NULL,
                             PRIMARY KEY(id, uri));
            CREATE VIRTUAL TABLE node_search USING fts5(uri UNINDEXED, search_text);
            CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """
        )
        search_parts: dict[str, list[str]] = defaultdict(list)
        identifier_rows: set[tuple[str, str]] = set()
        fact_batch: list[tuple[str, str, str, int]] = []
        fact_count = 0
        for subject, predicate, obj in graph:
            if not isinstance(subject, URIRef) or not str(subject).startswith(KG_PREFIX):
                continue
            s, p, o = str(subject), str(predicate), str(obj)
            is_uri = isinstance(obj, URIRef)
            fact_batch.append((s, p, o, int(is_uri)))
            fact_count += 1
            if len(fact_batch) >= 10000:
                conn.executemany("INSERT INTO facts VALUES (?,?,?,?)", fact_batch)
                fact_batch.clear()
            parts = search_parts[s]
            if not parts:
                parts.append(search_words(local_name(s)))
                identifier_rows.add((normalize_id(local_name(s)), s))
            if predicate == RDF.type:
                parts.append(search_words(local_name(o)))
            elif not is_uri:
                parts.append(search_words(local_name(p)))
                parts.append(o[:160])
                if local_name(p).lower().endswith("id") and len(o) <= 100:
                    identifier_rows.add((normalize_id(o), s))
        if fact_batch:
            conn.executemany("INSERT INTO facts VALUES (?,?,?,?)", fact_batch)
        node_rows = [(uri, " ".join(sorted(set(parts)))[:3000]) for uri, parts in sorted(search_parts.items())]
        conn.executemany("INSERT INTO nodes VALUES (?,?)", node_rows)
        conn.executemany("INSERT INTO node_search(uri,search_text) VALUES (?,?)", node_rows)
        conn.executemany("INSERT INTO ids VALUES (?,?)", sorted(identifier_rows))
        conn.executescript(
            """
            CREATE INDEX facts_subject ON facts(subject);
            CREATE INDEX facts_object_uri ON facts(object) WHERE is_uri=1;
            CREATE INDEX ids_id ON ids(id);
            """
        )
        conn.executemany(
            "INSERT INTO meta VALUES (?,?)",
            [("graph_path", str(graph_path)), ("graph_size", str(graph_path.stat().st_size)),
             ("graph_mtime_ns", str(graph_path.stat().st_mtime_ns))],
        )
        conn.commit()
        counts = {"nodes": len(node_rows), "facts": fact_count, "ids": len(identifier_rows)}
    except Exception:
        conn.close()
        temporary.unlink(missing_ok=True)
        raise
    conn.close()
    temporary.replace(index_path)
    return counts


def verify_index(conn: sqlite3.Connection, graph_path: Path) -> None:
    meta = dict(conn.execute("SELECT key,value FROM meta").fetchall())
    graph_path = graph_path.resolve()
    if (
        meta.get("graph_path") != str(graph_path)
        or meta.get("graph_size") != str(graph_path.stat().st_size)
        or meta.get("graph_mtime_ns") != str(graph_path.stat().st_mtime_ns)
    ):
        raise RuntimeError("Graph index is stale. Rebuild it with build-index.")


def extract_ids(question: str) -> list[str]:
    return list(dict.fromkeys(normalize_id(match.group()) for match in EXACT_ID_RE.finditer(question)))


def search_seeds(conn: sqlite3.Connection, question: str, max_seeds: int = 3) -> tuple[list[str], list[str]]:
    ids = extract_ids(question)
    seeds: list[str] = []
    for identifier in ids:
        rows = conn.execute("SELECT uri FROM ids WHERE id=? ORDER BY uri", (identifier,))
        seeds.extend(row[0] for row in rows)
    seeds = list(dict.fromkeys(seeds))
    if seeds:
        # Prefer the entity whose own URI carries the ID over its many child records.
        direct = [uri for uri in seeds if any(normalize_id(local_name(uri)) == i for i in ids)]
        if direct:
            seeds = direct
        seeds.sort()
        return seeds[:max_seeds], ids
    terms = []
    for token in TOKEN_RE.findall(search_words(question)):
        lowered = token.lower()
        if len(lowered) >= 3 and lowered not in STOPWORDS and lowered not in terms:
            terms.append(lowered)
    if not terms:
        return [], ids
    # Quoted FTS terms avoid treating user punctuation as an FTS operator.
    fts_query = " OR ".join('"' + term.replace('"', '') + '"' for term in terms[:12])
    rows = conn.execute(
        "SELECT uri FROM node_search WHERE node_search MATCH ? ORDER BY bm25(node_search), uri LIMIT ?",
        (fts_query, max_seeds),
    )
    return [row[0] for row in rows], ids


def _facts(conn: sqlite3.Connection, uri: str) -> list[sqlite3.Row]:
    return list(conn.execute(
        "SELECT subject,predicate,object,is_uri FROM facts WHERE subject=? ORDER BY predicate,object",
        (uri,),
    ))


def retrieve(
    conn: sqlite3.Connection,
    question: str,
    *,
    max_seeds: int = 3,
    max_neighbors: int = 5000,
    max_triples: int = 5000,
    max_chars: int = 320000,
    max_hops: int = 2,
    exact_id_max_neighbors: int = 64,
    exact_id_max_triples: int = 1200,
    exact_id_max_chars: int = 100000,
) -> dict:
    seeds, ids = search_seeds(conn, question, max_seeds)
    if ids:
        max_neighbors = min(max_neighbors, exact_id_max_neighbors)
        max_triples = min(max_triples, exact_id_max_triples)
        max_chars = min(max_chars, exact_id_max_chars)
    applied_limits = {
        "max_seeds": max_seeds,
        "max_neighbors": max_neighbors,
        "max_triples": max_triples,
        "max_chars": max_chars,
        "max_hops": max_hops,
        "exact_id_policy_applied": bool(ids),
    }
    if not seeds:
        return {"seeds": [], "matched_ids": ids, "entities": [], "evidence": [],
                "truncated": False, "context": "", "applied_limits": applied_limits}
    question_tokens = word_tokens(question) - STOPWORDS
    selected = list(seeds)
    seen = set(selected)
    frontier = list(seeds)
    truncated = False
    for _ in range(max_hops):
        candidates: dict[str, float] = {}
        for uri in frontier:
            for row in _facts(conn, uri):
                if row["is_uri"] and row["object"].startswith(KG_PREFIX):
                    target = row["object"]
                    if target not in seen:
                        candidates[target] = max(candidates.get(target, 0), _edge_score(row, question_tokens))
            for row in conn.execute(
                "SELECT subject,predicate FROM facts WHERE object=? AND is_uri=1", (uri,)
            ):
                source = row["subject"]
                if source not in seen:
                    candidates[source] = max(candidates.get(source, 0), _edge_score(row, question_tokens))
        ranked = sorted(candidates, key=lambda uri: (-candidates[uri], uri))
        capacity = max_neighbors - (len(selected) - len(seeds))
        frontier = ranked[:capacity]
        selected.extend(frontier)
        seen.update(frontier)
        truncated |= len(ranked) > capacity
        if not frontier or capacity <= 0:
            break
    lines: list[str] = []
    evidence: list[dict] = []
    included_triples = 0
    included_chars = 0
    for uri in selected:
        facts = _facts(conn, uri)
        # Literal facts first; URI edges remain explicit and graph grounded.
        facts.sort(key=lambda row: (row["is_uri"], local_name(row["predicate"]), row["object"]))
        remaining = max_triples - included_triples
        if remaining <= 0:
            truncated = True
            break
        if len(facts) > remaining:
            facts = facts[:remaining]
            truncated = True
        rendered = [f"ENTITY {uri}"]
        for row in facts:
            value = row["object"] if row["is_uri"] else repr(row["object"])
            rendered.append(f"  {local_name(row['predicate'])}: {value}")
        block = "\n".join(rendered) + "\n"
        separator_chars = 1 if lines else 0
        if included_chars + separator_chars + len(block) > max_chars:
            truncated = True
            break
        lines.append(block)
        evidence.append({"uri": uri, "triples": len(facts), "text": block})
        included_triples += len(facts)
        included_chars += separator_chars + len(block)
    return {
        "seeds": seeds,
        "matched_ids": ids,
        "entities": [item["uri"] for item in evidence],
        "evidence": evidence,
        "truncated": truncated,
        "context": "\n".join(lines),
        "applied_limits": applied_limits,
    }


def _edge_score(row: sqlite3.Row, question_tokens: set[str]) -> float:
    predicate_tokens = word_tokens(local_name(row["predicate"]))
    uri = row["object"] if "object" in row.keys() else row["subject"]
    uri_tokens = word_tokens(local_name(uri))
    return 1 + 3 * len(predicate_tokens & question_tokens) + len(uri_tokens & question_tokens)
