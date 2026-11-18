"""Convert unstructured local documents into reviewable job and evidence proposals."""

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .contracts import EvidenceFact, EvidenceLibrary, EvidenceRecord, EvidenceSource, JobSnapshot, Requirement
from .documents import read_document
from .model import ModelError, ask


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProposedRequirement(Proposal):
    capability: str
    level: Literal["required", "responsibility", "preferred", "example"]
    source_phrase: str
    named_tools: list[str]


class ProposedJob(Proposal):
    single_posting: bool
    employer: str | None
    title: str | None
    location: str | None
    requirements: list[ProposedRequirement]


class ProposedFact(Proposal):
    assertion: str
    capabilities: list[str]
    technologies: list[str]


class ProposedRecord(Proposal):
    title: str
    kind: Literal["experience", "project", "leadership", "education", "skill"]
    facts: list[ProposedFact]


class ProposedEvidence(Proposal):
    records: list[ProposedRecord]


def _source_text(text: str, quote: str) -> str:
    # Preserve words and punctuation, allowing only PDF/DOCX whitespace differences.
    candidate = " ".join(quote.split())
    if not candidate or candidate not in " ".join(text.split()):
        raise ModelError("A proposed quotation is missing from its source. No proposal was saved.")
    return candidate


def _source(path: Path) -> tuple[bytes, str]:
    raw, text = read_document(path)
    if len(text) > 60_000:
        raise ModelError(f"{path.name} is too long for one import. Split it into smaller files.")
    return raw, text


def import_job(
    path: Path, job_id: str, version: int, library: EvidenceLibrary | None,
    *, employer: str | None = None, title: str | None = None,
) -> JobSnapshot:
    _, text = _source(path)
    labels = sorted({
        label for record in (library.records if library else ())
        for fact in record.facts for label in fact.capabilities
    })
    proposed = ask(
        ProposedJob,
        "Extract one job posting. Set single_posting false for multiple or ambiguous postings. "
        "Use null for missing metadata or use supplied employer and title. Quote each requirement "
        "verbatim. Use existing capability labels where equivalent. Split required conjunctions "
        "into separate requirements. Named tools within one requirement are alternatives.",
        {"posting": text, "existing_capability_labels": labels, "employer": employer, "title": title},
    )
    if not proposed.single_posting:
        raise ModelError("Use an input file containing exactly one job posting.")
    employer, title = employer or proposed.employer, title or proposed.title
    if not employer or not title or not proposed.requirements:
        raise ModelError("The proposal needs an employer, title, and requirements. Supply missing metadata locally.")
    return JobSnapshot(
        schema_version="1.0", id=job_id, version=version, employer=employer, title=title,
        location=proposed.location, source=str(path.resolve()), captured_at=datetime.now(timezone.utc),
        description=text, requirements=tuple(
            Requirement(
                id=f"req_{index:03}", capability=item.capability, level=item.level,
                source_phrase=_source_text(text, item.source_phrase), named_tools=tuple(item.named_tools),
            )
            for index, item in enumerate(proposed.requirements, start=1)
        ),
    )


def import_evidence(paths: list[Path], existing: EvidenceLibrary | None) -> EvidenceLibrary:
    resolved = [path.resolve() for path in paths]
    if len(set(resolved)) != len(resolved):
        raise ModelError("List each source file once.")
    previous = existing.records if existing else ()
    source_hashes: dict[str, set[str]] = {}
    for record in previous:
        for fact in record.facts:
            source_hashes.setdefault(fact.source.reference, set()).add(fact.source.sha256)

    changed = {}
    for path in resolved:
        raw, text = _source(path)
        digest = hashlib.sha256(raw).hexdigest()
        if source_hashes.get(str(path)) != {digest}:
            changed[path] = (digest, text)

    refs = {str(path) for path in changed}
    records = []
    for record in previous:
        remaining = tuple(fact for fact in record.facts if fact.source.reference not in refs)
        if remaining:
            records.append(record.model_copy(update={"facts": remaining}))

    for path, (digest, text) in changed.items():
        response = ask(
            ProposedEvidence,
            "Group resume or project evidence by its real record. Copy accomplishments or skills "
            "as verbatim excerpts. Skip identity, contact details, aspirations, and job requirements. "
            "Label capabilities demonstrated by that excerpt. List only technologies named in it. "
            "For skills inventories, classify the record as skill and never imply project usage.",
            {"source_text": text},
        )
        if not response.records or any(not record.facts for record in response.records):
            raise ModelError(f"No usable evidence was proposed from {path.name}.")
        source = EvidenceSource(
            reference=str(path), section="Extracted document text", sha256=digest,
        )
        labels_seen: set[str] = set()
        for record in response.records:
            identifier = hashlib.sha256(f"{path}\0{record.kind}\0{record.title}".encode()).hexdigest()[:16]
            if identifier in labels_seen:
                raise ModelError(f"Duplicate proposed record in {path.name}.")
            labels_seen.add(identifier)
            facts = []
            for fact in record.facts:
                assertion = _source_text(text, fact.assertion)
                if any(
                    not tool.strip() or not re.search(
                        rf"(?<!\w){re.escape(tool.strip())}(?!\w)", assertion, re.IGNORECASE,
                    )
                    for tool in fact.technologies
                ):
                    raise ModelError(f"A proposed technology is missing from the cited text in {path.name}.")
                facts.append(EvidenceFact(
                    id=f"fact_{identifier}_{hashlib.sha256(assertion.encode()).hexdigest()[:12]}",
                    assertion=assertion, capabilities=tuple(fact.capabilities),
                    technologies=tuple(fact.technologies), source=source, verification="user_supplied",
                ))
            records.append(EvidenceRecord(
                id=f"record_{identifier}", kind=record.kind, title=record.title, facts=tuple(facts),
            ))

    return EvidenceLibrary(schema_version="1.0", records=tuple(records))
