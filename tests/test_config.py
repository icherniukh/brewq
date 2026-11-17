from __future__ import annotations

import pytest

from brewq import config as cfg_mod


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch, tmp_path):
    monkeypatch.setenv("BREWQ_CONFIG", str(tmp_path / "config.toml"))


def test_defaults_are_complete():
    conf = cfg_mod.load()
    assert conf["search"]["sort"] == "90d"
    assert conf["output"]["columns"] == ["name", "90d", "trend", "desc"]
    assert conf["list"]["columns"] == ["name", "desc"]
    assert conf["cache"]["max_age_seconds"] == 86400


def test_file_value_does_not_leak_into_later_loads(tmp_path):
    toml = tmp_path / "config.toml"
    toml.write_text("max-age = 1\n")
    assert cfg_mod.load()["cache"]["max_age_seconds"] == 1
    toml.unlink()
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
    assert conf["output"]["top"] == "auto"


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


def test_valid_fields_survive_invalid_neighbor(tmp_path, capsys):
    (tmp_path / "config.toml").write_text('top = "ten"\ncolumns = ["url"]\n')
    conf = cfg_mod.load()
    assert conf["output"] == {"top": "auto", "columns": ["url"]}
    assert "top:" in capsys.readouterr().err


@pytest.mark.parametrize("value,expected", [('"auto"', "auto"), ("12", 12), ("0", 0)])
def test_top_accepts_auto_fixed_and_unlimited(tmp_path, capsys, value, expected):
    (tmp_path / "config.toml").write_text(f"top = {value}\n")
    assert cfg_mod.load()["output"]["top"] == expected
    assert capsys.readouterr().err == ""


def test_all_long_option_keys(tmp_path, capsys):
    (tmp_path / "config.toml").write_text(
        'sort = "365d"\nreverse = true\ntop = 0\n'
        'columns = ["name", "90d", "auto"]\ninstalled-columns = ["bin"]\n'
        'max-age = 0\nauto-update = false\n'
    )
    conf = cfg_mod.load()
    assert conf["search"] == {"sort": "365d", "reverse": True}
    assert conf["output"] == {"top": 0, "columns": ["name", "90d", "auto"]}
    assert conf["list"]["columns"] == ["bin"]
    assert conf["cache"] == {"max_age_seconds": 0, "auto_refresh": False}
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("setting", [
    'limit = 1', 'auto_refresh = true', 'max_age_seconds = 1',
    '[search]\nsort = "name"', '[output]\nlimit = 1', '[list]\ncolumns = ["url"]',
    '[cache]\nauto_refresh = false', '[search]', '[output]', '[list]', '[cache]',
])
def test_old_config_keys_and_sections_are_unknown(setting, tmp_path, capsys):
    (tmp_path / "config.toml").write_text(f"{setting}\n")
    assert cfg_mod.load() == cfg_mod.DEFAULTS
    name = setting.splitlines()[0].strip("[]").split(" = ")[0]
    assert f"unknown setting {name!r}" in capsys.readouterr().err


@pytest.mark.parametrize("key,value,kind", [
    ("columns", '["version"]', "column"),
    ("installed-columns", '["description"]', "column"),
    ("sort", '"trending"', "sort field"), ("sort", '"installs"', "sort field"),
])
def test_old_field_names_are_unknown_and_retain_defaults(key, value, kind, tmp_path, capsys):
    (tmp_path / "config.toml").write_text(f"{key} = {value}\n")
    assert cfg_mod.load() == cfg_mod.DEFAULTS
    assert f"Unknown {kind}" in capsys.readouterr().err


@pytest.mark.parametrize("setting,typo,expected", [
    ("auto_updat", "false", "auto-update"), ("[srot]", "", "sort"),
    ("colums", '["name"]', "columns"), ("srot", '"name"', "sort"),
    ("columns", '["trned"]', "trend"), ("sort", '"naem"', "name"),
])
def test_typos_suggest_without_resolving(setting, typo, expected, tmp_path, capsys):
    (tmp_path / "config.toml").write_text(f"{setting}\n" if setting.startswith("[") else f"{setting} = {typo}\n")
    assert cfg_mod.load() == cfg_mod.DEFAULTS
    assert f"Did you mean {expected!r}" in capsys.readouterr().err


def test_unknown_settings_warn(tmp_path, capsys):
    (tmp_path / "config.toml").write_text('[unknown]\nx = 1\n[output]\nunknown = 1\n')
    assert cfg_mod.load() == cfg_mod.DEFAULTS
    err = capsys.readouterr().err
    assert "unknown setting 'unknown'" in err
    assert "unknown setting 'output'" in err


def test_auto_column_is_search_output_only(tmp_path, capsys):
    (tmp_path / "config.toml").write_text('installed-columns = ["name", "auto"]\n')
    assert cfg_mod.load() == cfg_mod.DEFAULTS
    assert "installed-columns:" in capsys.readouterr().err


def test_config_read_error_falls_back(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BREWQ_CONFIG", str(tmp_path))
    assert cfg_mod.load() == cfg_mod.DEFAULTS
    assert "config error" in capsys.readouterr().err


def test_config_diagnostic_prints_once_per_process(tmp_path, monkeypatch, capsys):
    path = tmp_path / "config.toml"
    path.write_text("topp = 3\n")
    monkeypatch.setenv("BREWQ_CONFIG", str(path))
    cfg_mod.load()
    cfg_mod.load()
    err = capsys.readouterr().err
    assert err.count("unknown setting 'topp'. Did you mean 'top'?") == 1
