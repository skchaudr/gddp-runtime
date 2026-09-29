"""Durable evidence for one verification invocation and its Pi lanes."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts.runtime.verification.receipt_sink import receipt_path


class EvaluationCapture:
    def __init__(self) -> None:
        self.path: Path | None = None
        self.errors: list[str] = []

    def error(self, exc: Exception) -> None:
        message = f"evaluation capture incomplete: {exc}"
        self.errors.append(message)
        print(message, file=sys.stderr)

    def write(self, path: Path, value) -> None:
        try:
            path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
        except (OSError, TypeError, ValueError) as exc:
            self.error(exc)

    @classmethod
    def start(cls, args, node: dict, graph: dict) -> EvaluationCapture:
        capture = cls()
        try:
            target = receipt_path(
                graph["project_id"], node["node_id"], base=args.receipt_dir,
                job_id=args.job_id, attempt=args.attempt,
            ).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            capture.path = Path(tempfile.mkdtemp(prefix=target.stem + ".capture-", dir=target.parent))
            for name, source in (("node.yaml", args.node_yaml), ("project.yaml", args.project_yaml),
                                 ("shape-profile.yaml", args.shape_profile)):
                if source:
                    (capture.path / name).write_bytes(source.read_bytes())
            head = subprocess.run(
                ["git", "-C", str(args.repo), "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=5, check=False,
            )
            capture.write(capture.path / "input.json", {
                "node": node, "project": graph, "repo": str(args.repo.resolve()),
                "evaluated_commit_sha": head.stdout.strip() if head.returncode == 0 else None,
                "merge_commit_sha": args.merge_commit_sha,
                "expected_base_commit_sha": args.expected_base_commit_sha,
                "job_id": args.job_id, "attempt": args.attempt,
                "execution_attempt_id": args.execution_attempt_id,
            })
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
            capture.error(exc)
        return capture

    def lane(self, name: str, *, system_prompt: str, user_prompt: str,
             provider: str, model: str | None, thinking: str) -> Path | None:
        if self.path is None:
            return None
        try:
            path = Path(tempfile.mkdtemp(prefix=name + "-", dir=self.path))
            self.write(path / "request.json", {
                "system_prompt": system_prompt, "user_prompt": user_prompt,
                "provider": provider, "model": model, "thinking": thinking,
            })
            return path
        except OSError as exc:
            self.error(exc)
            return None
