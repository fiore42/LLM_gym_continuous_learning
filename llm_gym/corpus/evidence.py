"""Build and query a deterministic, provenance-preserving evidence index."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Protocol


INDEX_VERSION = 2
TEXT_SUFFIXES = {".srt", ".vtt", ".ttml", ".ass", ".txt", ".md", ".csv"}
DOCUMENT_SUFFIXES = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}
IGNORED_DIRS = {"audio", "video", "logs", "temporary-audio", ".git", "media"}
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does",
    "for", "from", "how", "in", "is", "it", "of", "on", "or", "that", "the",
    "this", "to", "what", "when", "where", "which", "who", "why", "with",
}
_SRT_BLOCK = re.compile(
    r"(?ms)^(?:\s*\d+\s*\n)?\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})\s+-->\s+"
    r"(\d{2}:\d{2}:\d{2}[,.]\d{3}).*?\n(.*?)(?=\n\s*\n|\Z)"
)


def index_signature(index_path: str | Path) -> str:
    """Return a cheap identity for the current derived index contents."""
    path = Path(index_path)
    try:
        stat = path.stat()
    except OSError:
        return "missing"
    return f"{INDEX_VERSION}:{stat.st_size}:{stat.st_mtime_ns}"


@dataclass(frozen=True)
class EvidenceRecord:
    platform: str
    source_key: str
    content_id: str
    canonical_url: str
    published_at: str | None
    title: str | None
    author: str | None
    kind: str
    text: str
    locator: str | None
    artifact_path: str
    extraction_status: str = "EXTRACTED"

    @property
    def evidence_id(self) -> str:
        value = "\x1f".join((self.platform, self.source_key, self.content_id, self.kind, self.artifact_path))
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


class EvidenceAdapter(Protocol):
    """Contract implemented by each source-specific evidence collector."""

    name: str

    def collect(self, source_root: Path) -> tuple[list[EvidenceRecord], list[str]]:
        ...


class _YouTubeEvidenceAdapter:
    name = "youtube"

    def collect(self, source_root: Path) -> tuple[list[EvidenceRecord], list[str]]:
        return _youtube_records(source_root)


class _XEvidenceAdapter:
    name = "x"

    def collect(self, source_root: Path) -> tuple[list[EvidenceRecord], list[str]]:
        return _post_records(source_root)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _chunks(record: EvidenceRecord) -> list[tuple[str | None, str]]:
    """Split text without dropping content; SRT chunks retain time locators."""
    if Path(record.artifact_path).suffix.lower() not in {".srt", ".vtt", ".ttml", ".ass"}:
        return [(record.locator, record.text)]
    matches = _SRT_BLOCK.findall(record.text)
    if not matches:
        return [(record.locator, record.text)]
    chunks: list[tuple[str | None, str]] = []
    for start, end, body in matches:
        cleaned = " ".join(line.strip() for line in body.splitlines() if line.strip())
        if cleaned:
            chunks.append((f"{start.replace(',', '.')}–{end.replace(',', '.')}", cleaned))
    return chunks or [(record.locator, record.text)]


def _post_records(source_root: Path) -> tuple[list[EvidenceRecord], list[str]]:
    records: list[EvidenceRecord] = []
    warnings: list[str] = []
    for post_path in sorted(source_root.glob("x/*/posts/*/post.json")):
        handle = post_path.relative_to(source_root).parts[1]
        try:
            post = json.loads(_read_text(post_path))
        except (OSError, json.JSONDecodeError) as exc:
            warnings.append(f"UNREADABLE_POST:{post_path}:{exc}")
            continue
        post_id = str(post.get("id") or post_path.parent.name.split("_", 1)[-1])
        url = f"https://x.com/{handle}/status/{post_id}"
        records.append(EvidenceRecord(
            platform="x", source_key=handle, content_id=post_id,
            canonical_url=url, published_at=post.get("created_at"),
            title=None, author=handle, kind="post", text=str(post.get("text") or ""),
            locator=None, artifact_path=str(post_path),
        ))
        for artifact in sorted(post_path.parent.rglob("*")):
            if not artifact.is_file() or artifact.name in {"post.json", ".complete"}:
                continue
            if any(part in IGNORED_DIRS for part in artifact.relative_to(source_root).parts):
                continue
            if artifact.suffix.lower() in DOCUMENT_SUFFIXES:
                warnings.append(f"UNEXTRACTED_DOCUMENT:{artifact}")
                continue
            if artifact.suffix.lower() not in TEXT_SUFFIXES or artifact.name.endswith(".json"):
                continue
            try:
                text = _read_text(artifact)
            except OSError as exc:
                warnings.append(f"UNREADABLE_ARTIFACT:{artifact}:{exc}")
                continue
            if text:
                records.append(EvidenceRecord(
                    platform="x", source_key=handle, content_id=post_id,
                    canonical_url=url, published_at=post.get("created_at"),
                    title=None, author=handle, kind="attachment_text", text=text,
                    locator=None, artifact_path=str(artifact),
                ))
    return records, warnings


def _youtube_records(source_root: Path) -> tuple[list[EvidenceRecord], list[str]]:
    records: list[EvidenceRecord] = []
    warnings: list[str] = []
    for state_path in sorted(source_root.glob("youtube/*/ingestion-state.sqlite3")):
        source = state_path.relative_to(source_root).parts[1]
        connection = sqlite3.connect(state_path)
        try:
            rows = connection.execute(
                "SELECT video_id, canonical_url, title, published_at, status, transcript_path FROM videos"
            ).fetchall()
        finally:
            connection.close()
        for video_id, url, title, published_at, status, transcript_path in rows:
            if not transcript_path:
                continue
            path = Path(str(transcript_path))
            if not path.is_absolute():
                path = Path.cwd() / path
            if not path.is_file():
                warnings.append(f"MISSING_TRANSCRIPT:{video_id}:{transcript_path}:{status}")
                continue
            try:
                text = _read_text(path)
            except OSError as exc:
                warnings.append(f"UNREADABLE_TRANSCRIPT:{path}:{exc}")
                continue
            if not text:
                warnings.append(f"EMPTY_TRANSCRIPT:{video_id}:{path}")
                continue
            records.append(EvidenceRecord(
                platform="youtube", source_key=source, content_id=str(video_id),
                canonical_url=str(url), published_at=published_at, title=title,
                author=source, kind="transcript", text=text, locator="transcript",
                artifact_path=str(path),
            ))
    return records, warnings


def collect_records(source_root: str | Path = "source") -> tuple[list[EvidenceRecord], list[str]]:
    root = Path(source_root)
    records: list[EvidenceRecord] = []
    warnings: list[str] = []
    for adapter in (_YouTubeEvidenceAdapter(), _XEvidenceAdapter()):
        adapter_records, adapter_warnings = adapter.collect(root)
        records.extend(adapter_records)
        warnings.extend(adapter_warnings)
    return records, warnings


def _connect(path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS evidence_items (
            evidence_id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            source_key TEXT NOT NULL,
            content_id TEXT NOT NULL,
            canonical_url TEXT NOT NULL,
            published_at TEXT,
            title TEXT,
            author TEXT,
            kind TEXT NOT NULL,
            text TEXT NOT NULL,
            locator TEXT,
            artifact_path TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            extraction_status TEXT NOT NULL,
            index_version INTEGER NOT NULL,
            indexed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS evidence_chunks (
            chunk_id TEXT PRIMARY KEY,
            evidence_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            locator TEXT,
            text TEXT NOT NULL,
            FOREIGN KEY (evidence_id) REFERENCES evidence_items(evidence_id)
        );
        CREATE INDEX IF NOT EXISTS idx_evidence_chunks_evidence
            ON evidence_chunks(evidence_id, chunk_index);
        """
    )
    # FTS tables are derived data. Rebuild them when an older index used the
    # default tokenizer, so morphology is handled consistently offline.
    porter = "tokenize='porter unicode61 remove_diacritics 2'"
    fts_definitions = {
        "evidence_fts": f"CREATE VIRTUAL TABLE evidence_fts USING fts5(evidence_id UNINDEXED, text, title, author, {porter})",
        "evidence_chunk_fts": f"CREATE VIRTUAL TABLE evidence_chunk_fts USING fts5(chunk_id UNINDEXED, evidence_id UNINDEXED, text, {porter})",
    }
    rebuild = False
    for table, create_sql in fts_definitions.items():
        existing = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
        if existing is None or porter not in str(existing[0]):
            connection.execute(f"DROP TABLE IF EXISTS {table}")
            connection.execute(create_sql)
            rebuild = True
    if rebuild:
        connection.execute(
            "INSERT INTO evidence_fts(evidence_id, text, title, author) "
            "SELECT evidence_id, text, COALESCE(title, ''), COALESCE(author, '') FROM evidence_items"
        )
        connection.execute(
            "INSERT INTO evidence_chunk_fts(chunk_id, evidence_id, text) "
            "SELECT chunk_id, evidence_id, text FROM evidence_chunks"
        )
        connection.commit()
    return connection


