from __future__ import annotations

from brewq import config as cfg_mod


def test_defaults_are_complete():
    conf = cfg_mod.load()
    assert conf["search"]["type"] == "all"
    assert conf["output"]["columns"] == ["name", "version", "installs", "description"]
    assert conf["list"]["columns"] == ["name", "version", "description"]
    assert conf["cache"]["max_age_seconds"] == 86400


def test_env_override_cache_max_age(monkeypatch):
    monkeypatch.setenv("BREWQ_CACHE_MAX_AGE", "3600")
    conf = cfg_mod.load()
    assert conf["cache"]["max_age_seconds"] == 3600


def test_env_override_config_path(monkeypatch, tmp_path):
    toml = tmp_path / "brewq.toml"
    toml.write_text('[output]\ncolumns = ["name"]\n')
    monkeypatch.setenv("BREWQ_CONFIG", str(toml))
    conf = cfg_mod.load()
    assert conf["output"]["columns"] == ["name"]
    # defaults for untouched sections still present
    assert conf["search"]["type"] == "all"


def test_cache_dir_env(monkeypatch, tmp_path):
    monkeypatch.setenv("BREWQ_CACHE_DIR", str(tmp_path))
    assert cfg_mod.cache_dir() == tmp_path


def test_cache_dir_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("BREWQ_CACHE_DIR", "")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert cfg_mod.cache_dir() == tmp_path / "brewq"
