---
description: Run independent evaluation and generate SHA-targeted receipt
subagent: reviewer
model: google/gemini-3.1-pro
---

Evaluate attempt for node "$1" in project "$2".
1. Extract target commit SHA from the latest job row for node $1.
2. Execute node acceptance criteria test suite / validation script against that exact SHA.
3. Verify integrity lanes: static check, execution pass, artifact presence.
4. Output structured receipt bound to target commit SHA.
5. Do NOT flip node graph status; report receipt for human review.
