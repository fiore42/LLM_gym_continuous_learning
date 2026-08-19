"""OpenAI-compatible model client with environment-only credentials."""

from __future__ import annotations

import json
import os
from time import perf_counter
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from typing import Callable

from ..shared.settings import runtime_parameters


class ModelProviderError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


def _http_error(exc: HTTPError) -> ModelProviderError:
    """Preserve actionable provider diagnostics without exposing credentials."""
    try:
        body = exc.read().decode("utf-8", errors="replace")
        payload = json.loads(body)
        detail = payload.get("error", payload)
        if isinstance(detail, dict):
            detail = detail.get("message") or detail.get("type") or detail
        detail = str(detail)
    except (OSError, UnicodeError, json.JSONDecodeError):
        detail = str(exc.reason or "no response body")
    if len(detail) > 500:
        detail = detail[:497] + "..."
    retryable = exc.code in {408, 409, 429} or exc.code >= 500
    return ModelProviderError(
        f"model request failed: HTTP {exc.code}: {detail}", retryable=retryable
    )


RESPONSE_FORMATS = {"json_object", "text", "none"}
THINKING_MODES = {"enabled", "disabled", "none"}


def _provider_option(prefix: str, name: str, default: str, allowed: set[str]) -> str:
    """Read one provider-shape option, failing fast on an unusable value.

    Providers disagree about these fields and the disagreement is only visible
    live: an OpenAI-compatible URL does not imply an OpenAI-compatible request
    body. A typo here would otherwise be sent to the provider and come back as
    an opaque 400, so reject it at construction instead.
    """
    value = (os.environ.get(f"{prefix}_{name}", "") or default).strip().lower()
    if value not in allowed:
        raise ValueError(
            f"{prefix}_{name} must be one of {sorted(allowed)}; got {value!r}"
        )
    return value


def _usage(payload_usage: dict, *, prefix: str = "AGENT",
           latency_seconds: float | None = None) -> dict:
    """Normalize provider usage, estimated cost, and observed latency.

    ``latency_seconds`` is time-to-last-token: this client blocks until the
    full response is read, so no earlier timing is observable without
    switching to streaming. Raw latency is confounded by answer length — a
    model that writes more takes longer without being slower — so
    ``output_tokens_per_second`` is the comparable figure across providers.
    """
    input_tokens = int(payload_usage.get("prompt_tokens", payload_usage.get("input_tokens", 0)) or 0)
    output_tokens = int(payload_usage.get("completion_tokens", payload_usage.get("output_tokens", 0)) or 0)
    input_rate = float(os.environ.get(f"{prefix}_INPUT_COST_PER_MILLION", "0") or 0)
    output_rate = float(os.environ.get(f"{prefix}_OUTPUT_COST_PER_MILLION", "0") or 0)
    usage = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000,
    }
    if latency_seconds is not None:
        usage["latency_seconds"] = round(latency_seconds, 4)
        usage["output_tokens_per_second"] = (
            round(output_tokens / latency_seconds, 2) if latency_seconds > 0 else None
        )
    return usage


