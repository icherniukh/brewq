from brewq.shortcut import ensure, owned, path_block, remove


def test_clean_link_repeat_and_remove(tmp_path):
    brewq = tmp_path / "bin" / "brewq"
    brewq.parent.mkdir()
    brewq.write_text("#!/bin/sh\n")
    state = tmp_path / "state.json"
    assert ensure(brewq, brewq.parent, state, "absent") == f"bq -> {brewq}"
    link = brewq.parent / "bq"
    assert link.is_symlink() and link.resolve() == brewq.resolve()
    assert ensure(brewq, brewq.parent, state, "command") == f"bq -> {brewq}"
    assert remove(brewq, brewq.parent, state) == "bq shortcut removed"
    assert not link.exists()
    assert not state.exists()


def test_foreign_command_and_alias_are_preserved(tmp_path):
    brewq = tmp_path / "brewq"
    brewq.write_text("brewq")
    foreign = tmp_path / "bq"
    foreign.write_text("foreign")
    other = tmp_path / "brq"
    other.write_text("other")
    state = tmp_path / "state.json"
    assert "left unchanged" in ensure(brewq, tmp_path, state, "absent")
    assert foreign.read_text() == "foreign"
    assert other.read_text() == "other"
    assert not state.exists()
    assert "shell alias" in ensure(brewq, tmp_path, state, "alias")
    assert foreign.read_text() == "foreign"


def test_remove_does_not_delete_a_foreign_command(tmp_path):
    brewq = tmp_path / "brewq"
    brewq.write_text("brewq")
    foreign = tmp_path / "bq"
    foreign.write_text("foreign")
    assert "left unchanged" in remove(brewq, tmp_path, tmp_path / "state.json")
    assert foreign.read_text() == "foreign"


def test_zsh_none_means_the_name_is_free(monkeypatch):
    import subprocess

    from brewq import shortcut

    monkeypatch.setattr(shortcut, "shutil_which", lambda name: "/bin/zsh")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 1, "bq: none\n", ""))
    assert shortcut.shell_claim("bq") == "absent"


def test_path_block_reports_a_foreign_command(tmp_path):
    brewq = tmp_path / "brewq"
    brewq.write_text("brewq")
    foreign = tmp_path / "other" / "bq"
    foreign.parent.mkdir()
    foreign.write_text("foreign")
    assert path_block(str(foreign), brewq, tmp_path / "state.json")
    assert path_block(None, brewq, tmp_path / "state.json") is None


def test_uv_managed_sibling_is_ours_and_replaced(tmp_path):
    bindir = tmp_path / "tool" / "bin"
    bindir.mkdir(parents=True)
    brewq = bindir / "brewq"
    brewq.write_text("brewq")
    sibling = bindir / "bq"
    sibling.write_text("old")
    shim_dir = tmp_path / "shims"
    shim_dir.mkdir()
    shim = shim_dir / "bq"
    shim.symlink_to(sibling)
    assert owned(shim, brewq, None)
    assert ensure(brewq, shim_dir, tmp_path / "state.json", "command").endswith(str(brewq))
    assert shim.resolve() == brewq.resolve()


def test_dry_run_reports_link_without_creating_anything(tmp_path):
    brewq = tmp_path / "bin" / "brewq"
    brewq.parent.mkdir()
    brewq.write_text("#!/bin/sh\n")
    state = tmp_path / "state.json"
    assert ensure(brewq, brewq.parent, state, "absent", dry_run=True) == f"would link bq -> {brewq}"
    assert not (brewq.parent / "bq").exists()
    assert not state.exists()


def test_dry_run_preserves_everything_it_reports(tmp_path):
    brewq = tmp_path / "brewq"
    brewq.write_text("brewq")
    foreign = tmp_path / "bq"
    foreign.write_text("foreign")
    state = tmp_path / "state.json"
    assert ensure(brewq, tmp_path, state, "absent", dry_run=True).startswith(
        "would leave bq unchanged")
    assert foreign.read_text() == "foreign"
    assert not state.exists()
    assert remove(brewq, tmp_path, state, dry_run=True).startswith("would leave bq unchanged")
    assert foreign.read_text() == "foreign"
    owned_dir = tmp_path / "owned"
    owned_dir.mkdir()
    owned_brewq = owned_dir / "brewq"
    owned_brewq.write_text("brewq")
    assert ensure(owned_brewq, owned_dir, state, "absent") == f"bq -> {owned_brewq}"
    assert remove(owned_brewq, owned_dir, state, dry_run=True) == "would remove bq shortcut"
    assert (owned_dir / "bq").is_symlink()
    assert state.exists()
    assert path_block(str(foreign), brewq, state, dry_run=True).startswith(
        "would leave bq unchanged")


def test_dry_run_remove_reports_stale_state_without_deleting(tmp_path):
    brewq = tmp_path / "brewq"
    brewq.write_text("brewq")
    state = tmp_path / "state.json"
    state.write_text('{"path": "x", "target": "y"}')
    assert remove(brewq, tmp_path, state, dry_run=True) == "would remove bq shortcut state"
    assert state.exists()
    assert remove(brewq, tmp_path, state) == "bq shortcut absent"
    assert not state.exists()
