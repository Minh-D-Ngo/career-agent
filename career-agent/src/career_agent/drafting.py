"""Offline LangGraph workflow for a reviewable, evidence-linked draft."""

import hashlib
import html
import json
import re
from dataclasses import asdict, dataclass
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context

from .contracts import DraftClaim, EvidenceFact, EvidenceLibrary, JobSnapshot
from .matching import MatchReport, match


MAX_RECORDS = 3
SECTIONS = {
    "experience": "Experience",
    "project": "Projects",
    "leadership": "Leadership",
    "education": "Education",
    "skill": "Skills",
}


class DraftValidationError(ValueError):
    """The proposed claim text or citations cannot be used by the offline draft."""


@dataclass(frozen=True)
class DraftArtifacts:
    draft_id: str
    claim_count: int
    markdown: str
    evidence_json: str
    gaps_json: str

    def files(self) -> tuple[tuple[str, str], ...]:
        return (
            ("draft.md", self.markdown),
            ("evidence.json", self.evidence_json),
            ("gaps.json", self.gaps_json),
        )


class DraftInput(TypedDict):
    job: JobSnapshot
    library: EvidenceLibrary
    selected_fact_ids: tuple[str, ...] | None


class DraftState(DraftInput, total=False):
    report: MatchReport
    claims: tuple[DraftClaim, ...]
    artifacts: DraftArtifacts


def _match_evidence(state: DraftState) -> dict:
    return {"report": match(state["job"], state["library"])}


def candidate_facts(report: MatchReport, library: EvidenceLibrary) -> tuple[EvidenceFact, ...]:
    relevant_ids = {
        fact_id for item in report.requirements for fact_id in item.capability_evidence_ids
    }
    records = {record.id: record for record in library.records}
    return tuple(
        fact
        for ranked in report.ranked_records[:MAX_RECORDS]
        for fact in records[ranked.record_id].facts
        if fact.id in relevant_ids
    )


def _select_claims(state: DraftState) -> dict:
    facts = candidate_facts(state["report"], state["library"])
    selection = state["selected_fact_ids"]
    if selection is not None:
        by_id = {fact.id: fact for fact in facts}
        if not selection or len(set(selection)) != len(selection) or set(selection) - by_id.keys():
            raise DraftValidationError("Model selection must use unique fact IDs from the ranked shortlist.")
        facts = tuple(by_id[fact_id] for fact_id in selection)
    return {"claims": tuple(
        DraftClaim(id=f"claim_{fact.id}", text=fact.assertion, evidence_ids=(fact.id,))
        for fact in facts
    )}


def validate_verbatim_claim(
    claim: DraftClaim, facts: dict[str, EvidenceFact],
) -> tuple[EvidenceFact, ...]:
    """Require every citation to support the exact text used by the stub."""
    missing = sorted(set(claim.evidence_ids) - facts.keys())
    if missing:
        raise DraftValidationError(f"Claim {claim.id} cites unknown evidence: {', '.join(missing)}")
    cited = tuple(facts[fact_id] for fact_id in claim.evidence_ids)
    if any(fact.assertion != claim.text for fact in cited):
        raise DraftValidationError(f"Unsupported claim {claim.id} differs from its cited evidence")
    return cited


def _markdown_text(text: str) -> str:
    # Preserve the displayed text while preventing imported markup from becoming links or HTML.
    escaped = html.escape(" ".join(text.split()), quote=False)
    return re.sub(r"([\\`*_\[\]#|~])", r"\\\1", escaped)


def _json_text(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _validate_and_render(state: DraftState) -> dict:
    job, report = state["job"], state["report"]
    records = {record.id: record for record in state["library"].records}
    facts = {fact.id: fact for record in records.values() for fact in record.facts}
    record_id_by_fact = {
        fact.id: record.id for record in records.values() for fact in record.facts
    }
    claims_by_record: dict[str, list[DraftClaim]] = {}
    evidence_rows = []
    for claim in state["claims"]:
        cited = validate_verbatim_claim(claim, facts)
        record_id = record_id_by_fact[cited[0].id]
        claims_by_record.setdefault(record_id, []).append(claim)
        evidence_rows.append({
            "claim_id": claim.id,
            "text": claim.text,
            "evidence_ids": claim.evidence_ids,
            "support": "supported",
            "rationale": "Verbatim reuse of the supplied assertion. Review the source before use.",
            "citations": [
                {"record_id": record_id_by_fact[fact.id], **fact.model_dump(mode="json")}
                for fact in cited
            ],
        })

    target = f"{_markdown_text(job.title)} at {_markdown_text(job.employer)}"
    lines = ["# Resume draft", "", f"Target role: {target}", "", "Review status: **DRAFT**", ""]
    if not claims_by_record:
        lines.extend(["No relevant evidence was selected. Review the gap report.", ""])
    for kind, heading in SECTIONS.items():
        section_ids = [
            record_id for record_id in claims_by_record if records[record_id].kind == kind
        ]
        if not section_ids:
            continue
        lines.extend([f"## {heading}", ""])
        for record_id in section_ids:
            lines.extend([f"### {_markdown_text(records[record_id].title)}", ""])
            for claim in claims_by_record[record_id]:
                lines.append(f"- {_markdown_text(claim.text)} [`{claim.id}`]")
            lines.append("")

    markdown = "\n".join(lines)
    job_reference = {
        "job_id": job.id, "job_version": job.version, "description_sha256": report.description_sha256,
    }
    evidence = {
        "schema_version": "1.0",
        **job_reference,
        "review_status": "DRAFT",
        "selected_record_ids": list(claims_by_record),
        "claims": evidence_rows,
    }
    if state["selected_fact_ids"] is not None:
        evidence["selected_fact_ids"] = state["selected_fact_ids"]
    gaps = {
        "schema_version": "1.0",
        **job_reference,
        "requirements": [asdict(item) for item in report.requirements],
    }
    fingerprint = _json_text({"markdown": markdown, "evidence": evidence, "gaps": gaps})
    draft_id = "draft_" + hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]
    return {"artifacts": DraftArtifacts(
        draft_id=draft_id,
        claim_count=len(evidence_rows),
        markdown=markdown,
        evidence_json=_json_text({"draft_id": draft_id, **evidence}),
        gaps_json=_json_text({"draft_id": draft_id, **gaps}),
    )}


def _build_graph():
    graph = StateGraph(DraftState, input_schema=DraftInput)
    graph.add_node("match_evidence", _match_evidence)
    graph.add_node("select_claims", _select_claims)
    graph.add_node("validate_and_render", _validate_and_render)
    graph.add_edge(START, "match_evidence")
    graph.add_edge("match_evidence", "select_claims")
    graph.add_edge("select_claims", "validate_and_render")
    graph.add_edge("validate_and_render", END)
    return graph.compile()


_GRAPH = _build_graph()


def build_draft(
    job: JobSnapshot, library: EvidenceLibrary, selected_fact_ids: tuple[str, ...] | None = None,
) -> DraftArtifacts:
    # Draft inputs can contain private material even when tracing is enabled in the shell.
    with tracing_context(enabled=False):
        return _GRAPH.invoke({
            "job": job, "library": library, "selected_fact_ids": selected_fact_ids,
        })["artifacts"]
