# ADR 0001: Minimal offline foundation

Status: accepted for Step 0.2.

Use Python's argparse and standard library for the CLI and environment settings.
The installable package has no runtime dependencies. Add Pydantic when the
Step 0.3 contracts are defined and LangGraph when the graph is built. This
keeps today's behavior easy to understand and avoids committing to unused
interfaces. `pytest` is an optional test dependency; the same tests also run
with standard-library unittest without downloading anything.

Personal workspaces are chosen explicitly and may be outside the repository.
The repository ignores `data/users/`; initialization only creates directories
and never overwrites files. Environment settings are read from the process, not
an automatically loaded .env file. A key is optional and is excluded from the
settings object's representation. No API calls are made.

Future contracts should retain source and evidence IDs, snapshots and review
states; exact fields remain for Step 0.3. Job discovery, resume approval and
submission are distinct events. Avoid claiming automated evidence checks prove
semantic truth: human review remains essential.
