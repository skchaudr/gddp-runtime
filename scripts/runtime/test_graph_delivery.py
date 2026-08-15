"""Tests for graph_delivery: local bare-repo fixtures only, never real repos."""
from __future__ import annotations
import os
import subprocess
import pytest
from scripts.runtime import graph_delivery as gd

_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}

def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], check=True, env=_ENV,
                           capture_output=True, text=True).stdout.strip()

def _commit(work, name, content, base=None):
    _git(work, "checkout", "-B", name, *([base] if base else []))
    if content is None:
        _git(work, "commit", "--allow-empty", "-m", name)
    else:
        (work / "f.txt").write_text(content)
        _git(work, "add", "f.txt")
        _git(work, "commit", "-m", name)
    return _git(work, "rev-parse", "HEAD")

def _push(work, refs):
    for ref, sha in refs.items():
        _git(work, "push", "origin", f"{sha}:refs/heads/{ref}")

def _tmp_refs(work):
    return _git(work, "for-each-ref", "refs/gddp-delivery-tmp")

@pytest.fixture
def spine(tmp_path):
    origin, work = tmp_path / "o.git", tmp_path / "o-work"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    subprocess.run(["git", "init", str(work)], check=True, capture_output=True)
    _git(work, "remote", "add", "origin", str(origin))
    c1 = _commit(work, "b1", "n1")
    c2 = _commit(work, "b2", None, c1)       # node-02 attempt-a: EMPTY
    c3 = _commit(work, "b3", "n2", c2)       # node-02 attempt-b: content, delivery
    cf = _commit(work, "bf", "foreign", c1)  # foreign graph's own node
    _push(work, {
        "gddp/result-j1-j1-node-01-attempt-0-aaaa1111": c1,
        "gddp/result-j2-j2-node-02-attempt-0-bbbb2222": c2,
        "gddp/result-j3-j3-node-02-attempt-1-cccc3333": c3,
        "gddp/result-jf-jf-node-99-foreign-attempt-0-eeee5555": cf,
    })
    d = tmp_path / "cfg" / "graphs" / "testproj"
    d.mkdir(parents=True)
    (d / "project.yaml").write_text(
        "project_id: testproj\nproject_name: t\nrepo: x\nnodes:\n- id: node-01\n- id: node-02\n")
    return work, d.parent.parent, c1, c2, c3, cf

def test_delivery_excludes_empty_and_foreign_commits(spine):
    work, cfg, c1, c2, c3, cf = spine
    sha, candidates = gd.find_delivery_commit(work, cfg, "testproj")
    shas = {s for _, _, s in candidates}
    assert sha == c3 and c2 not in shas and cf not in shas
    assert _tmp_refs(work) == ""  # private fetch namespace left clean on success

def test_forked_spine_fails_loudly(spine):
    work, cfg, c1, c2, c3, cf = spine
    a = _commit(work, "fa", "x", c1)
    b = _commit(work, "fb", "y", c1)
    _push(work, {
        "gddp/result-j4-j4-node-02-attempt-2-dddd4444": a,
        "gddp/result-j5-j5-node-02-attempt-3-eeee6666": b,
    })
    with pytest.raises(gd.GraphDeliveryError, match="forked"):
        gd.find_delivery_commit(work, cfg, "testproj")
    assert _tmp_refs(work) == ""  # namespace also cleared when the call raises

def test_publish_pushes_and_verifies(spine):
    work, cfg, c1, c2, c3, cf = spine
    branch, sha = gd.publish(work, cfg, "testproj")
    assert sha == c3 and branch == "review/testproj"
    assert sha in _git(work, "ls-remote", "--heads", "origin", branch)

def test_cleanup_refuses_without_publish(spine):
    work, cfg, c1, c2, c3, cf = spine
    with pytest.raises(gd.GraphDeliveryError, match="does not exist"):
        gd.cleanup_transport_refs(work, cfg, "testproj", delete=True)
    assert "gddp/result" in _git(work, "ls-remote", "--heads", "origin")  # nothing deleted

def test_cleanup_refuses_review_branch_missing_delivery_commit(spine):
    work, cfg, c1, c2, c3, cf = spine
    _push(work, {"review/testproj": c1})  # published before node-02's real work landed
    with pytest.raises(gd.GraphDeliveryError, match="does not contain the delivery commit"):
        gd.cleanup_transport_refs(work, cfg, "testproj", delete=True)
    assert "gddp/result" in _git(work, "ls-remote", "--heads", "origin")  # nothing deleted

def test_cleanup_dry_run_lists_without_deleting(spine, capsys):
    work, cfg, c1, c2, c3, cf = spine
    gd.publish(work, cfg, "testproj")
    before = _git(work, "ls-remote", "--heads", "origin")
    targets = gd.cleanup_transport_refs(work, cfg, "testproj", delete=False)
    assert all("foreign" not in t for t in targets)
    assert f"{len(targets)} ref(s) would be deleted" in capsys.readouterr().out
    assert _git(work, "ls-remote", "--heads", "origin") == before