def build_index(records: Iterable[EvidenceRecord], index_path: str | Path = "data/evidence.sqlite3") -> dict[str, int]:
    destination = Path(index_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    connection = _connect(destination)
    seen: set[str] = set()
    inserted = updated = reused = 0
    chunk_count = 0
    now = datetime.now(timezone.utc).isoformat()
    try:
        for record in records:
            seen.add(record.evidence_id)
            existing = connection.execute(
                "SELECT content_hash, index_version FROM evidence_items WHERE evidence_id = ?",
                (record.evidence_id,),
            ).fetchone()
            existing_chunks = connection.execute(
                "SELECT COUNT(*) FROM evidence_chunks WHERE evidence_id = ?", (record.evidence_id,)
            ).fetchone()[0]
            if existing and existing == (record.content_hash, INDEX_VERSION) and existing_chunks:
                reused += 1
                chunk_count += int(existing_chunks)
                continue
            connection.execute("DELETE FROM evidence_fts WHERE evidence_id = ?", (record.evidence_id,))
            connection.execute("DELETE FROM evidence_chunk_fts WHERE evidence_id = ?", (record.evidence_id,))
            connection.execute("DELETE FROM evidence_chunks WHERE evidence_id = ?", (record.evidence_id,))
            connection.execute(
                """INSERT INTO evidence_fts(evidence_id, text, title, author) VALUES (?, ?, ?, ?)""",
                (record.evidence_id, record.text, record.title or "", record.author or ""),
            )
            connection.execute(
                """INSERT INTO evidence_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(evidence_id) DO UPDATE SET
                     platform=excluded.platform, source_key=excluded.source_key,
                     content_id=excluded.content_id, canonical_url=excluded.canonical_url,
                     published_at=excluded.published_at, title=excluded.title,
                     author=excluded.author, kind=excluded.kind, text=excluded.text,
                     locator=excluded.locator, artifact_path=excluded.artifact_path,
                     content_hash=excluded.content_hash, extraction_status=excluded.extraction_status,
                     index_version=excluded.index_version, indexed_at=excluded.indexed_at""",
                (record.evidence_id, record.platform, record.source_key, record.content_id,
                 record.canonical_url, record.published_at, record.title, record.author,
                 record.kind, record.text, record.locator, record.artifact_path,
                 record.content_hash, record.extraction_status, INDEX_VERSION, now),
            )
            for chunk_index, (locator, text) in enumerate(_chunks(record)):
                chunk_id = hashlib.sha256(
                    f"{record.evidence_id}\x1f{chunk_index}\x1f{locator}\x1f{text}".encode("utf-8")
                ).hexdigest()
                connection.execute(
                    "INSERT INTO evidence_chunks VALUES (?, ?, ?, ?, ?)",
                    (chunk_id, record.evidence_id, chunk_index, locator, text),
                )
                connection.execute(
                    "INSERT INTO evidence_chunk_fts(chunk_id, evidence_id, text) VALUES (?, ?, ?)",
                    (chunk_id, record.evidence_id, text),
                )
                chunk_count += 1
            if existing:
                updated += 1
            else:
                inserted += 1
        stale = connection.execute("SELECT evidence_id FROM evidence_items").fetchall()
        for (evidence_id,) in stale:
            if evidence_id not in seen:
                connection.execute("DELETE FROM evidence_items WHERE evidence_id = ?", (evidence_id,))
                connection.execute("DELETE FROM evidence_fts WHERE evidence_id = ?", (evidence_id,))
                connection.execute("DELETE FROM evidence_chunk_fts WHERE evidence_id = ?", (evidence_id,))
                connection.execute("DELETE FROM evidence_chunks WHERE evidence_id = ?", (evidence_id,))
        connection.commit()
    finally:
        connection.close()
    return {"inserted": inserted, "updated": updated, "reused": reused,
            "total": len(seen), "chunks": chunk_count}


def _fts_query(query: str) -> str:
    # Questions are natural language, not FTS5 expressions. Remove common
    # function words before quoting terms; the Porter tokenizer handles
    # deterministic morphological matching inside SQLite.
    terms = [term for term in re.findall(r"[\w]+", query.lower(), flags=re.UNICODE)
             if term not in _STOPWORDS]
    return " OR ".join(f'"{term.replace(chr(34), "")}"' for term in terms)


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    """Return sentence-like spans without requiring a model or a tokenizer."""
    spans: list[tuple[int, int]] = []
    start = 0
    for match in re.finditer(r"[.!?]+(?:[\"')\]]+)?(?=\s+|$)", text):
        end = match.end()
        if text[start:end].strip():
            spans.append((start, end))
        start = end
    if text[start:].strip():
        spans.append((start, len(text)))
    return spans


def _context_snippet(connection: sqlite3.Connection, evidence_id: str,
                     match_indexes: list[int], *, max_chars: int = 2400) -> str:
    """Return complete sentence-like excerpts around FTS matches.

    Subtitle cues are not sentence boundaries. Build a bounded cue window,
    reconstruct sentence-like spans from punctuation, and retain only the
    spans containing matched cues. This improves reviewability without
    changing the raw transcript or attempting to repair transcription text.
    """
    if not match_indexes:
        return ""
    rows = connection.execute(
        """SELECT chunk_index, text FROM evidence_chunks
           WHERE evidence_id = ? ORDER BY chunk_index""", (evidence_id,)
    ).fetchall()
    if not rows:
        return ""
    chunks = [(int(row[0]), str(row[1]).strip()) for row in rows if str(row[1]).strip()]
    text = " ".join(chunk for _, chunk in chunks)
    offsets: list[tuple[int, int, int]] = []
    cursor = 0
    for chunk_index, chunk in chunks:
        begin = cursor
        cursor += len(chunk)
        offsets.append((chunk_index, begin, cursor))
        cursor += 1
    spans = _sentence_spans(text)
    matched_sentences: set[int] = set()
    for chunk_index, begin, end_offset in offsets:
        if chunk_index not in match_indexes:
            continue
        for span_index, (span_start, span_end) in enumerate(spans):
            if begin < span_end and end_offset > span_start:
                matched_sentences.update(
                    index for index in (span_index - 1, span_index)
                    if 0 <= index < len(spans)
                )
    if not matched_sentences:
        # Punctuation-free transcript text still gets a bounded excerpt.
        result = text
    else:
        sentence_groups: list[list[int]] = []
        for index in sorted(matched_sentences):
            if sentence_groups and index == sentence_groups[-1][-1] + 1:
                sentence_groups[-1].append(index)
            else:
                sentence_groups.append([index])
        pieces = [" ".join(text[spans[index][0]:spans[index][1]].strip()
                            for index in group)
                  for group in sentence_groups]
        result = " […] ".join(piece for piece in pieces if piece)
    if len(result) <= max_chars:
        return result
    # Keep the beginning and end of a bounded context; the locator still
    # points to the exact matching chunk in the source artifact.
    head = max_chars * 2 // 3
    tail = max_chars - head - 7
    return result[:head].rstrip() + " […] " + result[-tail:].lstrip()


def search_index_with_metadata(
    query: str,
    index_path: str | Path = "data/evidence.sqlite3",
    limit: int = 10,
) -> dict[str, object]:
    """Search evidence and report how much matching indexed text was returned."""
    if limit < 1:
        raise ValueError("limit must be positive")
    fts_query = _fts_query(query)
    if not fts_query:
        return {
            "matches": [],
            "query": query,
            "limit": limit,
            "matched_chunk_count": 0,
            "matched_evidence_count": 0,
            "returned_count": 0,
            "truncated": False,
            "index_version": INDEX_VERSION,
        }
    connection = _connect(index_path)
    try:
        matched_chunk_count, matched_evidence_count = connection.execute(
            """SELECT COUNT(*), COUNT(DISTINCT evidence_id)
                 FROM evidence_chunk_fts
                WHERE evidence_chunk_fts MATCH ?""",
            (fts_query,),
        ).fetchone()
        rows = connection.execute(
            """WITH ranked AS (
                   SELECT i.evidence_id, i.platform, i.source_key, i.content_id, i.canonical_url,
                          i.published_at, i.title, i.kind, i.artifact_path, c.locator,
                          c.chunk_index, f.rank AS match_rank,
                          ROW_NUMBER() OVER (PARTITION BY i.evidence_id ORDER BY f.rank) AS evidence_rank
                     FROM evidence_chunk_fts f
                     JOIN evidence_chunks c ON c.chunk_id = f.chunk_id
                     JOIN evidence_items i ON i.evidence_id = c.evidence_id
                    WHERE evidence_chunk_fts MATCH ?
                 )
                 SELECT evidence_id, platform, source_key, content_id, canonical_url,
                        published_at, title, kind, artifact_path, locator, chunk_index
                   FROM ranked
                  WHERE evidence_rank = 1
               ORDER BY match_rank
                  LIMIT ?""",
            (fts_query, limit),
        ).fetchall()
        keys = ("evidence_id", "platform", "source_key", "content_id", "canonical_url",
                "published_at", "title", "kind", "artifact_path", "locator", "snippet")
        matches = []
        for row in rows:
            evidence_id = str(row[0])
            matched_indexes = [int(item[0]) for item in connection.execute(
                """SELECT c.chunk_index FROM evidence_chunk_fts f
                   JOIN evidence_chunks c ON c.chunk_id = f.chunk_id
                  WHERE evidence_chunk_fts MATCH ? AND f.evidence_id = ?
                  ORDER BY f.rank LIMIT 4""", (fts_query, evidence_id)
            ).fetchall()]
            base = row[:10] + (_context_snippet(connection, evidence_id, matched_indexes),)
            matches.append(dict(zip(keys, base)))
        return {
            "matches": matches,
            "query": query,
            "limit": limit,
            "matched_chunk_count": int(matched_chunk_count),
            "matched_evidence_count": int(matched_evidence_count),
            "returned_count": len(matches),
            "truncated": int(matched_chunk_count) > len(matches),
            "index_version": INDEX_VERSION,
        }
    finally:
        connection.close()


def search_index(query: str, index_path: str | Path = "data/evidence.sqlite3", limit: int = 10) -> list[dict[str, object]]:
    """Return matching evidence while preserving the original list API."""
    return list(search_index_with_metadata(query, index_path, limit)["matches"])
