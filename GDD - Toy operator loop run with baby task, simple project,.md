---
format: note
tags:
  - topic/GDD
type: project
status: active
created: 2026/04/08, 07:04:46
modified: 2026/04/08, 07:04:34
title: GDD - Toy operator loop run with baby task, simple project,
project: '[[GDDP]]'
---
## [[GDDO - operator practice manual run checklist]]
- add --verbose or --dry-run to a CLI
- add one missing unit test
- rename a confusing function
- extract one duplicated helper
- add a healthcheck endpoint
- move one hardcoded path to env/config

Good project types:

- single-file CLI
- tiny Flask/FastAPI app
- static site generator
- cron script repo
- scraper/tooling repo

Avoid for now:

- auth
- migrations
- multi-service repos
- external APIs
- async workers
