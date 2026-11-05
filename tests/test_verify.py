from __future__ import annotations

import runpy
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify.py"


@pytest.mark.parametrize("broken", [None, "filter", "completion", "old-help", "layout"])
@pytest.mark.parametrize("metavars", [False, True])
def test_installed_gate_checks_behavior_not_just_version(monkeypatch, broken, metavars):
    check = runpy.run_path(str(SCRIPT))["check_installed_shim"]
    version = check.__globals__["__version__"]
    monkeypatch.setitem(check.__globals__, "_external_entrypoint", lambda name: f"/tools/{name}")
    calls = []

    def run(argv, **kwargs):
        args = argv[1:]
        calls.append((args, kwargs))
        code, output = 0, ""
        if args == ["--version"]:
            output = f"brewq {version}\n"
        elif args == ["--help"]:
            output = "-c, --columns --full-help --tsv --top --limit"
            if broken != "old-help":
                output += " -i, --installed"
            if metavars:
                output = output.replace("-c, --columns", "-c COLS, --columns COLS")
        elif args == ["completion", "zsh"]:
            output = "" if broken == "completion" else "compdef _brewq brewq bq\n"
        else:
            output = "zzverify-hidden\n" if broken == "filter" else "zzverify-installed-a\n"
            if "--tsv" not in args:
                output = ("NAME  TYPE  VERSION  DESCRIPTION\n" if broken == "layout" else "NAME  DESCRIPTION\n")
                output += "zzverify-installed-a  useful description\n"
            assert kwargs["cwd"] != str(SCRIPT.parent.parent)
            assert "PYTHONPATH" not in kwargs["env"]
            assert kwargs["env"]["PATH"].endswith("no-brew")
        return subprocess.CompletedProcess(argv, code, output, "")

    monkeypatch.setattr(subprocess, "run", run)
    result = check()
    assert result.ok == (broken is None)
    assert len(calls) > 4  # Both entrypoints must execute real behavioral cases.


def test_relative_path_discovery_survives_working_directory_change(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    executable = bindir / "bq"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setenv("PATH", "../bin")
    discover = runpy.run_path(str(SCRIPT))["_external_entrypoint"]
    found = discover("bq")
    assert Path(found).is_absolute()
    monkeypatch.chdir(tmp_path)
    assert Path(found).samefile(executable)
