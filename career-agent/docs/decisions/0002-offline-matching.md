# ADR 0002: Typed evidence and offline matching

Step 0.3 uses Pydantic to validate versioned JSON at the CLI boundary. A job
snapshot includes the full description, timestamp, normalized requirements and
source excerpts. The CLI checks excerpts against the description and computes a
SHA-256 hash of the exact UTF-8 description. Each evidence fact records its
assertion, verification status, source section and source file hash. The source
reference is metadata for review. The matcher does not open any source paths.

A record groups facts about one experience or project. Capability labels match
exactly after normalizing case and whitespace. For a requirement with named
tools, direct coverage needs at least one listed tool on the same fact as the
capability. A capability match without that tool yields partial coverage and a
named tool gap. A missing result means the supplied library had no matching
evidence. An empty library yields unknown coverage.

For ranking, required criteria weigh 3, responsibilities 2, and preferences
and examples 1. For each record and requirement, direct coverage earns twice
the weight and partial coverage earns the weight. Multiple facts can explain a
match but score only once per requirement. Zero-score records are omitted.
Ties sort by record ID. This baseline uses manually assigned labels and weights
that can be evaluated on later examples.

A draft claim must cite one or more unique fact IDs in its evidence library.
A valid reference establishes that the cited fact exists. Later resume
validation and human review will assess whether the text is supported.
User-supplied assertions retain their verification status in the source
records. Matching and citation validation do not change that status.
