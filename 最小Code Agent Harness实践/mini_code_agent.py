#!/usr/bin/env python3
"""A small, inspectable coding-agent harness for educational use."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI


MAX_STEPS = 20
MAX_TOOL_OUTPUT = 8_000
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "dist", "build", "__pycache__"}
ALLOWED_COMMANDS = {"git", "pytest", "python", "python3", "ruff", "npm", "pnpm", "yarn", "go", "cargo"}


class Workspace:
    """Resolve file operations inside one repository root."""

    def __init__(self, root: str) -> None:
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise ValueError(f"Workspace does not exist: {self.root}")

    def resolve(self, relative_path: str) -> Path:
        path = (self.root / relative_path).resolve()
        if path != self.root and self.root not in path.parents:
            raise ValueError(f"Path escapes workspace: {relative_path}")
        if ".git" in path.relative_to(self.root).parts:
            raise ValueError("Direct access to .git is not allowed")
        return path

    def relative(self, path: Path) -> str:
        return str(path.relative_to(self.root))


def truncate(text: str, limit: int = MAX_TOOL_OUTPUT) -> str:
    """Keep both ends of long observations so errors at the tail survive."""
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-limit // 2 :]
    return f"{head}\n\n... <truncated {len(text) - limit} chars> ...\n\n{tail}"


def list_files(ws: Workspace, path: str = ".", max_depth: int = 3) -> str:
    base = ws.resolve(path)
    if not base.is_dir():
        raise ValueError(f"Not a directory: {path}")

    lines: list[str] = []
    base_depth = len(base.parts)
    for current, dirs, files in os.walk(base):
        current_path = Path(current)
        depth = len(current_path.parts) - base_depth
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and depth < max_depth)
        for name in sorted(files):
            file_path = current_path / name
            lines.append(ws.relative(file_path))
            if len(lines) >= 300:
                lines.append("... <file list truncated>")
                return "\n".join(lines)
    return "\n".join(lines) or "<empty directory>"


def read_file(ws: Workspace, path: str, start_line: int = 1, end_line: int = 250) -> str:
    file_path = ws.resolve(path)
    if not file_path.is_file():
        raise ValueError(f"Not a file: {path}")
    if start_line < 1 or end_line < start_line:
        raise ValueError("Invalid line range")

    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    selected = lines[start_line - 1 : end_line]
    numbered = [f"{number}: {line}" for number, line in enumerate(selected, start=start_line)]
    return truncate("\n".join(numbered) or "<empty file>")


def search_code(ws: Workspace, query: str, path: str = ".") -> str:
    base = ws.resolve(path)
    matches: list[str] = []
    if base.is_file():
        candidates = [base]
    else:
        candidates = []
        for current, dirs, files in os.walk(base):
            dirs[:] = [directory for directory in dirs if directory not in SKIP_DIRS]
            candidates.extend(Path(current) / name for name in files)

    for file_path in candidates:
        if not file_path.is_file():
            continue
        try:
            if file_path.stat().st_size > 1_000_000:
                continue
            lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines, start=1):
            if query.lower() in line.lower():
                matches.append(f"{ws.relative(file_path)}:{number}: {line.strip()}")
                if len(matches) >= 80:
                    matches.append("... <search results truncated>")
                    return truncate("\n".join(matches))
    return truncate("\n".join(matches) or "<no matches>")


def edit_file(ws: Workspace, path: str, old_text: str, new_text: str) -> str:
    file_path = ws.resolve(path)
    if not file_path.is_file():
        raise ValueError(f"Not a file: {path}")

    content = file_path.read_text(encoding="utf-8")
    count = content.count(old_text)
    if count != 1:
        raise ValueError(f"old_text must match exactly once; found {count} matches")

    file_path.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
    return f"Updated {path} ({len(old_text)} chars -> {len(new_text)} chars)"


def run_command(ws: Workspace, command: str) -> str:
    argv = shlex.split(command)
    if not argv:
        raise ValueError("Empty command")
    if argv[0] not in ALLOWED_COMMANDS:
        raise ValueError(f"Command not allowed: {argv[0]}")

    print(f"\n[approval required] Run in {ws.root}: {argv!r}")
    approved = input("Approve? [y/N] ").strip().lower() == "y"
    if not approved:
        return "Command rejected by user"

    completed = subprocess.run(
        argv,
        cwd=ws.root,
        capture_output=True,
        text=True,
        timeout=60,
        shell=False,
    )
    output = f"exit_code={completed.returncode}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    return truncate(output)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files inside the workspace. Use this to understand repository structure.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory relative to workspace"},
                    "max_depth": {"type": "integer", "minimum": 1, "maximum": 5},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a bounded line range from a UTF-8 text file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer", "minimum": 1},
                    "end_line": {"type": "integer", "minimum": 1},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search text recursively in repository files. Returns file:line matches.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "path": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace one exact text fragment in an existing file. Fails unless old_text occurs exactly once.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"},
                },
                "required": ["path", "old_text", "new_text"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run an approved development command in the workspace. Use for tests, lint and git diff/status.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
                "additionalProperties": False,
            },
        },
    },
]


SYSTEM_PROMPT = """You are a coding agent operating inside one repository.

