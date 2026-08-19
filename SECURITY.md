# Security

- Never open issues that paste live API keys, cookies, or `.env` values.
- This project is a **library**, not a hosted vector database.
- If you find a way a dual-write can replace a large `.tvim` without
  hitting the shrink guard, or a tool that loads a `.tvim` from a URL
  beside secrets, file a private advisory if the GitHub repo has them
  enabled; otherwise an issue with a **redacted** repro.

Do not ask maintainers to add `save(force=True)` or
`load_tvim_from_url` “just for debugging.” The ANN is a cache. Forcing
the write is how overnight backfill dies. Loading untrusted `.tvim`
files is data, not a plugin — keep it out of the secret process.

Fail-open on missing ANN must not be copied onto auth or allowlists.
