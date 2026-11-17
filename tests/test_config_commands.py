from __future__ import annotations

import re
import shlex
import sys
import tomllib
from pathlib import Path

import pytest

from brewq import cli, config


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("BREWQ_CONFIG", str(tmp_path / "nested/config.toml"))
    for name in ("BREWQ_NO_AUTO_REFRESH", "VISUAL", "EDITOR"):
        monkeypatch.delenv(name, raising=False)


def _editor(tmp_path, source):
    script = tmp_path / "fake editor.py"
    script.write_text(
        "import sys\nfrom pathlib import Path\n"
        "assert sys.argv[1] == '--test-editor'\n"
        "path = Path(sys.argv[2])\n" + source
    )
    return shlex.join([sys.executable, str(script), "--test-editor"])


@pytest.mark.parametrize("command", [[], ["show"], ["defaults"]])
def test_config_toml_round_trips_defaults(command, capsys):
    assert cli.main(["+config", *command]) == 0
    out, err = capsys.readouterr()
    assert not err
    values = tomllib.loads(out)
    assert list(values) == [
        "top", "sort", "reverse", "columns", "installed-columns", "auto-update", "max-age",
    ]
    path = config.config_path()
    if command != ["defaults"]:
        assert out.startswith(f"# {path} (not found)\n")
        assert all(line.endswith(" # default") for line in out.splitlines()[1:])
    else:
        assert "#" not in out
    assert not path.exists()
    path.parent.mkdir()
    path.write_text(out)
    assert config.load() == config.DEFAULTS
    assert not capsys.readouterr().err


def test_show_effective_values_and_sources(tmp_path, monkeypatch, capsys):
    path = config.config_path()
    path.parent.mkdir()
    path.write_text('top = 17\nsort = "name"\nauto-update = true\nreverse = "bad"\ntopp = 3\n')
    monkeypatch.setenv("BREWQ_NO_AUTO_REFRESH", " YES ")
    assert cli.main(["+config", "show"]) == 0
    out, err = capsys.readouterr()
    assert out.startswith(f"# {path} (exists)\n")
    assert "top = 17 # config file" in out
    assert 'sort = "name" # config file' in out
    assert "reverse = false # default" in out
    assert "auto-update = false # BREWQ_NO_AUTO_REFRESH" in out
    assert "reverse: expected true or false" in err
    assert "unknown setting 'topp'. Did you mean 'top'?" in err
    values = tomllib.loads(out)
    path.write_text(out)
    loaded = config.load()
    assert loaded["output"]["top"] == values["top"] == 17
    assert loaded["search"] == {"sort": "name", "reverse": False}
    assert loaded["cache"]["auto_refresh"] is values["auto-update"] is False


@pytest.mark.parametrize("value,source", [
    ("1", "BREWQ_NO_AUTO_REFRESH"), ("false", "config file"), ("bad", "config file"),
])
def test_show_env_sources_follow_opt_out_semantics(value, source, monkeypatch, capsys):
    path = config.config_path()
    path.parent.mkdir()
    path.write_text("auto-update = false\n")
    monkeypatch.setenv("BREWQ_NO_AUTO_REFRESH", value)
    assert cli.main(["+config"]) == 0
    out, err = capsys.readouterr()
    assert f"auto-update = false # {source}" in out
    assert bool(err) == (value == "bad")


def test_defaults_ignore_file_and_environment(monkeypatch, capsys):
    path = config.config_path()
    path.parent.mkdir()
    path.write_text("invalid toml !!!")
    monkeypatch.setenv("BREWQ_NO_AUTO_REFRESH", "bad")
    assert cli.main(["+config", "defaults"]) == 0
    out, err = capsys.readouterr()
    assert not err
    assert tomllib.loads(out)["auto-update"] is True


def test_serializer_escapes_known_value_types():
    cfg = config.load()
    text = 'quote" slash\\ newline\n tab\t control\x01 emoji 🎵'
    cfg["search"]["sort"] = text
    cfg["output"]["columns"] = [text]
    cfg["output"]["top"] = 3
    values = tomllib.loads(config.to_toml(cfg))
    assert values["sort"] == text
    assert values["columns"] == [text]
    assert values["top"] == 3
    assert values["reverse"] is False


