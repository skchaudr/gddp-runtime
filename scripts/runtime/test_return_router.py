"""
test_return_router.py — Tests for the return router logic.
"""

import sys
from pathlib import Path

# Add the parent directory to sys.path to allow importing from the current package
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.runtime.return_router import parse_node_id, validate_repo

def test_parse_node_id():
    print("Testing parse_node_id...")

    # Standard case
    body1 = "This PR implements the feature.\n\nnode: auth-boundary\njob: job_123"
    assert parse_node_id(body1) == "auth-boundary"

    # Case insensitivity
    body2 = "Fixed stuff.\nNODE: data-sync\n"
    assert parse_node_id(body2) == "data-sync"

    # Extra whitespace
    body3 = "node:    scan-vault-core   "
    assert parse_node_id(body3) == "scan-vault-core"

    # Missing tag
    body4 = "No node tag here."
    assert parse_node_id(body4) is None

    # Tag not on its own line (should fail based on ^ requirement)
    body5 = "The node: tag is here"
    assert parse_node_id(body5) is None

    print("  → parse_node_id: OK")

def test_validate_repo():
    print("Testing validate_repo...")

    assert validate_repo("skchaudr/vault-doctor") is True
    assert validate_repo("other/repo") is False

    print("  → validate_repo: OK")

if __name__ == "__main__":
    try:
        test_parse_node_id()
        test_validate_repo()
        print("\nAll tests passed!")
    except AssertionError as e:
        print(f"\nTest failed!")
        sys.exit(1)
