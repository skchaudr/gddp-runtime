from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ToolSafetyError(ValueError):
    """Raised when a semantic tool request would mutate state or use network."""


NETWORK_TOKENS = {
    "curl",
    "wget",
    "ssh",
    "scp",
    "sftp",
    "rsync",
    "nc",
    "netcat",
    "telnet",
    "ftp",
    "pip",
    "npm",
    "pnpm",
    "yarn",
    "brew",
}

WRITE_TOKENS = {
    ">",
    ">>",
    "2>",
    "rm",
    "rmdir",
    "mv",
    "cp",
    "touch",
    "mkdir",
    "tee",
    "sed",
    "perl",
    "python",
    "python3",
    "git commit",
    "git push",
    "git reset",
    "git checkout",
    "git switch",
    "git merge",
    "git rebase",
    "git clean",
    "git add",
}

ALLOWED_COMMAND_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("git", "diff"),
    ("git", "log"),
    ("git", "show"),
    ("git", "status"),
    ("git", "grep"),
    ("pytest",),
    ("python3", "-m", "pytest"),
    ("python", "-m", "pytest"),
)

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {"name": "read_file", "description": "Read a file inside the source repo."},
    {"name": "list_directory", "description": "List a directory inside the source repo."},
    {"name": "grep_code", "description": "Search files with a regular expression."},
    {"name": "run_command", "description": "Run an allowed read-only command."},
    {"name": "read_node_yaml", "description": "Read the configured node YAML file."},
    {"name": "read_project_yaml", "description": "Read the configured project YAML file."},
    {"name": "git_diff", "description": "Return git diff output."},
    {"name": "git_log", "description": "Return recent git log output."},
]


@dataclass(frozen=True)
class SemanticToolbox:
    repo_root: Path
    node_yaml_path: Path | None = None
    project_yaml_path: Path | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "repo_root", Path(self.repo_root).resolve())

    def execute(self, name: str, args: dict[str, Any]) -> Any:
        tools = {
            "read_file": self.read_file,
            "list_directory": self.list_directory,
            "grep_code": self.grep_code,
            "run_command": self.run_command,
            "read_node_yaml": self.read_node_yaml,
            "read_project_yaml": self.read_project_yaml,
            "git_diff": self.git_diff,
            "git_log": self.git_log,
        }
        if name not in tools:
            raise ToolSafetyError(f"unknown tool: {name}")
        return tools[name](**args)

    def read_file(self, path: str, max_bytes: int = 200_000) -> str:
        target = self._resolve_inside_repo(path)
        if not target.is_file():
            raise FileNotFoundError(str(target))
        return target.read_text(encoding="utf-8", errors="replace")[:max_bytes]

    def list_directory(self, path: str = ".") -> list[str]:
        target = self._resolve_inside_repo(path)
        if not target.is_dir():
            raise NotADirectoryError(str(target))
        return sorted(child.name + ("/" if child.is_dir() else "") for child in target.iterdir())

    def grep_code(self, pattern: str, path: str = ".", context: int = 0, max_matches: int = 100) -> list[dict[str, Any]]:
        root = self._resolve_inside_repo(path)
        regex = re.compile(pattern)
        matches: list[dict[str, Any]] = []
        files = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file()]
        for file_path in files:
            if len(matches) >= max_matches or self._should_skip(file_path):
                continue
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
            for index, line in enumerate(lines, start=1):
                if regex.search(line):
                    start = max(1, index - context)
                    end = min(len(lines), index + context)
                    matches.append(
                        {
                            "path": str(file_path.relative_to(self.repo_root)),
                            "line": index,
                            "text": line,
                            "context": lines[start - 1 : end],
                        }
                    )
                    if len(matches) >= max_matches:
                        break
        return matches

    def run_command(self, command: list[str], timeout_seconds: int = 30) -> str:
        self._assert_safe_command(command)
        result = subprocess.run(
            command,
            cwd=self.repo_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=self._network_disabled_env(),
        )
        output = result.stdout + result.stderr
        if result.returncode != 0:
            raise RuntimeError(f"command failed with exit {result.returncode}: {output}")
        return output

    def read_node_yaml(self) -> str:
        if self.node_yaml_path is None:
            raise ToolSafetyError("node_yaml_path is not configured")
        return self.read_file(str(self.node_yaml_path))

    def read_project_yaml(self) -> str:
        if self.project_yaml_path is None:
            raise ToolSafetyError("project_yaml_path is not configured")
        return self.read_file(str(self.project_yaml_path))

    def git_diff(self, ref: str | None = None) -> str:
        command = ["git", "diff"]
        if ref:
            command.append(ref)
        return self.run_command(command)

    def git_log(self, max_count: int = 10) -> str:
        return self.run_command(["git", "log", f"--max-count={max_count}", "--oneline"])

    def _resolve_inside_repo(self, path: str | Path) -> Path:
        target = Path(path)
        if target.is_absolute():
            resolved = target.resolve()
        else:
            resolved = (self.repo_root / target).resolve()
        if resolved != self.repo_root and self.repo_root not in resolved.parents:
            raise ToolSafetyError(f"path escapes repo root: {path}")
        return resolved

    def _assert_safe_command(self, command: list[str]) -> None:
        if not command:
            raise ToolSafetyError("empty command")
        lowered = [part.lower() for part in command]
        joined = " ".join(lowered)
        if any(token in lowered for token in NETWORK_TOKENS):
            raise ToolSafetyError(f"network command refused: {command[0]}")
        if any(token in lowered or token in joined for token in WRITE_TOKENS):
            raise ToolSafetyError(f"write-capable command refused: {' '.join(command)}")
        if not any(tuple(lowered[: len(prefix)]) == prefix for prefix in ALLOWED_COMMAND_PREFIXES):
            raise ToolSafetyError(f"command is not in read-only allowlist: {' '.join(command)}")

    def _network_disabled_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(
            {
                "NO_PROXY": "*",
                "no_proxy": "*",
                "PIP_NO_INDEX": "1",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
            }
        )
        return env

    def _should_skip(self, path: Path) -> bool:
        return any(part in {".git", "__pycache__", ".pytest_cache"} for part in path.parts)
