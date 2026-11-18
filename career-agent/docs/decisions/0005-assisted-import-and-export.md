# ADR 0005: Assisted imports, source selection, and DOCX export

Document parsing reads the selected files locally. Only an explicit
`--use-openai` command sends extracted text or selected fields to OpenAI.
The import uses structured responses and checks quoted text against the
local source. Technology names in imported evidence must occur in the
quoted assertion. Matching labels and metadata still need user review.
The reusable evidence library keeps source hashes and source paths. An
incremental import preserves unchanged sources and records outside the
requested updates and writes a new file for review.

Model-assisted drafting selects from fact IDs already shortlisted by the
offline matcher. The graph rejects unknown and duplicate IDs and uses the
same fact wording and citation rules as the offline draft. Approval rebuilds
the proposed draft from the saved selection locally to compare the reviewed
files. Freeform rewriting is deferred until there is a reliable way to
validate changes to the wording.

DOCX rendering runs locally against the stored, hash-checked approved
Markdown. The export adds Word headings and bullets and removes review
annotations. The approved source bundle remains the version stored in
SQLite. PDF export needs a dependable local conversion path.
