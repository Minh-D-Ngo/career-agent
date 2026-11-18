# Career Agent

The Python project is in the inner [`career-agent/`](career-agent/) folder,
which contains `pyproject.toml`. If you opened the outer repository in VS Code,
start in the repository root and run:

```powershell
cd career-agent
python -m pip install -e .
python -m career_agent.cli status
```

Run the last two commands directly if your terminal is already in the folder
containing `pyproject.toml`. Use the same Python interpreter for installation
and for running the CLI.

See the [project README](career-agent/README.md) for the example commands and
tests. Run them from the folder containing `pyproject.toml`.
