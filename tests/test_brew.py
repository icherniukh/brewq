from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from brewq import brew


def test_info_all_uses_current_trusted_tap_behavior():
    completed = subprocess.CompletedProcess(
        [], 0, stdout='{"formulae": [], "casks": []}', stderr=""
    )
    with patch("brewq.brew._brew_path", return_value="/opt/homebrew/bin/brew"), \
         patch("brewq.brew.subprocess.run", return_value=completed) as run:
        result = brew.info_all(timeout=12)

    assert result == {"formulae": [], "casks": []}
    run.assert_called_once_with(
        ["/opt/homebrew/bin/brew", "info", "--json=v2"],
        capture_output=True,
        text=True,
        check=True,
        timeout=12,
    )


def test_info_all_surfaces_homebrew_error_reason_concisely():
    failure = subprocess.CalledProcessError(
        1,
        ["brew", "info"],
        output="",
        stderr=(
            "Warning: an unrelated warning\n"
            "Error: a tap formula could not be imported\n"
            "a long follow-up explanation\n"
        ),
    )
    with patch("brewq.brew._brew_path", return_value="/opt/homebrew/bin/brew"), \
         patch("brewq.brew.subprocess.run", side_effect=failure), \
         pytest.raises(
             brew.BrewCommandError,
             match=r"^brew info failed: Error: a tap formula could not be imported$",
         ):
        brew.info_all()


def test_info_all_reports_exit_status_when_homebrew_is_silent():
    failure = subprocess.CalledProcessError(
        2, ["brew", "info"], output="", stderr=""
    )
    with patch("brewq.brew._brew_path", return_value="/opt/homebrew/bin/brew"), \
         patch("brewq.brew.subprocess.run", side_effect=failure), \
         pytest.raises(brew.BrewCommandError, match=r"brew info failed: exited with status 2"):
        brew.info_all()


def test_info_all_reports_timeout_without_command_repr():
    failure = subprocess.TimeoutExpired(["brew", "info"], 7)
    with patch("brewq.brew._brew_path", return_value="/opt/homebrew/bin/brew"), \
         patch("brewq.brew.subprocess.run", side_effect=failure), \
         pytest.raises(brew.BrewCommandError, match=r"^brew info timed out after 7s$"):
        brew.info_all(timeout=7)
