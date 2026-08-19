"""Per-item significance assessment: one corpus item, one bounded model call.

One item per call keeps every unit bounded, inspectable and independently
retryable, and it is what lets a digest run for tens of minutes without any
single call being long. The alternative — one call over the whole window — is
faster to build and impossible to debug.

The model returns a judgement plus one to three mapped verbatim spans from the
item text. Deterministic code then checks that every span really appears in the
text, so the judgement is auditable rather than trusted. A confident assessment
quoting something the item never said is rejected here, not downstream.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .prompt_registry import load_prompt
from .synthesis import MAX_OUTPUT_TOKENS, _parse_model_json
from ..shared.settings import agent_parameters

DIGEST_PROMPT_ROOT = Path(__file__).resolve().parents[2] / "prompts" / "digest"
SIGNIFICANCE_PROMPT_VERSION = load_prompt(root=DIGEST_PROMPT_ROOT).prompt_version

# Duplication is deliberately absent: it is a deterministic property of a group
# of items, decided by code, not a judgement about one item in isolation.
SIGNIFICANCE_LABELS = ("SIGNIFICANT", "INCREMENTAL", "UNSUPPORTED", "PROMOTIONAL")

_WHITESPACE = re.compile(r"\s+")


class ModelClient(Protocol):
    def complete(self, *, system: str, user: str, model: str,
                 max_output_tokens: int) -> str: ...


@dataclass(frozen=True)
class SignificanceRequest:
    item: dict[str, Any]
    model: str
    prompt_version: str = SIGNIFICANCE_PROMPT_VERSION
    max_output_tokens: int = MAX_OUTPUT_TOKENS
    revision_feedback: str = ""
    request_timeout_seconds: int | None = None

    def validate(self) -> None:
        if not str(self.item.get("evidence_id") or "").strip():
            raise ValueError("item requires evidence_id")
        if not str(self.item.get("text") or "").strip():
            raise ValueError("item requires text to assess")
        if not self.model.strip() or self.max_output_tokens < 1:
            raise ValueError("model and output token limit are required")
        if self.request_timeout_seconds is not None and self.request_timeout_seconds < 1:
            raise ValueError("request timeout must be positive")


@dataclass(frozen=True)
class SignificanceResult:
    item_id: str
    claimed_change: str
    problem_addressed: str
    significance: str
    reason: str
    supporting_evidence: list[dict[str, str]]
    model: str
    prompt_version: str
    validation: dict[str, Any]
    prompt: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.prompt_version == "significance-v1":
            evidence = payload.pop("supporting_evidence")
            payload["supporting_quote"] = evidence[0]["quote"]
        return payload

    @property
    def supporting_quote(self) -> str:
        """Compatibility view for code inspecting an explicit v1 result."""
        return self.supporting_evidence[0]["quote"]


def render_prompt(request: SignificanceRequest) -> tuple[str, str, dict[str, Any]]:
    prompt = load_prompt(version=request.prompt_version, root=DIGEST_PROMPT_ROOT)
    item = request.item
    user = prompt.user_template.format(
        item_id=item.get("evidence_id", ""),
        published_at=item.get("published_at_utc") or item.get("published_at") or "unknown",
        canonical_url=item.get("canonical_url", ""),
        title=item.get("title") or "untitled",
        text=item.get("text", ""),
    )
    if request.revision_feedback:
        user += prompt.revision_templates["revision_prefix"] + request.revision_feedback
    return prompt.system_template, user, {
        "prompt_id": prompt.prompt_id,
        "prompt_version": prompt.prompt_version,
        "prompt_sha256": prompt.sha256,
        "source_path": prompt.source_path,
        "system_prompt": prompt.system_template,
        "rendered_user_prompt": user,
    }


def quote_is_grounded(quote: str, text: str) -> bool:
    """Return whether the quote appears in the item text.

    Compared with whitespace collapsed, because a model reflowing a line break
    into a space has not misquoted anything. Every other difference — changed
    wording, corrected spelling, inserted ellipsis — fails, which is the point:
    a quote that cannot be located is not evidence.
    """
    if not quote.strip():
        return False
    return _WHITESPACE.sub(" ", quote).strip().casefold() in _WHITESPACE.sub(" ", text).strip().casefold()


def _supporting_evidence(payload: dict[str, Any], request: SignificanceRequest) -> list[dict[str, str]]:
    """Validate the versioned evidence shape and ground every exact quote."""
    text = str(request.item.get("text") or "")
    if request.prompt_version == "significance-v1":
        quote = payload.get("supporting_quote")
        if not isinstance(quote, str):
            raise ValueError("supporting_quote must be a string")
        if not quote_is_grounded(quote, text):
            raise ValueError(
                "supporting_quote does not appear in the item text; the judgement "
                "cannot be checked against the source")
        return [{"claim_component": payload["claimed_change"].strip(),
                 "quote": quote.strip()}]

    evidence = payload.get("supporting_evidence")
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 3:
        raise ValueError("supporting_evidence must contain between 1 and 3 entries")
    cleaned: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, row in enumerate(evidence, start=1):
        if not isinstance(row, dict) or set(row) != {"claim_component", "quote"}:
            raise ValueError(
                f"supporting_evidence[{index}] must contain only claim_component and quote")
        component, quote = row["claim_component"], row["quote"]
        if not isinstance(component, str) or not component.strip():
            raise ValueError(f"supporting_evidence[{index}].claim_component must be text")
        if not isinstance(quote, str) or not quote.strip():
            raise ValueError(f"supporting_evidence[{index}].quote must be text")
        identity = _WHITESPACE.sub(" ", quote).strip().casefold()
        if identity in seen:
            raise ValueError("supporting_evidence quotes must be distinct")
        if not quote_is_grounded(quote, text):
            raise ValueError(
                f"supporting_evidence[{index}].quote does not appear in the item text; "
                "the judgement cannot be checked against the source")
        seen.add(identity)
        cleaned.append({"claim_component": component.strip(), "quote": quote.strip()})
    return cleaned


def _validated(payload: dict[str, Any], request: SignificanceRequest) -> dict[str, Any]:
    """Reject a response that does not meet the contract, naming the reason."""
    expected = {"claimed_change", "problem_addressed", "significance", "reason",
                "supporting_quote" if request.prompt_version == "significance-v1"
                else "supporting_evidence"}
    if set(payload) != expected:
        raise ValueError(
            f"model response keys must be exactly {sorted(expected)}; got {sorted(payload)}")
    for key in ("claimed_change", "problem_addressed", "significance", "reason"):
        if key not in payload:
            raise ValueError(f"model response is missing {key}")
        if not isinstance(payload[key], str):
            raise ValueError(f"{key} must be a string")
    significance = payload["significance"].strip().upper()
    if significance not in SIGNIFICANCE_LABELS:
        raise ValueError(
            f"significance must be one of {list(SIGNIFICANCE_LABELS)}; got {significance!r}")
    if not payload["reason"].strip():
        raise ValueError("reason must not be empty")
    evidence = _supporting_evidence(payload, request)
    return {
        "significance": significance,
        "quote_grounded": True,
        "quotes_grounded": True,
        "evidence_count": len(evidence),
        "quote_lengths": [len(row["quote"]) for row in evidence],
        "labels_allowed": list(SIGNIFICANCE_LABELS),
        "supporting_evidence": evidence,
    }


def assess_item(request: SignificanceRequest, client: ModelClient) -> SignificanceResult:
    """Assess one item, validating the response before returning it."""
    request.validate()
    system, user, prompt_record = render_prompt(request)
    kwargs: dict[str, Any] = {"system": system, "user": user, "model": request.model,
                              "max_output_tokens": request.max_output_tokens}
    if request.request_timeout_seconds is not None:
        kwargs["timeout_seconds"] = request.request_timeout_seconds
    payload = _parse_model_json(client.complete(**kwargs))
    validation = _validated(payload, request)
    supporting_evidence = validation.pop("supporting_evidence")
    return SignificanceResult(
        item_id=str(request.item["evidence_id"]),
        claimed_change=payload["claimed_change"].strip(),
        problem_addressed=payload["problem_addressed"].strip(),
        significance=validation["significance"],
        reason=payload["reason"].strip(),
        supporting_evidence=supporting_evidence,
        model=request.model,
        prompt_version=prompt_record["prompt_version"],
        validation=validation,
        prompt=prompt_record,
    )
