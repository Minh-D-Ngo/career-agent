# Career Agent

A local-first career assistant, currently at **Step 1.2: local approval and history**.
The CLI can match evidence to a job, write a draft with reports, save the exact
approved version, and record a submission you made.

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

## Try an offline resume draft

Run this from the folder containing `pyproject.toml`, using a fresh output
directory for each run:

```powershell
career-agent draft --job data/examples/harbor-demo-job.json --evidence data/examples/harbor-demo-evidence.json --output-dir data/users/local/resumes/harbor-demo
```

Open the three files in VS Code:

- `draft.md` contains the draft bullets and their claim IDs.
- `evidence.json` maps each claim to the original assertion, file section,
  source hash, and verification status.
- `gaps.json` shows coverage across the supplied evidence library, including
  broader capabilities and missing named tools.

The draft reuses evidence text from up to three ranked records and stays in
`DRAFT` for review. A report entry marked `supported` means the text matches its
cited assertion. Check the separate verification status before relying on a
claim. [See how the graph works](docs/decisions/0003-offline-drafting.md).

## Approve a draft and record a submission

For a practice run in PowerShell, use a separate ignored demo workspace. Run
these commands from the folder containing `pyproject.toml`:

```powershell
$demo = 'data/users/demo'
$job = 'data/examples/harbor-demo-job.json'
$evidence = 'data/examples/harbor-demo-evidence.json'
$draft = "$demo/resumes/harbor-demo"
python -m career_agent.cli draft --job $job --evidence $evidence --output-dir $draft
```

Open `draft.md`, `evidence.json`, and `gaps.json` in VS Code. Once you've
reviewed them, approve that exact version:

```powershell
python -m career_agent.cli approve --workspace $demo --draft-dir $draft --job $job --evidence $evidence
python -m career_agent.cli history --workspace $demo
```

History shows an approved version and application status `NOT_RECORDED`.
To simulate recording a submission in the fictional demo, paste the ID printed
by `approve` into the following command:

```powershell
$resumeId = 'paste-approved-resume-id'
python -m career_agent.cli record-application --workspace $demo --resume $resumeId --submitted-on 2026-01-16 --method 'Company website'
python -m career_agent.cli history --workspace $demo
```

For a real job, run `record-application` after submitting the application
yourself. History will show `USER_REPORTED_SUBMITTED`. The workspace database
stores the approved bytes, their source job snapshot, and application history.
To revise a draft, generate and review a fresh bundle before approving.
[See the storage decisions](docs/decisions/0004-local-approval.md).

## Tests

After installing the package and its dependencies, the standard-library
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
- Step 1.1: offline LangGraph draft with evidence and gap reports.
- Step 1.2: explicit approval, immutable versions, and local submission records.
- Step 1.3: optional model use and document export.

Never commit private resumes, job snapshots, application history, or secrets.
`.gitignore` covers the default private directory and `.env`; it does not
protect already tracked files or arbitrary external workspace paths.