Rules:
1. Inspect relevant code before editing.
2. Keep changes minimal and directly related to the task.
3. Prefer search_code and bounded read_file calls over reading large files.
4. After editing, run the narrowest relevant test or check.
5. Never claim success without reporting what you verified.
6. If a tool fails, inspect the error and change your approach; do not blindly repeat it.
7. Finish with a concise summary: changed files, reason, verification, and remaining uncertainty.
"""


def build_client() -> OpenAI:
    kwargs: dict[str, Any] = {"api_key": os.environ["LLM_API_KEY"]}
    if os.getenv("LLM_BASE_URL"):
        kwargs["base_url"] = os.environ["LLM_BASE_URL"]
    return OpenAI(**kwargs)


def append_trace(trace_path: Path, event: dict[str, Any]) -> None:
    event = {"time": datetime.now(timezone.utc).isoformat(), **event}
    with trace_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=False) + "\n")


def run_agent(workspace_path: str, task: str) -> None:
    ws = Workspace(workspace_path)
    client = build_client()
    model = os.environ["LLM_MODEL"]
    trace_path = ws.root / ".mini-agent-trace.jsonl"

    handlers: dict[str, Callable[..., str]] = {
        "list_files": lambda **args: list_files(ws, **args),
        "read_file": lambda **args: read_file(ws, **args),
        "search_code": lambda **args: search_code(ws, **args),
        "edit_file": lambda **args: edit_file(ws, **args),
        "run_command": lambda **args: run_command(ws, **args),
    }
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]

    append_trace(trace_path, {"type": "task", "task": task, "model": model})
    for step in range(1, MAX_STEPS + 1):
        print(f"\n=== step {step}/{MAX_STEPS} ===")
        response = client.chat.completions.create(model=model, messages=messages, tools=TOOLS)
        message = response.choices[0].message
        assistant_message = message.model_dump(exclude_none=True)
        messages.append(assistant_message)
        append_trace(trace_path, {"type": "assistant", "step": step, "message": assistant_message})

        if message.content:
            print(message.content)

        if not message.tool_calls:
            print(f"\nTrace saved to {trace_path}")
            return

        for call in message.tool_calls:
            name = call.function.name
            try:
                arguments = json.loads(call.function.arguments)
                if name not in handlers:
                    raise ValueError(f"Unknown tool: {name}")
                print(f"tool: {name}({json.dumps(arguments, ensure_ascii=False)})")
                result = handlers[name](**arguments)
                is_error = False
            except Exception as error:  # Tool failures become observations, not agent crashes.
                result = f"ERROR: {type(error).__name__}: {error}"
                is_error = True

            result = truncate(result)
            print(result)
            append_trace(
                trace_path,
                {"type": "tool", "step": step, "name": name, "result": result, "is_error": is_error},
            )
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "name": name, "content": result}
            )

    print(f"Stopped after reaching the {MAX_STEPS}-step budget. Trace: {trace_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('Usage: python mini_code_agent.py <workspace> "<task>"')
        raise SystemExit(2)
    run_agent(sys.argv[1], sys.argv[2])
