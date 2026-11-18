# ADR 0003: Offline resume draft graph

Step 1.1 runs three LangGraph nodes in sequence. The first calls the Step 0.3
matcher. The second takes up to three ranked records and copies the facts that
cover at least one requirement. The third validates citations and assembles
the draft and reports. Keeping selection separate from validation makes it
possible to test invalid claims independently of the component that proposes
them.

The draft generator accepts only verbatim assertions with valid evidence IDs.
A claim that adds a metric or technology fails validation before the CLI writes
any files. The evidence report includes the exact assertion and source metadata.
The Markdown display escapes formatting and flattens whitespace so imported
text stays readable. A matching assertion may still be user supplied and need
review. Gap coverage reflects the entire input library and may include evidence
that did not fit in the draft.

The graph runs in memory, with LangSmith tracing disabled even when enabled in
the shell. For identical inputs it produces the same content and draft ID.
The CLI writes the three review artifacts into a new directory and rejects
existing output paths. Every result starts in DRAFT. Step 1.2 will add explicit
approval and persistence for an approved version.
