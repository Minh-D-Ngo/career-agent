"""Read optional settings from the process environment without exposing secrets."""

from dataclasses import dataclass, field
import os
from typing import Mapping


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None = field(default=None, repr=False)
    openai_model: str | None = None

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        source = os.environ if environ is None else environ
        return cls(
            openai_api_key=source.get("OPENAI_API_KEY") or None,
            openai_model=source.get("OPENAI_MODEL") or None,
        )
