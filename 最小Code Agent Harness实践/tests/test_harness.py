from pathlib import Path

import pytest

from mini_code_agent import Workspace, edit_file, read_file, search_code, truncate


def test_workspace_rejects_parent_escape(tmp_path: Path) -> None:
    workspace = Workspace(str(tmp_path))

    with pytest.raises(ValueError, match="escapes workspace"):
        workspace.resolve("../secret.txt")


def test_workspace_rejects_git_directory(tmp_path: Path) -> None:
    workspace = Workspace(str(tmp_path))

    with pytest.raises(ValueError, match=".git"):
        workspace.resolve(".git/config")


def test_read_search_and_exact_edit(tmp_path: Path) -> None:
    source = tmp_path / "sample.py"
    source.write_text("value = 1\nprint(value)\n", encoding="utf-8")
    workspace = Workspace(str(tmp_path))

    assert "1: value = 1" in read_file(workspace, "sample.py")
    assert "sample.py:2: print(value)" in search_code(workspace, "print")
    assert edit_file(workspace, "sample.py", "value = 1", "value = 2").startswith("Updated")
    assert source.read_text(encoding="utf-8").startswith("value = 2")


def test_edit_requires_a_unique_match(tmp_path: Path) -> None:
    (tmp_path / "sample.txt").write_text("same\nsame\n", encoding="utf-8")
    workspace = Workspace(str(tmp_path))

    with pytest.raises(ValueError, match="exactly once"):
        edit_file(workspace, "sample.txt", "same", "new")


def test_truncate_keeps_head_and_tail() -> None:
    result = truncate("abcdefghij", limit=6)

    assert result.startswith("abc")
    assert result.endswith("hij")
    assert "truncated" in result
