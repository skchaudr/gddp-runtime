"""
canary_local_executor_slow.py — Deliberately slow variant of
canary_local_executor.py, used only to test the Node 2 stabilization loop's
controlled mid-execution interruption/retry path. Sleeps long enough to be
killed before it can print the patch, so the executor session reaches
'failed' (not 'completed') and exercises automatic retry allocation.
"""

import sys
import time


def main() -> int:
    time.sleep(30)
    sys.stdout.write("# never reached if killed before this point\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
