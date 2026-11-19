"""Help text and the real parsers must describe the same command line.

Each check derives its expectations from the argparse parsers, so adding,
renaming or hiding an option without updating the help fails here.
"""
from __future__ import annotations

import argparse
import re
import shlex

import pytest

from brewq import cli
from brewq.options import SORT_CHOICES

# A flag mentioned in prose: "-u", "--no-color", "`-a`". Not "TSV-only",
# "+x/-x" or "-1" (lookbehind rules out word characters, "/", "+" and "-").
_FLAG = re.compile(r"(?<![\w/+-])(--?[A-Za-z][\w-]*)")
# A brewq invocation inside help prose: "brewq ripgrep", "`brewq +update --force`".
_EXAMPLE = re.compile(r"\bbrewq((?: [^|`\n]+)?)")


def _search() -> argparse.ArgumentParser:
    return cli._build_search_parser()


def _actions() -> dict[str, argparse.ArgumentParser]:
    return dict(cli._build_command_parser()._brewq_subcommands)  # pyright: ignore[reportAttributeAccessIssue]


def _parsers() -> dict[str, argparse.ArgumentParser]:
    return {"search": _search(), **_actions()}


def _option_strings(parser: argparse.ArgumentParser) -> set[str]:
    return {s for action in parser._actions for s in action.option_strings}


def _help_texts() -> dict[str, str]:
    """Rendered help for every parser, plus --full-help for search."""
    texts = {name: parser.format_help() for name, parser in _parsers().items()}
    texts["full-help"] = cli._full_help_text()
    return texts


def _parse(argv: list[str]) -> argparse.Namespace:
    """Parse like cli._main, without running the command."""
    argv = cli._join_column_edits(argv)
    if argv and argv[0].startswith("+"):
        return cli._build_command_parser().parse_args(argv)
    return _search().parse_intermixed_args(argv)


@pytest.mark.parametrize("name", list(_parsers()))
def test_every_option_is_listed_in_its_help(name):
    parser = _parsers()[name]
    help_text = parser.format_help()
    for action in parser._actions:
        if not action.option_strings:
            continue
        assert action.help is not argparse.SUPPRESS, f"{name}: hidden option {action.option_strings}"
        for option in action.option_strings:
            assert re.search(rf"(?<![\w-]){re.escape(option)}(?![\w-])", help_text), (
                f"{name}: {option} is accepted but missing from help"
            )


@pytest.mark.parametrize("name", list(_help_texts()))
def test_every_flag_mentioned_in_help_exists(name):
    """Prose and epilogs may only name real options of that parser.

    Action help may also mention search options. Full ``brewq ...`` examples
    are checked by parsing them (below), so they are left out here.
    """
    known = _option_strings(_search())
    if name in _actions():
        known |= _option_strings(_actions()[name])
    prose = _EXAMPLE.sub("", _help_texts()[name])
    mentioned = set(_FLAG.findall(prose))
    assert mentioned - known == set(), f"{name} help names unknown options"


@pytest.mark.parametrize("name", list(_help_texts()))
def test_every_example_in_help_parses(name):
    examples = [
        shlex.split(match.strip())
        for text in [_help_texts()[name]]
        for part in text.split(" | ")
        for match in _EXAMPLE.findall(part)
    ]
    # Usage lines ("usage: brewq [options] ...") are templates, not examples.
    examples = [argv for argv in examples if not any(t.startswith("[") for t in argv)]
    for argv in examples:
        try:
            _parse(argv)
        except SystemExit as exc:
            pytest.fail(f"{name}: example `brewq {shlex.join(argv)}` does not parse ({exc})")


def test_sort_help_lists_exactly_the_sort_choices():
    sort = next(a for a in _search()._actions if "--sort" in a.option_strings)
    listed = re.search(r"sort key: (.+?) \(default", sort.help or "")
    assert listed, "-s help no longer lists its fields"
    assert tuple(listed.group(1).split(", ")) == SORT_CHOICES


def test_action_choices_are_shown_in_help():
    for name, parser in _actions().items():
        help_text = parser.format_help()
        for action in parser._actions:
            for choice in action.choices or ():
                assert choice in help_text, f"{name}: choice {choice!r} missing from help"
