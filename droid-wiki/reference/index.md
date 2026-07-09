# Reference

This section collects the contracts the rest of the wiki refers back to: the environment variables and config paths that point the runtime at its config checkout and credentials, the SQLite schema and Pydantic/dataclass models that define what state and verdicts look like, and the external dependencies the runtime expects on the host. Use these pages when you need the exact shape of a column, the name of an env var, or the minimum version of a library. The runtime has no separate config file: behavior is driven by environment variables plus the graph YAML in gddp-config, so the configuration page is the authoritative list of knobs.

- [Configuration](configuration.md) — every environment variable the runtime reads, its purpose, default, and whether it is required.
- [Data models](data-models.md) — the six SQLite tables, the Pydantic verdict models, and the dataclasses the graph reader and deterministic lane produce.
- [Dependencies](dependencies.md) — Python packages, external binaries, and the stdlib pieces the runtime relies on.

For how these pieces fit together at runtime, see the [architecture overview](../overview/architecture.md) and the [verification system](../systems/verification.md) page.
