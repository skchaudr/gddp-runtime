---
description: Safely edit or add criteria to a GDDP node YAML
subagent: worker
inheritContext: true
---

Safely update GDDP node "$1" in project "$2".
1. Python `yaml.safe_load` node at `graphs/$2/nodes/$1.yaml`.
2. Apply changes: $3. NEVER modify the `status` field.
3. If node has `depends_on`, ensure initial state is `pending`, not `ready`.
4. Output proposed YAML patch to main thread before writing.
5. Save using `yaml.safe_dump(..., sort_keys=False, allow_unicode=True, width=120)`.
6. Run `~/bin/gddp node validate --project $2` and report exact output.
