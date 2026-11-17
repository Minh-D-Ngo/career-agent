# Career Agent

A local-first career assistant, currently at **Step 0.3: offline evidence matching**.
The CLI can initialize a private workspace and rank documented experience
against a manually normalized job snapshot.

## Setup

Python 3.10 or newer is required. In VS Code, open the project folder that
contains `pyproject.toml`. In a fresh clone of this repository, that is the
inner `career-agent/` folder. Run these commands from that folder:

```sh
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e .
career-agent --help
career-agent status
career-agent init --workspace data/users/local
```

`status` shows which features are available.
Initialization creates empty subdirectories without replacing existing files.
Select a different path for each person, or place the workspace outside the
repository. See `data/README.md` for the privacy boundary.

Optional environment variables are `OPENAI_API_KEY` and `OPENAI_MODEL`.
They are not required for any current command. Set them in your shell when
needed; `.env.example` documents their names but is not automatically loaded.
No current command makes an API call.

## Try the matching baseline

Run this from the project folder in PowerShell or a Unix shell:

```sh
career-agent match --job data/examples/harbor-demo-job.json --evidence data/examples/harbor-demo-evidence.json
```

The fictional Reading Room Inventory project ranks first. Its spreadsheet
dashboard partially covers the reporting requirement, with Looker and
Metabase both missing. The JSON includes matching evidence IDs and the job
description hash. Labels are normalized by case and whitespace. See
[the matching decisions](docs/decisions/0002-offline-matching.md) for the scoring
rule and the limits of citation validation.

## Tests

After installing the package and its Pydantic dependency, the standard-library
test runner works offline without an API key:

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

On PowerShell, set `$env:PYTHONPATH = 'src'` before running the command without
the `PYTHONPATH=src` prefix. Alternatively, after installing the optional
`test` extra (`python -m pip install -e '.[test]'`), run `python -m pytest`.
Installing packages may need network access; executing the tests does not.

## Roadmap

- Step 0.1: acceptance specification supplied by the owner.
- Step 0.2: package, CLI, environment settings, workspace convention, offline tests.
- Step 0.3: typed data contracts and an inspectable deterministic baseline.
- Step 1.1 onward: offline LangGraph slice, then review/persistence and optional model/export.

Never commit private resumes, job snapshots, application history, or secrets.
`.gitignore` covers the default private directory and `.env`; it does not
protect already tracked files or arbitrary external workspace paths.