class OpenAICompatibleClient:
    """Minimal chat-completions client; provider details stay outside synthesis."""

    def __init__(self, *, api_key: str, base_url: str, opener: Callable = urlopen,
                 timeout_seconds: int | None = None, cost_prefix: str = "AGENT",
                 response_format: str | None = None, thinking: str | None = None):
        if not api_key.strip():
            raise ValueError("AGENT_API_KEY is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.opener = opener
        self.timeout_seconds = timeout_seconds or runtime_parameters()["subprocess_timeout_seconds"]
        self.cost_prefix = cost_prefix
        # Defaults preserve the OpenAI request shape. Other providers on this
        # endpoint shape differ: GLM-5.2 does not document response_format and
        # enables reasoning by default, which bills as output and can consume
        # the whole token budget before any JSON is emitted.
        self.response_format = (
            _provider_option(cost_prefix, "RESPONSE_FORMAT", "json_object", RESPONSE_FORMATS)
            if response_format is None else response_format)
        self.thinking = (
            _provider_option(cost_prefix, "THINKING", "none", THINKING_MODES)
            if thinking is None else thinking)
        self.last_usage: dict = {}

    @classmethod
    def from_environment(cls, *, opener: Callable = urlopen) -> "OpenAICompatibleClient":
        return cls(api_key=os.environ.get("AGENT_API_KEY", ""),
                   base_url=os.environ.get("AGENT_BASE_URL", "https://api.openai.com/v1"),
                   opener=opener)

    def complete(self, *, system: str, user: str, model: str, max_output_tokens: int,
                 timeout_seconds: int | None = None) -> str:
        # Usage describes this request only. Clear it at the client boundary so
        # even a caller that forgets to do so cannot charge a failed request
        # with the preceding successful request's usage.
        self.last_usage = {}
        payload_body: dict = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": max_output_tokens,
            "temperature": 0,
        }
        if self.response_format != "none":
            payload_body["response_format"] = {"type": self.response_format}
        if self.thinking != "none":
            payload_body["thinking"] = {"type": self.thinking}
        body = json.dumps(payload_body).encode("utf-8")
        request = Request(self.base_url + "/chat/completions", data=body, method="POST",
                          headers={"Authorization": f"Bearer {self.api_key}",
                                   "Content-Type": "application/json"})
        try:
            started = perf_counter()
            with self.opener(request, timeout=timeout_seconds or self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
            latency_seconds = perf_counter() - started
        except HTTPError as exc:
            raise _http_error(exc) from exc
        except Exception as exc:
            raise ModelProviderError(f"model request failed: {exc}") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ModelProviderError("model response was not valid JSON") from exc
        # Usage belongs to the HTTP request, even when its content is later
        # rejected as truncated or structurally invalid. Record it as soon as
        # the response envelope is readable so callers can preserve billed
        # spend on failed attempts.
        self.last_usage = _usage(payload.get("usage") or {}, prefix=self.cost_prefix,
                                 latency_seconds=latency_seconds)
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelProviderError("model response did not contain choices[0].message.content") from exc
        # A truncated response is usually unparseable JSON. Report the real
        # cause instead of letting it surface as a parse failure downstream.
        if (payload.get("choices") or [{}])[0].get("finish_reason") == "length":
            raise ModelProviderError(
                f"model response truncated at max_output_tokens={max_output_tokens}; "
                "raise the output limit or reduce the supplied evidence",
                retryable=False,
            )
        if not isinstance(content, str) or not content.strip():
            raise ModelProviderError("model returned empty content")
        return content


class AnthropicClient:
    """Minimal Anthropic Messages API client behind the shared model contract."""

    def __init__(self, *, api_key: str, base_url: str = "https://api.anthropic.com",
                 opener: Callable = urlopen, timeout_seconds: int | None = None,
                 cost_prefix: str = "AGENT", thinking: str | None = None):
        if not api_key.strip():
            raise ValueError("ANTHROPIC_API_KEY is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.opener = opener
        self.timeout_seconds = timeout_seconds or runtime_parameters()["subprocess_timeout_seconds"]
        self.cost_prefix = cost_prefix
        # Synthesis returns a fixed JSON schema, so extended thinking buys
        # little and bills as output. Overridable, since that is a measurable
        # claim rather than a certainty.
        self.thinking = (
            _provider_option(cost_prefix, "THINKING", "disabled", THINKING_MODES)
            if thinking is None else thinking)
        self.last_usage: dict = {}

    @classmethod
    def from_environment(cls, *, opener: Callable = urlopen) -> "AnthropicClient":
        return cls(api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
                   base_url=os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
                   opener=opener)

    def complete(self, *, system: str, user: str, model: str, max_output_tokens: int,
                 timeout_seconds: int | None = None) -> str:
        self.last_usage = {}
        payload_body: dict = {
            "model": model,
            "max_tokens": max_output_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if self.thinking != "none":
            payload_body["thinking"] = {"type": self.thinking}
        body = json.dumps(payload_body).encode("utf-8")
        request = Request(self.base_url + "/v1/messages", data=body, method="POST",
                          headers={"x-api-key": self.api_key,
                                   "anthropic-version": "2023-06-01",
                                   "Content-Type": "application/json"})
        try:
            started = perf_counter()
            with self.opener(request, timeout=timeout_seconds or self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
            latency_seconds = perf_counter() - started
        except HTTPError as exc:
            raise _http_error(exc) from exc
        except Exception as exc:
            raise ModelProviderError(f"model request failed: {exc}") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ModelProviderError("model response was not valid JSON") from exc
        self.last_usage = _usage(payload.get("usage") or {}, prefix=self.cost_prefix,
                                 latency_seconds=latency_seconds)
        try:
            blocks = payload["content"]
            if not isinstance(blocks, list):
                raise TypeError("content is not a list")
            content = "\n".join(
                str(block["text"])
                for block in blocks
                if isinstance(block, dict)
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelProviderError("model response did not contain a text content block") from exc
        # A truncated response is usually unparseable JSON. Report the real
        # cause instead of letting it surface as a parse failure downstream.
        if payload.get("stop_reason") == "max_tokens":
            raise ModelProviderError(
                f"model response truncated at max_output_tokens={max_output_tokens}; "
                "raise the output limit or reduce the supplied evidence",
                retryable=False,
            )
        if not isinstance(content, str) or not content.strip():
            raise ModelProviderError("model returned empty content")
        return content


def model_client_from_environment(*, opener: Callable = urlopen, prefix: str = "AGENT"):
    """Select a provider without changing synthesis or runner contracts."""
    provider = os.environ.get(f"{prefix}_PROVIDER", "openai-compatible").strip().lower()
    api_key = os.environ.get(f"{prefix}_API_KEY", "")
    base_url = os.environ.get(f"{prefix}_BASE_URL", "")
    if provider == "anthropic":
        if prefix == "AGENT":
            api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
            base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL", "")
        return AnthropicClient(api_key=api_key,
                               base_url=base_url or "https://api.anthropic.com", opener=opener,
                               cost_prefix=prefix)
    if provider in {"openai", "openai-compatible"}:
        return OpenAICompatibleClient(api_key=api_key,
                                      base_url=base_url or "https://api.openai.com/v1", opener=opener,
                                      cost_prefix=prefix)
    raise ValueError(f"unsupported AGENT_PROVIDER: {provider}")
