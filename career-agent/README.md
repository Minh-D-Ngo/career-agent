# Career Agent

A local-first career assistant, currently at **Step 1.3: optional document import,
model-assisted selection, and DOCX export**. You can still match, draft, and
approve using existing JSON entirely offline.

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

Set `OPENAI_API_KEY` and optionally `OPENAI_MODEL` in your shell for the
explicit `--use-openai` commands. `.env.example` documents their names.
The app reads the shell environment.

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

## Use your own files in VS Code

Keep your original resume, project descriptions, and individual job postings
in `data/users/local/imports/`. The import commands read UTF-8 TXT, Markdown,
DOCX, or text-based PDF files. Give `import-job` one posting per file. For
scanned PDFs, make a text copy or run OCR first.

From the folder containing `pyproject.toml`, install the optional extras:

```powershell
python -m pip install -e '.[model,documents]'
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'OpenAI API key' -AsSecureString)).Password
```

First, you can try the optional import with `data/examples/harbor-demo-source.md`
and `data/examples/harbor-demo-posting.txt` in place of your originals. For real
documents, review what you are sending. `import-evidence` sends extracted
resume and project text to OpenAI, including contact details if they appear
in the text. Use a redacted copy if needed. `import-job` sends the posting
text, any employer/title overrides, and capability labels from the cited
library. The SDK requests structured output with `store=false`.

Set the following file names to match your files, then run each command after
the previous one succeeds:

```powershell
$localWorkspace = 'data/users/local'
$evidenceLibrary = "$localWorkspace/projects/evidence-library.json"
$jobSnapshot = "$localWorkspace/jobs/first-job-v1.json"

python -m career_agent.cli import-evidence --use-openai --source "$localWorkspace/imports/resume.docx" --source "$localWorkspace/imports/project-one.txt" --source "$localWorkspace/imports/project-two.txt" --output $evidenceLibrary
python -m career_agent.cli import-job --use-openai --source "$localWorkspace/imports/job-posting.txt" --job-id job_first_posting --evidence $evidenceLibrary --output $jobSnapshot
```

Review both JSON proposals in VS Code. Check the assertions, capability
labels, and the job's requirement levels before drafting. Evidence remains
marked `user_supplied`. The source hashes describe the original files. The
same evidence library can be used for every job. To add or refresh documents,
run `import-evidence` with `--existing $evidenceLibrary`, pass the sources
to update, and choose a new output filename. Unchanged sources and records
from other files are kept. Imported source identity uses the file's absolute
path, so moving a source makes it a new source.

```powershell
$draftFolder = "$localWorkspace/resumes/first-job-draft-01"
python -m career_agent.cli draft --job $jobSnapshot --evidence $evidenceLibrary --output-dir $draftFolder
```

That draft runs offline. To try model-assisted selection, add `--use-openai`
and choose a new output folder. This sends the role title, normalized
requirements, and shortlisted assertion text and IDs, then selects from
those IDs. The draft still uses the original evidence wording. Approval
uses the saved selection and works offline. Use the prior section's
`approve` command with your real job, evidence, workspace, and draft paths.

After approving, export a local Word copy using the ID printed by `approve`:

```powershell
$resumeId = 'paste-approved-resume-id'
python -m career_agent.cli export-docx --workspace $localWorkspace --resume $resumeId --output "$localWorkspace/resumes/first-job.docx"
```

DOCX is a simple formatted copy of the approved draft. Review the layout in
Word. Keep the exact file you submit in your workspace, since the history
currently links to the approved source bundle. See the [Step 1.3 design
notes](docs/decisions/0005-assisted-import-and-export.md).

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
- Step 1.3: opt-in OpenAI imports and evidence selection, plus local DOCX export.

Never commit private resumes, job snapshots, application history, or secrets.
`.gitignore` covers the default private directory and `.env`; it does not
protect already tracked files or arbitrary external workspace paths.
