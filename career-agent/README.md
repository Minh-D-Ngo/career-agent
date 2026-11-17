# Career Agent

A local-first career assistant, currently at **Step 0.2: foundation**. The CLI
can report status and create a private workspace. Resume generation, data
contracts, LangGraph, persistence, and model calls are not implemented.

## Setup

Python 3.10 or newer is required. From this directory:

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

`status` prints `Career Agent foundation is ready. No resume workflow is implemented yet.`
Initialization creates empty subdirectories without replacing existing files.
Select a different path for each person, or place the workspace outside the
repository. See `data/README.md` for the privacy boundary.

Optional environment variables are `OPENAI_API_KEY` and `OPENAI_MODEL`.
They are not required for any current command. Set them in your shell when
needed; `.env.example` documents their names but is not automatically loaded.
No current command makes an API call.

## Tests

The standard-library test runner needs no network or API key:

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
