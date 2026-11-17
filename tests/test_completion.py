from __future__ import annotations

import json
import os
import pty
import select
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from brewq import cache, cli


@pytest.fixture
def completion_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("BREWQ_CACHE_DIR", str(tmp_path))
    (tmp_path / "brew-all.json").write_text(json.dumps({
        "formulae": [{"name": "zzcomplete-formula"}, {"name": "duplicate"},
                     {"name": "bad\nname"}, {"name": "$(touch bad)"}],
        "casks": [{"token": "zzcomplete-cask"}, {"token": "duplicate"}],
    }))
    return tmp_path


def test_names_are_deduplicated_and_shell_safe(completion_cache):
    assert cache.completion_names() == ["duplicate", "zzcomplete-cask", "zzcomplete-formula"]


@pytest.mark.parametrize("contents", [None, b"not JSON", b"\xff", b"{}", b'{"formulae":[],"casks":[]}'])
def test_missing_or_invalid_cache_is_quiet(tmp_path, monkeypatch, capsys, contents):
    monkeypatch.setenv("BREWQ_CACHE_DIR", str(tmp_path / "cache"))
    if contents is not None:
        (tmp_path / "cache").mkdir()
        (tmp_path / "cache/brew-all.json").write_bytes(contents)
    before = sorted(tmp_path.rglob("*"))
    assert cli.main(["--_complete"]) == 0
    assert capsys.readouterr() == ("", "")
    assert sorted(tmp_path.rglob("*")) == before


def _require_zsh() -> str:
    zsh = shutil.which("zsh")
    if zsh:
        return zsh
    if os.environ.get("BREWQ_REQUIRE_ZSH") == "1":
        pytest.fail("zsh is required to validate printed completion")
    pytest.skip("zsh is not installed")


