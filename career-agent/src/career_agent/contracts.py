"""Version 1 records for the offline matching baseline."""

import hashlib
import re
from typing import Annotated, Iterable, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, model_validator

RecordID = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]*$")]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
SourceText = Annotated[str, StringConstraints(pattern=r"\S")]
SHA256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


def _require_unique(ids: Iterable[str], label: str) -> None:
    values = list(ids)
    if len(values) != len(set(values)):
        raise ValueError(f"Duplicate {label} IDs")


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Requirement(Contract):
    id: RecordID
    capability: Label
    level: Literal["required", "responsibility", "preferred", "example"]
    source_phrase: SourceText
    named_tools: tuple[Label, ...] = ()


class JobSnapshot(Contract):
    schema_version: Literal["1.0"]
    id: RecordID
    version: int = 1
    employer: Label
    title: Label
    location: Label | None = None
    source: Label
    source_url: HttpUrl | None = None
    captured_at: AwareDatetime
    listing_state: Literal["unknown", "active", "closed"] = "unknown"
    description: SourceText
    requirements: tuple[Requirement, ...]

    @property
    def description_sha256(self) -> str:
        return hashlib.sha256(self.description.encode("utf-8")).hexdigest()

    @model_validator(mode="after")
    def check_requirements(self) -> "JobSnapshot":
        if self.version < 1:
            raise ValueError("Job snapshot version must be positive")
        _require_unique((requirement.id for requirement in self.requirements), "requirement")
        raw_text = re.sub(r"\s+", " ", self.description)
        for requirement in self.requirements:
            excerpt = re.sub(r"\s+", " ", requirement.source_phrase.strip())
            if excerpt not in raw_text:
                raise ValueError(f"Requirement {requirement.id} must quote the job description")
        return self


class EvidenceSource(Contract):
    reference: Label
    section: Label
    sha256: SHA256


class EvidenceFact(Contract):
    id: RecordID
    assertion: SourceText
    capabilities: tuple[Label, ...]
    technologies: tuple[Label, ...] = ()
    source: EvidenceSource
    verification: Literal["user_supplied", "verified"]


class EvidenceRecord(Contract):
    id: RecordID
    kind: Literal["experience", "project", "leadership", "education", "skill"]
    title: Label
    facts: Annotated[tuple[EvidenceFact, ...], Field(min_length=1)]


class EvidenceLibrary(Contract):
    schema_version: Literal["1.0"]
    records: tuple[EvidenceRecord, ...]

    @model_validator(mode="after")
    def check_ids(self) -> "EvidenceLibrary":
        _require_unique((record.id for record in self.records), "record")
        _require_unique((fact.id for record in self.records for fact in record.facts), "evidence")
        return self


class DraftClaim(Contract):
    id: RecordID
    text: SourceText
    evidence_ids: tuple[RecordID, ...]

    @model_validator(mode="after")
    def check_evidence_ids(self) -> "DraftClaim":
        if not self.evidence_ids:
            raise ValueError("A draft claim needs at least one evidence ID")
        _require_unique(self.evidence_ids, "claim evidence")
        return self


def validate_claim_references(claim: DraftClaim, library: EvidenceLibrary) -> None:
    """Check citation IDs within the supplied snapshot. This does not verify claim text."""
    known = {fact.id for record in library.records for fact in record.facts}
    missing = sorted(set(claim.evidence_ids) - known)
    if missing:
        raise ValueError(f"Claim {claim.id} references unknown evidence: {', '.join(missing)}")
