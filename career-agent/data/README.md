# Data and private workspaces

`templates/` contains blank starting points. `examples/` contains synthetic
job and evidence records for offline matching. Use them as a guide when
creating your own JSON inputs inside your ignored workspace.

Choose an explicit personal workspace, for example:

```sh
career-agent init --workspace data/users/local
```

The command creates `imports`, `resumes`, `projects`, `jobs`, and
`applications`. It preserves existing files. Put original documents in
`imports/`; do not commit personal records, application history, databases,
or generated documents. `/data/users/` is ignored in this repository. An
external workspace can provide stronger separation, but check the Git ignore
rules of any repository that contains it. Git ignore does not remove already
tracked files or protect backups. Store workspace state there as well. The
matcher validates normalized JSON. Prepare those files and their source
references manually.
