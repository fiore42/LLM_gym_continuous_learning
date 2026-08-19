"""Provider-neutral synthesis contract with deterministic citation validation."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from dataclasses import field
from typing import Any, Protocol

from .prompt_registry import load_prompt
from ..shared.settings import agent_parameters


PROMPT_VERSION = load_prompt().prompt_version
# One configured ceiling for every synthesis call. Three separate
# defaults previously disagreed, and the lowest silently truncated a
# response that had been paid for.
MAX_OUTPUT_TOKENS = int(agent_parameters()["max_output_tokens"])

_UNSCOPED_CLAIM_PATTERNS = (
    re.compile(r"\bthe corpus (?:proves?|establishes?|demonstrates?|shows that|agrees)\b", re.I),
    re.compile(r"\b(?:all|every) sources? (?:agree|show|support|confirm)\b", re.I),
    re.compile(r"\bthe field (?:agrees|has reached consensus|consistently)\b", re.I),
    re.compile(r"\bthe corpus contains (?:no )?conflicting evidence\b", re.I),
    re.compile(r"\b(?:no|zero) (?:other )?sources? (?:disagree|conflict)\b", re.I),
    re.compile(r"\bindustry consensus\b", re.I),
    re.compile(r"\b(?:experts?|researchers?) (?:broadly|generally|widely) agree\b", re.I),
)
_NEGATED_SCOPE_PATTERN = re.compile(
    r"\b(?:not|never|no|without|does not|doesn't|do not|don't|is not|isn't|"
    r"cannot|can't)\b(?:\W+\w+){0,8}\W*$",
    re.I,
)
_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def validate_retrieval_scope(answer: str) -> list[str]:
    """Return corpus-wide claims that exceed the supplied evidence scope."""
    violations: list[str] = []
    for pattern in _UNSCOPED_CLAIM_PATTERNS:
        for match in pattern.finditer(answer):
            context_before = answer[max(0, match.start() - 80):match.start()]
            if _NEGATED_SCOPE_PATTERN.search(context_before):
                continue
            violations.append(pattern.pattern)
            break
    return violations


class ModelClient(Protocol):
    """Minimal interface for any future local or hosted model provider."""

    def complete(self, *, system: str, user: str, model: str, max_output_tokens: int) -> str:
        ...


@dataclass(frozen=True)
class SynthesisRequest:
    question: str
    evidence: tuple[dict[str, Any], ...]
    model: str
    prompt_version: str = PROMPT_VERSION
    max_output_tokens: int = MAX_OUTPUT_TOKENS
    revision_feedback: str = ""
    request_timeout_seconds: int | None = None

    def validate(self) -> None:
        if not self.question.strip():
            raise ValueError("question must not be empty")
        if not self.evidence:
            raise ValueError("synthesis requires retrieved evidence")
        if any(not item.get("evidence_id") for item in self.evidence):
            raise ValueError("every evidence item requires evidence_id")
        if not self.model.strip() or self.max_output_tokens < 1:
            raise ValueError("model and output token limit are required")
        if self.request_timeout_seconds is not None and self.request_timeout_seconds < 1:
            raise ValueError("request timeout must be positive")


@dataclass(frozen=True)
class SynthesisResult:
    answer: str
    citation_ids: tuple[str, ...]
    classification: str
    evidence_assessment: tuple[dict[str, Any], ...]
    model: str
    prompt_version: str
    validation: dict[str, Any]
    prompt: dict[str, Any] = field(default_factory=dict)
    suggested_queries: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def render_prompt(request: SynthesisRequest) -> tuple[str, str, dict[str, Any]]:
    prompt = load_prompt(version=request.prompt_version)
    evidence = "\n\n".join(
        f"EVIDENCE_ID: {item['evidence_id']}\n"
        f"SOURCE: {item.get('canonical_url', '')}\n"
        f"LOCATOR: {item.get('locator') or 'not specified'}\n"
        f"TEXT: {item.get('snippet', '')}"
        for item in request.evidence
    )
    system = prompt.system_template
    revision = (
        prompt.revision_templates["revision_prefix"] + request.revision_feedback
        if request.revision_feedback else ""
    )
    user = prompt.user_template.format(
        question=request.question, evidence=evidence, revision=revision,
    )
    return system, user, {
        "prompt_id": prompt.prompt_id,
        "prompt_version": prompt.prompt_version,
        "prompt_sha256": prompt.sha256,
        "source_path": prompt.source_path,
        "system_prompt": system,
        "rendered_user_prompt": user,
    }


def _parse_model_json(raw: str) -> dict[str, Any]:
    """Parse JSON responses with harmless Markdown/prose wrappers."""
    candidates = [raw.strip()]
    candidates.extend(match.strip() for match in _JSON_FENCE.findall(raw))
    first_object = raw.find("{")
    last_object = raw.rfind("}")
    if first_object >= 0 and last_object > first_object:
        candidates.append(raw[first_object:last_object + 1].strip())
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    preview = " ".join(raw.strip().split())[:400]
    raise ValueError(f"model response must be valid JSON; preview: {preview!r}")


def synthesize(request: SynthesisRequest, client: ModelClient) -> SynthesisResult:
    """Call an injected model and apply deterministic output/citation checks."""
    request.validate()
    system, user, prompt_record = render_prompt(request)
    raw = client.complete(system=system, user=user, model=request.model,
                          max_output_tokens=request.max_output_tokens,
                          timeout_seconds=request.request_timeout_seconds)
    payload = _parse_model_json(raw)
    answer = payload.get("answer")
    classification = payload.get("classification")
    citations = payload.get("citation_ids")
    assessment = payload.get("evidence_assessment")
    suggested_queries = payload.get("suggested_queries", [])
    allowed = {str(item["evidence_id"]) for item in request.evidence}
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("model response requires a non-empty answer")
    allowed_classifications = {"SUPPORTED", "INSUFFICIENT_EVIDENCE", "CONFLICTING_EVIDENCE"}
    if classification not in allowed_classifications:
        raise ValueError("model response requires a valid classification")
    if not isinstance(citations, list) or not citations:
        raise ValueError("model response requires citation_ids")
    citation_ids = tuple(str(item) for item in citations)
    unknown = sorted(set(citation_ids) - allowed)
    if unknown:
        raise ValueError(f"model returned unknown citation IDs: {unknown}")
    if not isinstance(assessment, list):
        raise ValueError("model response requires evidence_assessment")
    if not isinstance(suggested_queries, list) or any(
        not isinstance(query, str) or not query.strip() for query in suggested_queries
    ):
        raise ValueError("suggested_queries must be an array of non-empty strings")
    if len(suggested_queries) > 3:
        raise ValueError("suggested_queries must contain at most three queries")
    assessment_ids = [str(item.get("evidence_id")) for item in assessment
                      if isinstance(item, dict)]
    if len(assessment) != len(allowed) or set(assessment_ids) != allowed:
        raise ValueError("evidence_assessment must contain each supplied evidence ID exactly once")
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("relevant"), bool)
        or not isinstance(item.get("reason"), str)
        or not item["reason"].strip()
        for item in assessment
    ):
        raise ValueError("evidence_assessment entries require boolean relevant and non-empty reason")
    scope_violations = validate_retrieval_scope(answer)
    if scope_violations:
        raise ValueError(
            "answer makes an unsupported corpus-wide claim; scope it to the "
            "retrieved evidence"
        )
    validation = {
        "passed": True,
        "citation_count": len(citation_ids),
        "unknown_citation_ids": [],
        "evidence_available": len(allowed),
        "evidence_assessed": len(assessment),
        "evidence_marked_relevant": sum(bool(item["relevant"]) for item in assessment),
        "retrieval_scope_checked": True,
    }
    return SynthesisResult(answer.strip(), citation_ids, classification,
                           tuple(assessment), request.model, request.prompt_version,
                           validation, prompt_record,
                           tuple(query.strip() for query in suggested_queries))
