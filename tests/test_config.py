from __future__ import annotations

import pytest

from brewq import config as cfg_mod


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch, tmp_path):
    monkeypatch.setenv("BREWQ_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.delenv("BREWQ_CACHE_MAX_AGE", raising=False)


def test_defaults_are_complete():
    conf = cfg_mod.load()
    assert conf["search"]["sort"] == "90d"
    assert conf["output"]["columns"] == ["name", "installs_90d", "trending", "description"]
    assert conf["list"]["columns"] == ["name", "description"]
    assert conf["cache"]["max_age_seconds"] == 86400


def test_env_override_cache_max_age(monkeypatch):
    monkeypatch.setenv("BREWQ_CACHE_MAX_AGE", "3600")
    conf = cfg_mod.load()
    assert conf["cache"]["max_age_seconds"] == 3600


def test_env_override_does_not_leak_into_later_loads(monkeypatch):
    monkeypatch.setenv("BREWQ_CACHE_MAX_AGE", "1")
    assert cfg_mod.load()["cache"]["max_age_seconds"] == 1
    monkeypatch.delenv("BREWQ_CACHE_MAX_AGE")
    assert cfg_mod.load()["cache"]["max_age_seconds"] == 86400


def test_loaded_config_can_be_mutated_without_changing_defaults():
    conf = cfg_mod.load()
    conf["output"]["columns"].append("url")
    assert cfg_mod.load()["output"]["columns"] == [
        "name", "installs_90d", "trending", "description",
    ]


def test_env_override_config_path(monkeypatch, tmp_path):
    toml = tmp_path / "brewq.toml"
    toml.write_text('[output]\ncolumns = ["name"]\n')
    monkeypatch.setenv("BREWQ_CONFIG", str(toml))
    conf = cfg_mod.load()
    assert conf["output"]["columns"] == ["name"]
    # defaults for untouched sections still present
    assert conf["search"]["sort"] == "90d"


def test_cache_dir_env(monkeypatch, tmp_path):
    monkeypatch.setenv("BREWQ_CACHE_DIR", str(tmp_path))
    assert cfg_mod.cache_dir() == tmp_path


def test_cache_dir_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("BREWQ_CACHE_DIR", "")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert cfg_mod.cache_dir() == tmp_path / "brewq"


def test_corrupt_config_warns_and_uses_defaults(monkeypatch, tmp_path, capsys):
    toml = tmp_path / "bad.toml"
    toml.write_text("this is not valid toml = [[[")
    monkeypatch.setenv("BREWQ_CONFIG", str(toml))
    conf = cfg_mod.load()
    err = capsys.readouterr().err
    assert "config error" in err
    assert str(toml) in err
    assert conf["search"]["sort"] == "90d"
    assert conf["output"]["limit"] == 0


@pytest.mark.parametrize("section", ["search", "output", "list", "cache"])
@pytest.mark.parametrize("value", ["1", "true", '"bad"', "[]"])
def test_scalar_sections_fall_back(section, value, monkeypatch, tmp_path, capsys):
    path = tmp_path / "invalid.toml"
    path.write_text(f"{section} = {value}\n")
    monkeypatch.setenv("BREWQ_CONFIG", str(path))
    assert cfg_mod.load() == cfg_mod.DEFAULTS
    assert f"{section}: expected a table" in capsys.readouterr().err


@pytest.mark.parametrize("section,key,value", [
    ("output", "limit", '"ten"'),
    ("output", "limit", "-1"),
    ("output", "limit", "true"),
    ("output", "limit", "1.5"),
    ("cache", "max_age_seconds", '"3600"'),
    ("cache", "max_age_seconds", "-1"),
    ("cache", "max_age_seconds", "false"),
    ("cache", "max_age_seconds", "inf"),
    ("search", "sort", "1"),
    ("search", "sort", '"unknown"'),
    ("output", "columns", '"name"'),
    ("output", "columns", "[]"),
    ("output", "columns", '["name", 1]'),
    ("output", "columns", '["name", "unknown"]'),
    ("list", "columns", '["name", {}]'),
    ("list", "columns", '[""]'),
])
def test_invalid_fields_retain_default(section, key, value, monkeypatch, tmp_path, capsys):
    path = tmp_path / "invalid.toml"
    path.write_text(f"[{section}]\n{key} = {value}\n")
    monkeypatch.setenv("BREWQ_CONFIG", str(path))
    assert cfg_mod.load() == cfg_mod.DEFAULTS
    assert f"{section}.{key}:" in capsys.readouterr().err


@pytest.mark.parametrize("age", ["invalid", "", "-1", "1.5", "true", "9" * 5000])
def test_invalid_env_retains_valid_file_value(age, monkeypatch, tmp_path, capsys):
    path = tmp_path / "config.toml"
    path.write_text("[cache]\nmax_age_seconds = 300\n")
    monkeypatch.setenv("BREWQ_CACHE_MAX_AGE", age)
    assert cfg_mod.load()["cache"]["max_age_seconds"] == 300
    err = capsys.readouterr().err
    assert "BREWQ_CACHE_MAX_AGE: expected a nonnegative integer" in err
    assert "Traceback" not in err


def test_valid_fields_survive_invalid_neighbor(tmp_path, capsys):
    (tmp_path / "config.toml").write_text('[output]\nlimit = "ten"\ncolumns = ["url"]\n')
    conf = cfg_mod.load()
    assert conf["output"] == {"limit": 0, "columns": ["url"]}
    assert "output.limit" in capsys.readouterr().err


def test_zero_ranges_aliases_and_auto_are_valid(tmp_path, capsys):
    (tmp_path / "config.toml").write_text(
        '[search]\nsort = " YEAR "\n[output]\nlimit = 0\n'
        'columns = ["n", "90d", "auto"]\n[list]\ncolumns = ["bin"]\n'
        '[cache]\nmax_age_seconds = 0\n'
    )
    conf = cfg_mod.load()
    assert conf["search"]["sort"] == " YEAR "
    assert conf["output"] == {"limit": 0, "columns": ["n", "90d", "auto"]}
    assert conf["list"]["columns"] == ["bin"]
    assert conf["cache"]["max_age_seconds"] == 0
    assert capsys.readouterr().err == ""


def test_unknown_settings_are_ignored(tmp_path, capsys):
    (tmp_path / "config.toml").write_text('[unknown]\nx = 1\n[output]\nunknown = 1\n')
    assert cfg_mod.load() == cfg_mod.DEFAULTS
    err = capsys.readouterr().err
    assert "unknown section" in err
    assert "unknown setting output.unknown" in err


def test_auto_column_is_search_output_only(tmp_path, capsys):
    (tmp_path / "config.toml").write_text('[list]\ncolumns = ["name", "auto"]\n')
    assert cfg_mod.load()["list"]["columns"] == cfg_mod.DEFAULTS["list"]["columns"]
    assert "list.columns" in capsys.readouterr().err


def test_config_read_error_falls_back(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BREWQ_CONFIG", str(tmp_path))
    assert cfg_mod.load() == cfg_mod.DEFAULTS
    assert "config error" in capsys.readouterr().err
