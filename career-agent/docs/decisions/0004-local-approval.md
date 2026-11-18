# ADR 0004: Local draft approval and submission history

Approval requires an explicit CLI command. It runs the deterministic draft
workflow from the supplied job and evidence inputs and compares the result
with the three reviewed files byte for byte. Any edit, missing file, or
empty draft stops approval. This lets the first slice reuse the offline
validator. A future model workflow will need to validate its saved proposal
without regenerating the wording.

SQLite stores the exact draft and report bytes, the draft ID, the Markdown
SHA-256, the UTC approval timestamp, and the normalized job snapshot. A
job ID and version identify one immutable snapshot. If the snapshot changes,
increment the job version before generating and approving another draft.
Approving the same bundle twice returns the existing ID and timestamp.
New approvals leave prior versions intact.

Recording a submission is a separate command. It can link only to an approved
resume ID, which in turn identifies the job snapshot. Step 1.2 stores one
submission per approved resume ID. Repeating the same details is safe, and
a conflicting repeat is rejected. The CLI records the user's report of
submission. It does not contact employers.
