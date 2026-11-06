from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_license_and_upstream_notices_are_retained():
    license_text = (ROOT / "LICENSE").read_text()
    notice = (ROOT / "NOTICE").read_text()
    assert "Copyright (c) 2026 Ivan Cherniukh" in license_text
    assert "Permission is hereby granted" in license_text
    assert "Copyright (c) 2009-present, Homebrew contributors" in notice
    assert "BSD 2-Clause License" in notice
    assert "Copyright (c) 2014-2016 Yuki Nishijima" in notice
    assert "DidYouMean" in notice
