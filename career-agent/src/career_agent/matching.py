"""Explainable matching of manually normalized job and evidence labels."""

from dataclasses import dataclass
from typing import Literal

from .contracts import EvidenceFact, EvidenceLibrary, JobSnapshot, Requirement

Coverage = Literal["direct", "partial", "missing", "unknown"]
WEIGHTS = {"required": 3, "responsibility": 2, "preferred": 1, "example": 1}


@dataclass(frozen=True)
class RequirementMatch:
    requirement_id: str
    level: str
    capability: str
    named_tools: tuple[str, ...]
    coverage: Coverage
    capability_evidence_ids: tuple[str, ...]
    named_tool_coverage: Literal["direct", "missing", "unknown"] | None
    named_tool_evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class RankedRecord:
    record_id: str
    score: int
    direct_requirement_ids: tuple[str, ...]
    partial_requirement_ids: tuple[str, ...]


@dataclass(frozen=True)
class MatchReport:
    job_id: str
    job_version: int
    description_sha256: str
    requirements: tuple[RequirementMatch, ...]
    ranked_records: tuple[RankedRecord, ...]


def _normalize(label: str) -> str:
    return " ".join(label.casefold().split())


def _matching_facts(
    requirement: Requirement, facts: tuple[EvidenceFact, ...]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    capability = _normalize(requirement.capability)
    named_tools = {_normalize(tool) for tool in requirement.named_tools}
    related, exact = [], []
    for fact in facts:
        if capability in {_normalize(label) for label in fact.capabilities}:
            related.append(fact.id)
            if named_tools.intersection(_normalize(tech) for tech in fact.technologies):
                exact.append(fact.id)
    return tuple(related), tuple(exact)


def _coverage(
    related: list[str], exact: list[str], *, has_tools: bool, has_evidence: bool
) -> Coverage:
    if exact or (related and not has_tools):
        return "direct"
    if related:
        return "partial"
    return "missing" if has_evidence else "unknown"


def match(job: JobSnapshot, library: EvidenceLibrary) -> MatchReport:
    reports = []
    direct_by_record: dict[str, list[Requirement]] = {record.id: [] for record in library.records}
    partial_by_record: dict[str, list[Requirement]] = {record.id: [] for record in library.records}
    for requirement in job.requirements:
        has_tools = bool(requirement.named_tools)
        related_ids: list[str] = []
        exact_ids: list[str] = []
        for record in library.records:
            related, exact = _matching_facts(requirement, record.facts)
            related_ids.extend(related)
            exact_ids.extend(exact)
            if exact or (related and not has_tools):
                direct_by_record[record.id].append(requirement)
            elif related:
                partial_by_record[record.id].append(requirement)

        tool_coverage = None
        if has_tools:
            tool_coverage = "direct" if exact_ids else ("missing" if library.records else "unknown")
        reports.append(RequirementMatch(
            requirement_id=requirement.id,
            level=requirement.level,
            capability=requirement.capability,
            named_tools=requirement.named_tools,
            coverage=_coverage(
                related_ids, exact_ids, has_tools=has_tools, has_evidence=bool(library.records)
            ),
            capability_evidence_ids=tuple(sorted(related_ids)),
            named_tool_coverage=tool_coverage,
            named_tool_evidence_ids=tuple(sorted(exact_ids)),
        ))

    ranking = []
    for record in library.records:
        direct = direct_by_record[record.id]
        partial = partial_by_record[record.id]
        score = 2 * sum(WEIGHTS[item.level] for item in direct) + sum(
            WEIGHTS[item.level] for item in partial
        )
        if score:
            ranking.append(RankedRecord(
                record_id=record.id,
                score=score,
                direct_requirement_ids=tuple(item.id for item in direct),
                partial_requirement_ids=tuple(item.id for item in partial),
            ))

    return MatchReport(
        job_id=job.id,
        job_version=job.version,
        description_sha256=job.description_sha256,
        requirements=tuple(reports),
        ranked_records=tuple(sorted(ranking, key=lambda item: (-item.score, item.record_id))),
    )
