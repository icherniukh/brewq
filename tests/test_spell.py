from brewq.spell import correct


def test_correct_finds_close_misspellings():
    assert "docker" in correct("dockr", ["docker", "nginx", "dockerfile-lint"])


def test_correct_ignores_exact_input_and_unrelated_names():
    assert correct("tmux", ["tmux", "wget"]) == []


def test_correct_empty_query_or_dictionary():
    assert correct("", ["a"]) == []
    assert correct("abc", []) == []


def test_correct_normalizes_case_and_at_signs():
    assert correct("Python3", ["python@3"]) == ["python@3"]


def test_correct_misspell_branch_returns_single_candidate():
    # Deletion-heavy match: only the prefix-like branch applies, so at most one.
    result = correct("ripgrep", ["ripgrep-all", "ripgrep-x"])
    assert len(result) <= 1