@pytest.mark.parametrize("variable", ["VISUAL", "EDITOR"])
def test_edit_creates_commented_starter_and_accepts_editor_arguments(
    variable, tmp_path, monkeypatch, capsys,
):
    editor = _editor(tmp_path, "assert path.read_text() == " + repr(config.starter_toml())
                     + "\npath.write_text('top = 9\\n')\n")
    monkeypatch.setenv(variable, editor)
    if variable == "VISUAL":
        monkeypatch.setenv("EDITOR", "/this/editor/must/not/run")
    assert cli.main(["+config", "edit"]) == 0
    assert config.load()["output"]["top"] == 9
    assert capsys.readouterr() == ("", "")


def test_edit_preserves_existing_file(tmp_path, monkeypatch, capsys):
    path = config.config_path()
    path.parent.mkdir()
    path.write_text("# keep my comment\ntop = 7\n")
    monkeypatch.setenv("EDITOR", _editor(tmp_path,
                       "assert path.read_text() == '# keep my comment\\ntop = 7\\n'\n"))
    assert cli.main(["+config", "edit"]) == 0
    assert path.read_text() == "# keep my comment\ntop = 7\n"
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("contents", ['top = "bad"\n', 'topp = 2\n', 'invalid TOML !!!'])
def test_edit_reports_same_diagnostics_as_load(contents, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("VISUAL", _editor(tmp_path, f"path.write_text({contents!r})\n"))
    assert cli.main(["+config", "edit"]) == 1
    out, diagnostics = capsys.readouterr()
    assert out == ""
    assert "config error" in diagnostics
    config.load()
    assert capsys.readouterr().err == diagnostics


def test_edit_returns_editor_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EDITOR", _editor(tmp_path, "sys.exit(7)\n"))
    assert cli.main(["+config", "edit"]) == 7
    assert capsys.readouterr() == ("", "")


def test_edit_validates_even_when_editor_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EDITOR", _editor(tmp_path, "path.write_text('topp = 2\\n')\nsys.exit(7)\n"))
    assert cli.main(["+config", "edit"]) == 7
    assert "unknown setting 'topp'" in capsys.readouterr().err


def test_edit_requires_editor_without_creating_file(capsys):
    assert cli.main(["+config", "edit"]) == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert "VISUAL" in err and "EDITOR" in err
    assert not config.config_path().parent.exists()


@pytest.mark.parametrize("editor", ["/no/such/editor", "'unclosed", " "])
def test_edit_handles_invalid_editor(editor, monkeypatch, capsys):
    monkeypatch.setenv("VISUAL", editor)
    assert cli.main(["+config", "edit"]) == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert "brewq:" in err


def test_edit_reports_creation_error(tmp_path, monkeypatch, capsys):
    config.config_path().parent.write_text("not a directory")
    monkeypatch.setenv("EDITOR", _editor(tmp_path, "raise AssertionError('must not run')\n"))
    assert cli.main(["+config", "edit"]) == 1
    assert "config edit:" in capsys.readouterr().err


def test_readme_defaults_match_serialized_order_and_values():
    readme = Path(__file__).resolve().parents[1].joinpath("README.md").read_text()
    block = re.search(r"Built-in defaults:\s*```toml\n(.*?)```", readme, re.DOTALL)
    assert block
    documented = tomllib.loads(block.group(1))
    serialized = tomllib.loads(config.to_toml(config.DEFAULTS))
    assert list(documented.items()) == list(serialized.items())


@pytest.mark.parametrize("command", ["show", "defaults", "edit"])
def test_config_subcommand_help(command, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["+config", command, "--help"])
    assert exc.value.code == 0
    out, err = capsys.readouterr()
    assert f"+config {command}" in out
    assert not err


def test_starter_file_lists_every_default_and_changes_nothing(tmp_path, monkeypatch):
    starter = config.starter_toml()
    assert tomllib.loads(starter) == {}
    for line in config.to_toml(config.DEFAULTS).splitlines():
        assert f"# {line}" in starter
    path = tmp_path / "config.toml"
    path.write_text(starter)
    monkeypatch.setenv("BREWQ_CONFIG", str(path))
    _, sources, diagnostics = config.validate()
    assert diagnostics == []
    assert set(sources.values()) == {"default"}
