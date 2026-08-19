"""Persist X media and linked document assets for a post."""

from __future__ import annotations

import json
import mimetypes
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ..shared.atomic import atomic_write_text
from ..shared.settings import x_parameters


def _extension(url: str, content_type: str | None = None) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".m4v", ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}:
        return suffix
    guessed = mimetypes.guess_extension((content_type or "").split(";", 1)[0].strip())
    return guessed or ".bin"


def _download(url: str, destination: Path, *, max_bytes: int, timeout: int, opener=urlopen) -> str:
    request = Request(url, headers={"User-Agent": "LLM-gym-continuous-learning/1.0"})
    with opener(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        length = response.headers.get("Content-Length")
        if length and int(length) > max_bytes:
            raise ValueError(f"asset exceeds configured limit: {length} bytes")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=f".{destination.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            total = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    temporary.unlink(missing_ok=True)
                    raise ValueError(f"asset exceeds configured limit: {total} bytes")
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
    os.replace(temporary, destination)
    return content_type


def persist_post_assets(post_dir: str | Path, post: dict[str, object], includes: dict[str, list[dict[str, object]]], *, opener=urlopen) -> tuple[int, int, tuple[str, ...]]:
    """Download media and document links, returning counts and non-fatal warnings."""
    params = x_parameters()
    root = Path(post_dir)
    warnings: list[str] = []
    media_downloads = document_downloads = 0
    media_by_key = {str(item.get("media_key")): item for item in includes.get("media", []) if item.get("media_key")}
    media_dir = root / "media"
    for key in (post.get("attachments") or {}).get("media_keys", []):
        media = media_by_key.get(str(key))
        if not media:
            warnings.append(f"MEDIA_METADATA_MISSING:{key}")
            continue
        candidates = []
        if media.get("url"):
            candidates.append((0, str(media["url"]), None))
        for variant in media.get("variants", []) or []:
            if variant.get("url"):
                candidates.append((int(variant.get("bit_rate") or 0), str(variant["url"]), variant.get("content_type")))
        if not candidates:
            warnings.append(f"MEDIA_URL_MISSING:{key}")
            continue
        _, url, content_type = max(candidates, key=lambda item: item[0])
        destination = media_dir / f"{key}{_extension(url, content_type or media.get('type'))}"
        try:
            if params["download_media"] and not destination.exists():
                _download(url, destination, max_bytes=params["max_media_bytes"], timeout=params["download_timeout_seconds"], opener=opener)
                media_downloads += 1
        except Exception as exc:
            warnings.append(f"MEDIA_DOWNLOAD_FAILED:{key}:{exc}")
        atomic_write_text(media_dir / f"{key}.json", json.dumps(media, indent=2, ensure_ascii=False) + "\n")

    document_dir = root / "documents"
    document_suffixes = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".csv", ".txt", ".md"}
    for index, entity in enumerate((post.get("entities") or {}).get("urls", []) or [], start=1):
        url = entity.get("expanded_url") or entity.get("url")
        if not url or Path(urlparse(url).path).suffix.lower() not in document_suffixes:
            continue
        destination = document_dir / f"{index}{_extension(url)}"
        try:
            if params["download_linked_documents"] and not destination.exists():
                _download(url, destination, max_bytes=params["max_document_bytes"], timeout=params["download_timeout_seconds"], opener=opener)
                document_downloads += 1
        except Exception as exc:
            warnings.append(f"DOCUMENT_DOWNLOAD_FAILED:{url}:{exc}")
    if post.get("article"):
        atomic_write_text(root / "article.json", json.dumps(post["article"], indent=2, ensure_ascii=False) + "\n")
    return media_downloads, document_downloads, tuple(warnings)
