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
    assert conf["output"]["columns"] == ["name", "90d", "trend", "desc"]
    assert conf["list"]["columns"] == ["name", "desc"]
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
        "name", "90d", "trend", "desc",
    ]


def test_env_override_config_path(monkeypatch, tmp_path):
    toml = tmp_path / "brewq.toml"
    toml.write_text('columns = ["name"]\n')
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
    assert conf["output"]["limit"] == "auto"


@pytest.mark.parametrize("key,value", [
    ("top", '"ten"'), ("top", "-1"), ("top", "true"), ("top", "1.5"),
    ("max-age", '"3600"'), ("max-age", "-1"), ("max-age", "false"), ("max-age", "inf"),
    ("sort", "1"), ("sort", '"unknown"'),
    ("columns", '"name"'), ("columns", "[]"), ("columns", '["name", 1]'),
    ("columns", '["name", "unknown"]'), ("installed-columns", '["name", {}]'),
    ("installed-columns", '[""]'), ("auto-update", "1"), ("reverse", '"true"'),
])
def test_invalid_fields_retain_default(key, value, tmp_path, capsys):
    (tmp_path / "config.toml").write_text(f"{key} = {value}\n")
    assert cfg_mod.load() == cfg_mod.DEFAULTS
    assert f"{key}:" in capsys.readouterr().err


@pytest.mark.parametrize("age", ["invalid", "", "-1", "1.5", "true", "9" * 5000])
def test_invalid_env_retains_valid_file_value(age, monkeypatch, tmp_path, capsys):
    (tmp_path / "config.toml").write_text("max-age = 300\n")
    monkeypatch.setenv("BREWQ_CACHE_MAX_AGE", age)
    assert cfg_mod.load()["cache"]["max_age_seconds"] == 300
    assert "BREWQ_CACHE_MAX_AGE: expected a nonnegative integer" in capsys.readouterr().err


def test_valid_fields_survive_invalid_neighbor(tmp_path, capsys):
    (tmp_path / "config.toml").write_text('top = "ten"\ncolumns = ["url"]\n')
    conf = cfg_mod.load()
    assert conf["output"] == {"limit": "auto", "columns": ["url"]}
    assert "top:" in capsys.readouterr().err


@pytest.mark.parametrize("value,expected", [('"auto"', "auto"), ("12", 12), ("0", 0)])
def test_top_accepts_auto_fixed_and_legacy_unlimited(tmp_path, capsys, value, expected):
    (tmp_path / "config.toml").write_text(f"top = {value}\n")
    assert cfg_mod.load()["output"]["limit"] == expected
    assert capsys.readouterr().err == ""


def test_all_long_option_keys(tmp_path, capsys):
    (tmp_path / "config.toml").write_text(
        'sort = "365d"\nreverse = true\ntop = 0\n'
        'columns = ["name", "90d", "auto"]\ninstalled-columns = ["bin"]\n'
        'max-age = 0\nauto-update = false\n'
    )
    conf = cfg_mod.load()
    assert conf["search"] == {"sort": "365d", "reverse": True}
    assert conf["output"] == {"limit": 0, "columns": ["name", "90d", "auto"]}
    assert conf["list"]["columns"] == ["bin"]
    assert conf["cache"] == {"max_age_seconds": 0, "auto_refresh": False}
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("section,key,new", [
    ("search", "sort", "sort"), ("search", "reverse", "reverse"),
    ("output", "limit", "top"), ("output", "columns", "columns"),
    ("list", "columns", "installed-columns"),
    ("cache", "max_age_seconds", "max-age"), ("cache", "auto_refresh", "auto-update"),
])
def test_old_config_keys_name_replacements(section, key, new, tmp_path, capsys):
    (tmp_path / "config.toml").write_text(f"[{section}]\n{key} = 1\n")
    assert cfg_mod.load() == cfg_mod.DEFAULTS
    assert f"{section}.{key} was removed; use root key {new!r}" in capsys.readouterr().err


@pytest.mark.parametrize("old,new", [("limit", "top"), ("auto_refresh", "auto-update"),
                                    ("max_age_seconds", "max-age")])
def test_old_bare_config_keys_name_replacements(old, new, tmp_path, capsys):
    (tmp_path / "config.toml").write_text(f"{old} = 1\n")
    assert cfg_mod.load() == cfg_mod.DEFAULTS
    assert f"use {new!r}" in capsys.readouterr().err


@pytest.mark.parametrize("key,value,new", [
    ("columns", '["version"]', "ver"), ("installed-columns", '["description"]', "desc"),
    ("sort", '"trending"', "trend"), ("sort", '"installs"', "30d"),
])
def test_old_field_names_warn_and_retain_defaults(key, value, new, tmp_path, capsys):
    (tmp_path / "config.toml").write_text(f"{key} = {value}\n")
    assert cfg_mod.load() == cfg_mod.DEFAULTS
    assert f"use {new!r}" in capsys.readouterr().err


@pytest.mark.parametrize("setting,typo,expected", [
    ("colums", '["name"]', "columns"), ("srot", '"name"', "sort"),
    ("columns", '["trned"]', "trend"), ("sort", '"naem"', "name"),
])
def test_typos_suggest_without_resolving(setting, typo, expected, tmp_path, capsys):
    (tmp_path / "config.toml").write_text(f"{setting} = {typo}\n")
    assert cfg_mod.load() == cfg_mod.DEFAULTS
    assert f"Did you mean {expected!r}" in capsys.readouterr().err


def test_unknown_settings_warn(tmp_path, capsys):
    (tmp_path / "config.toml").write_text('[unknown]\nx = 1\n[output]\nunknown = 1\n')
    assert cfg_mod.load() == cfg_mod.DEFAULTS
    err = capsys.readouterr().err
    assert "unknown setting 'unknown'" in err
    assert "unknown setting 'output.unknown'" in err


def test_auto_column_is_search_output_only(tmp_path, capsys):
    (tmp_path / "config.toml").write_text('installed-columns = ["name", "auto"]\n')
    assert cfg_mod.load() == cfg_mod.DEFAULTS
    assert "installed-columns:" in capsys.readouterr().err


def test_config_read_error_falls_back(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BREWQ_CONFIG", str(tmp_path))
    assert cfg_mod.load() == cfg_mod.DEFAULTS
    assert "config error" in capsys.readouterr().err
