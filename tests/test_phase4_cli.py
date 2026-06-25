from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from as_docs.cli import cli

FIXTURE = Path(__file__).parent / "fixtures" / "SampleProject"


class _FakeGit:
    def __init__(self, diff_output: str) -> None:
        self._diff_output = diff_output

    def diff(self, *_args) -> str:
        return self._diff_output


class _FakeRepo:
    def __init__(self, working_tree_dir: Path, diff_output: str = "") -> None:
        self.working_tree_dir = str(working_tree_dir)
        self.git = _FakeGit(diff_output)


def _cfg_text(project_root: Path) -> str:
    return f"""
project:
  name: "SampleProject"
  root: "{project_root.as_posix()}"
scanner:
  active_configuration: "Config1"
ai:
  enabled: false
output:
  docs_dir: "docs/as-docs"
git:
  auto_level: 2
"""


def test_diff_reports_changed_pous(monkeypatch, tmp_path: Path) -> None:
    cfg = tmp_path / ".as-docs.yaml"
    cfg.write_text(_cfg_text(FIXTURE), encoding="utf-8")

    diff_output = "\n".join(
        [
            "Logical/MainProgram/Main.st",
            "Logical/GlobalVars/GlobalTypes.typ",
        ]
    )

    monkeypatch.setattr("as_docs.cli.Repo", lambda *args, **kwargs: _FakeRepo(FIXTURE, diff_output))

    runner = CliRunner()
    result = runner.invoke(cli, ["diff", "HEAD~1", "--config", str(cfg)])

    assert result.exit_code == 0
    assert "Changed POUs" in result.output
    assert "MainProgram" in result.output
    assert "MotorControl" in result.output


def test_install_hook_is_idempotent(monkeypatch, tmp_path: Path) -> None:
    cfg = tmp_path / ".as-docs.yaml"
    cfg.write_text(_cfg_text(FIXTURE), encoding="utf-8")

    repo_root = tmp_path / "repo"
    hooks_dir = repo_root / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("as_docs.cli.Repo", lambda *args, **kwargs: _FakeRepo(repo_root))

    runner = CliRunner()
    first = runner.invoke(cli, ["install-hook", "--yes", "--config", str(cfg)])
    second = runner.invoke(cli, ["install-hook", "--yes", "--config", str(cfg)])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "Installed post-commit hook" in first.output
    assert "already installed" in second.output.lower()

    hook_file = hooks_dir / "post-commit"
    content = hook_file.read_text(encoding="utf-8")
    assert "# >>> as-docs hook start >>>" in content
    assert "# <<< as-docs hook end <<<" in content
