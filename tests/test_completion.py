from __future__ import annotations

import json
import os
import pty
import select
import shlex
import shutil
import subprocess
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


@pytest.mark.skipif(not shutil.which("zsh"), reason="zsh is not installed")
@pytest.mark.parametrize(("line", "expected"), [
    ("bq --so", "bq --sort"),
    ("brewq --sort tre", "brewq --sort trending"),
    ("bq -s tre", "bq -s trending"),
    ("bq -c name,ver", "bq -c name,version"),
    ("bq --columns=name,ver", "bq --columns=name,version"),
    ("bq -c +ver", "bq -c +version"),
    ("bq -c +name,-descr", "bq -c +name,-description"),
    ("bq -c=-descr", "bq -c=-description"),
    ("bq list -c=-descr", "bq list -c=-description"),
    ("bq -c ver\t,descr", "bq -c version,description"),
    ("bq -c def", "bq -c default"),
    ("bq -c name,def", "bq -c name,def"),
    ("bq -c +version,hel", "bq -c +version,hel"),
    ("bq +list --li", "bq +list --limit"),
    ("bq --li", "bq --limit"),
    ("bq +list --to", "bq +list --top"),
    ("bq --inst", "bq --installed"),
    ("bq -i zzcomplete-f", "bq -i zzcomplete-formula"),
    ("bq +refresh --fo", "bq +refresh --force"),
    ("bq +update-cache --fo", "bq +update-cache --force"),
    ("bq +config pa", "bq +config path"),
    ("bq +completion zs", "bq +completion zsh"),
    ("bq +ran", "bq +random"),
    ("bq zzcomplete-f", "bq zzcomplete-formula"),
    ("brewq zzcomplete-c", "brewq zzcomplete-cask"),
    ("bq -- zzcomplete-f", "bq -- zzcomplete-formula"),
])
def test_actual_zsh_tab_completion(completion_cache, line, expected):
    assert _complete_in_zsh(completion_cache, line).rstrip(" =") == expected


@pytest.mark.skipif(not shutil.which("zsh"), reason="zsh is not installed")
def test_zsh_commands_still_complete_without_cache(tmp_path):
    assert _complete_in_zsh(tmp_path, "bq +ran").rstrip() == "bq +random"
    assert not (tmp_path / "brew-all.json").exists()