def test_printed_completion_is_the_current_zsh_script(tmp_path):
    zsh = _require_zsh()
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    proc = subprocess.run(
        [sys.executable, "-m", "brewq.cli", "+completion", "zsh"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=20,
    )
    assert proc.returncode == 0
    assert proc.stderr == ""
    from brewq.completion import script_errors

    assert script_errors(proc.stdout, cli._build_command_parser()) == []
    path = tmp_path / "completion.zsh"
    path.write_text(proc.stdout)
    syntax = subprocess.run([zsh, "-n", str(path)], capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr
    readme = Path(__file__).resolve().parents[1].joinpath("README.md").read_text()
    assert "source <(brewq +completion zsh)" in readme
    assert "brewq completion zsh" not in readme


def test_completion_bypasses_operational_paths(completion_cache, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("completion must not load config, inventory, seed, or refresh")

    for module, name in ((cli, "_load_cache"), (cli.config_mod, "load"),
                         (cache, "load"), (cache, "refresh"),
                         (cache.inventory_mod, "scan"), (cache, "_write_json"),
                         (cache, "_write_pickle"), (cli, "_finish_cache_command")):
        monkeypatch.setattr(module, name, forbidden)
    assert cli.main(["+completion", "zsh"]) == 0
    script = capsys.readouterr().out
    assert "compdef _brewq brewq bq" in script
    assert "--_complete" in script
    assert cli.main(["--_complete"]) == 0
    assert capsys.readouterr().out.splitlines() == cache.completion_names()


def _complete_in_zsh(tmp_path: Path, line: str) -> str:
    """Press real Tab in ZLE, then capture BUFFER without executing the command."""
    from brewq.completion import zsh_script

    initial, separator, continuation = line.partition("\t")
    keys = (b"\t" + continuation.encode() if separator else b"") + b"\t "
    script = tmp_path / "completion.zsh"
    script.write_text(zsh_script(cli._build_search_parser(), cli._build_command_parser()))
    result = tmp_path / "buffer"
    init = f"""
        autoload -Uz compinit
        compinit -D -i
        source {shlex.quote(str(script))}
        bindkey -e
        _capture_buffer() {{
            print -r -- "$BUFFER" > {shlex.quote(str(result))}
            zle .accept-line
        }}
        zle -N _capture_buffer
        bindkey '^X' _capture_buffer
        value={shlex.quote(initial)}
        _complete_command_line() {{ compstate[vared]=; _main_complete; }}
        zle -C _complete_command_line complete-word _complete_command_line
        bindkey '^I' _complete_command_line
        print READY
        vared -p 'TEST> ' value
    """
    env = {
        "HOME": str(tmp_path), "ZDOTDIR": str(tmp_path), "PATH": os.defpath,
        "TERM": "xterm-256color", "BREWQ_CACHE_DIR": str(tmp_path),
        "XDG_CACHE_HOME": str(tmp_path), "LC_ALL": "C.UTF-8",
    }
    master, slave = pty.openpty()
    proc = subprocess.Popen(
        [shutil.which("zsh"), "-dfic", init], stdin=slave, stdout=slave, stderr=slave,
        env=env, cwd=tmp_path, start_new_session=True,
    )
    os.close(slave)
    output = b""
    sent = False
    deadline = time.monotonic() + 10
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master], [], [], max(0, deadline - time.monotonic()))
            if not ready:
                break
            try:
                chunk = os.read(master, 65536)
            except OSError:
                break
            if not chunk:
                break
            output += chunk
            if not sent and b"READY" in output:
                os.write(master, keys + b"\x18")
                sent = True
        proc.wait(timeout=2)
    finally:
        os.close(master)
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    assert proc.returncode == 0, output.decode(errors="replace")
    assert result.exists(), output.decode(errors="replace")
    return result.read_text().rstrip()


@pytest.mark.parametrize(("line", "expected"), [
    ("bq --so", "bq --sort"),
    ("bq --no-c", "bq --no-color"),
    ("bq --al", "bq --all"),
    ("bq --no-rev", "bq --no-reverse"),
    ("bq --upd", "bq --update"),
    ("bq -i --upd", "bq -i --update"),
    ("bq +update --no-c", "bq +update --no-color"),
    ("brewq --sort tre", "brewq --sort trend"),
    ("bq -s tre", "bq -s trend"),
    ("bq -c name,ve", "bq -c name,ver"),
    ("bq --columns=name,ve", "bq --columns=name,ver"),
    ("bq -i -c name,des", "bq -i -c name,desc"),
    ("bq -c ve\t,des", "bq -c ver,desc"),
    ("bq -c def", "bq -c default"),
    ("bq -c name,def", "bq -c name,default"),
    ("bq -c default,u", "bq -c default,url"),
    ("bq -c name,al", "bq -c name,all"),
    ("bq -c he", "bq -c help"),
    ("bq -c +ve", "bq -c +ve"),
    ("bq -c name,descr", "bq -c name,descr"),
    ("bq -s trending", "bq -s trending"),
    ("bq -i --li", "bq -i --li"),
    ("bq --li", "bq --li"),
    ("bq -i --to", "bq -i --top"),
    ("bq --inst", "bq --installed"),
    ("bq -i zzcomplete-f", "bq -i zzcomplete-formula"),
    ("bq +update --fo", "bq +update --force"),
    ("bq +update --of", "bq +update --offline"),
    ("bq +config pa", "bq +config path"),
    ("bq +completion zs", "bq +completion zsh"),
    ("bq +ran", "bq +ran"),
    ("bq +pre", "bq +pre"),
    ("bq +ref", "bq +ref"),
    ("bq --ur", "bq --ur"),
    ("bq -i --ana", "bq -i --ana"),
    ("bq +li", "bq +li"),
    ("bq zzcomplete-f", "bq zzcomplete-formula"),
    ("brewq zzcomplete-c", "brewq zzcomplete-cask"),
    ("bq -- zzcomplete-f", "bq -- zzcomplete-formula"),
])
def test_actual_zsh_tab_completion(completion_cache, line, expected):
    _require_zsh()
    assert _complete_in_zsh(completion_cache, line).rstrip(" =") == expected


def test_zsh_commands_still_complete_without_cache(tmp_path):
    _require_zsh()
    assert _complete_in_zsh(tmp_path, "bq +upd").rstrip() == "bq +update"
    assert not (tmp_path / "brew-all.json").exists()
