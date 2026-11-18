"""Let the model select from locally ranked evidence by ID."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .contracts import EvidenceLibrary, JobSnapshot
from .drafting import DraftValidationError, candidate_facts
from .matching import match
from .model import ask


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selected_fact_ids: list[str]


def suggest_selection(job: JobSnapshot, library: EvidenceLibrary) -> tuple[str, ...] | None:
    candidates = candidate_facts(match(job, library), library)
    if not candidates:
        return None
    response = ask(
        Selection,
        "Select and order the candidate fact IDs most useful for the job. Keep complementary "
        "facts and omit duplication. Select at least one ID. Return only supplied IDs.",
        {
            "title": job.title,
            "requirements": [
                {
                    "capability": requirement.capability, "level": requirement.level,
                    "named_tools": requirement.named_tools,
                }
                for requirement in job.requirements
            ],
            "facts": [{"id": fact.id, "assertion": fact.assertion} for fact in candidates],
        },
    )
    return tuple(response.selected_fact_ids)


def read_saved_selection(draft_dir: Path) -> tuple[str, ...] | None:
    try:
        report = json.loads((draft_dir / "evidence.json").read_bytes())
    except (ValueError, UnicodeError) as exc:
        raise DraftValidationError("The reviewed evidence report is not valid JSON.") from exc
    if not isinstance(report, dict):
        raise DraftValidationError("The reviewed evidence report is not a JSON object.")
    if "selected_fact_ids" not in report:
        return None
    ids = report["selected_fact_ids"]
    if not isinstance(ids, list) or not all(isinstance(value, str) for value in ids):
        raise DraftValidationError("The reviewed evidence report has invalid fact IDs.")
    return tuple(ids)
