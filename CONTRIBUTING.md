# Contributing

1. Keep the public tree free of secrets, LAN IPs, and live operator paths.
2. Add or extend a test under `tests/` for behavior changes.
3. Run:

```bash
python3 -m unittest discover -s tests -q
```

4. Do not expand scope into a new agent framework. This kernel stays small
   so people can drop it into *their* loop.

Issues: one problem per ticket. Feature ideas: say who it helps and the
60-second demo that would prove it.
