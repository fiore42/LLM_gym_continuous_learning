"""Small, testable X API v2 client for user timelines."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ..shared.settings import ingestion_parameters, x_parameters


class XApiError(RuntimeError):
    """An API response that X returned as an error payload."""

    def __init__(self, message: str, *, problem_type: str | None = None):
        super().__init__(message)
        self.problem_type = problem_type


def _request_json(url: str, token: str, *, opener=urlopen) -> dict:
    request = Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with opener(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        exc.close()
        try:
            details = json.loads(body)
            errors = details.get("errors") or details.get("detail") or body
            if isinstance(errors, list):
                errors = "; ".join(str(item.get("detail", item)) for item in errors)
        except json.JSONDecodeError:
            errors = body
        raise XApiError(f"X API HTTP {exc.code}: {errors}") from exc
    if not isinstance(payload, dict):
        raise ValueError("X API returned a non-object response")
    if payload.get("errors") and not payload.get("data"):
        errors = payload["errors"]
        details = "; ".join(str(item.get("detail", item)) for item in errors)
        problem_type = next(
            (item.get("type") for item in errors if isinstance(item, dict) and item.get("type")),
            None,
        )
        raise XApiError(f"X API error: {details}", problem_type=problem_type)
    return payload


def _token(*, user_context: bool = False) -> str:
    variable = "X_API_USER_ACCESS_TOKEN" if user_context else "X_API_BEARER_TOKEN"
    token = os.environ.get(variable)
    if not token:
        raise RuntimeError(f"{variable} is required for X API ingestion")
    return token


def resolve_user_id(handle: str, *, opener=urlopen, access_token: str | None = None) -> str:
    """Resolve a username once; callers should persist the returned ID."""
    payload = _request_json(
        "https://api.x.com/2/users/by/username/" + handle.lstrip("@"),
        access_token or _token(), opener=opener,
    )
    user_id = (payload.get("data") or {}).get("id")
    if not user_id:
        raise RuntimeError(f"X API did not resolve user {handle}")
    return str(user_id)


def discover_user_posts_with_includes(
    handle: str,
    *,
    since: datetime | None = None,
    since_exclusive: bool = False,
    until: datetime | None = None,
    user_id: str | None = None,
    access_token: str | None = None,
    opener=urlopen,
) -> tuple[list[dict[str, object]], dict[str, list[dict[str, object]]]]:
    """Return configured posts plus expanded media and related API objects."""
    token = access_token or _token()
    params = x_parameters()
    ingestion = ingestion_parameters()
    # X timeline boundaries are second-granularity. Leave a small safety gap
    # when asking for the newest posts so the request is not ahead of X's
    # consistency window.
    effective_until = until or (datetime.now(timezone.utc) - timedelta(seconds=10))
    effective_until = effective_until.astimezone(timezone.utc).replace(microsecond=0)
    requested_since = since or effective_until - timedelta(days=ingestion["default_window_days"])
    if requested_since > effective_until:
        raise ValueError("since must be earlier than until")
    effective_since = max(
        requested_since,
        effective_until - timedelta(days=ingestion["max_window_days"]),
    )
    if since_exclusive:
        effective_since += timedelta(seconds=1)
    user_id = user_id or resolve_user_id(handle, opener=opener)
    query = {
        "max_results": params["max_results_per_request"],
        "start_time": effective_since.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "end_time": effective_until.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "tweet.fields": "id,text,created_at,author_id,conversation_id,in_reply_to_user_id,referenced_tweets,attachments,article,entities,lang,possibly_sensitive",
        "expansions": "attachments.media_keys,attachments.media_source_tweet,article.cover_media,article.media_entities,referenced_tweets.id,referenced_tweets.id.attachments.media_keys",
        "media.fields": "alt_text,duration_ms,height,media_key,preview_image_url,type,url,variants,width",
    }
    excludes = []
    if not params["include_replies"]:
        excludes.append("replies")
    if not params["include_retweets"]:
        excludes.append("retweets")
    if excludes:
        query["exclude"] = ",".join(excludes)
    posts: list[dict[str, object]] = []
    includes: dict[str, list[dict[str, object]]] = {}
    next_token = None
    while True:
        page_query = dict(query)
        if next_token:
            page_query["pagination_token"] = next_token
        payload = _request_json(
            "https://api.x.com/2/users/" + str(user_id) + "/tweets?" + urlencode(page_query),
            token,
            opener=opener,
        )
        posts.extend(payload.get("data") or [])
        for key, values in (payload.get("includes") or {}).items():
            if isinstance(values, list):
                includes.setdefault(key, []).extend(values)
        next_token = (payload.get("meta") or {}).get("next_token")
        if not next_token:
            break
    for key, values in includes.items():
        unique = {str(item.get("id") or item.get("media_key")): item for item in values}
        includes[key] = list(unique.values())
    return posts, includes


def discover_user_posts(
    handle: str,
    **kwargs,
) -> list[dict[str, object]]:
    """Return every configured main post in the requested window."""
    posts, _ = discover_user_posts_with_includes(handle, **kwargs)
    return posts


def lookup_posts_with_includes(
    post_ids: list[str], *, access_token: str | None = None, opener=urlopen,
) -> tuple[list[dict[str, object]], dict[str, list[dict[str, object]]]]:
    """Look up up to 100 existing posts with their expanded assets."""
    if not post_ids:
        return [], {}
    if len(post_ids) > 100:
        raise ValueError("X post lookup supports at most 100 IDs per request")
    query = {
        "ids": ",".join(post_ids),
        "tweet.fields": "id,text,created_at,author_id,conversation_id,in_reply_to_user_id,referenced_tweets,attachments,article,entities,lang,possibly_sensitive",
        "expansions": "attachments.media_keys,attachments.media_source_tweet,article.cover_media,article.media_entities,referenced_tweets.id,referenced_tweets.id.attachments.media_keys",
        "media.fields": "alt_text,duration_ms,height,media_key,preview_image_url,type,url,variants,width",
    }
    payload = _request_json(
        "https://api.x.com/2/tweets?" + urlencode(query),
        access_token or _token(), opener=opener,
    )
    includes = {
        key: value for key, value in (payload.get("includes") or {}).items()
        if isinstance(value, list)
    }
    return list(payload.get("data") or []), includes
