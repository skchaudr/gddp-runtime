"""
canary_local_executor.py — Trivial GDDP_LOCAL_SUBPROCESS_ARGV target for the
Node 2 (direct-executor-round-trip) stabilization loop.

Not production dispatch logic. This is the "executor" for a synthetic,
repeatable canary: it ignores the NodePacket on stdin and prints a fixed,
valid unified diff to stdout that creates one new marker file. The reconciler
applies this diff in an isolated worktree at the dispatch-time base commit, so
the same diff must apply cleanly every fresh run — it targets a path that does
not exist in the repo, never a real deliverable file.

Real work correctness is intentionally out of scope here: this only proves the
transport (dispatch -> poll -> collect -> apply -> commit -> evaluate), not
node acceptance criteria.
"""

import sys

_PATCH = """diff --git a/docs/canary-stabilization-marker.md b/docs/canary-stabilization-marker.md
new file mode 100644
index 0000000..0000000
--- /dev/null
+++ b/docs/canary-stabilization-marker.md
@@ -0,0 +1,3 @@
+# Canary Stabilization Marker
+
+Synthetic artifact produced by the Node 2 direct-executor stabilization loop.
"""


def main() -> int:
    sys.stdout.write(_PATCH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
