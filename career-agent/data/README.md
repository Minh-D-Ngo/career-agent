# Data and private workspaces

`templates/` contains illustrative blank starting points, not validated schemas.
`examples/` is reserved for synthetic, non-identifying fixtures. Step 0.3 will
define the authoritative contracts and representative synthetic data.

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
tracked files or protect backups. Store workspace state there as well. No
profile selection, parsing, source hashing, or validation is implemented yet.
