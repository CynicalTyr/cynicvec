# Contributing

1. Keep the public tree free of secrets, LAN IPs, and live operator paths.
2. Add or extend a test under `tests/` for behavior changes.
3. Run:

```bash
python3 -m unittest discover -s tests -q
```

4. Do not expand scope into a new vector database. This kernel stays a
   cache policy: SQL stays source of truth, `save()` keeps the shrink
   guard, and there is no MCP that loads a `.tvim` from a URL.

Issues: one problem per ticket. Feature ideas: say who it helps and the
60-second demo that would prove it.
