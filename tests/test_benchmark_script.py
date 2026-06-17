from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_benchmark_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "benchmark.py"
    spec = importlib.util.spec_from_file_location("benchmark_script", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_summarize_times_reports_milliseconds():
    bench = _load_benchmark_module()

    summary = bench.summarize_times("search", [0.010, 0.020, 0.030], failures=0)

    assert summary.name == "search"
    assert summary.iterations == 3
    assert summary.min_ms == 10.0
    assert summary.median_ms == 20.0
    assert summary.mean_ms == 20.0
    assert summary.max_ms == 30.0
    assert summary.failures == 0


def test_select_cases_returns_requested_cases_in_requested_order():
    bench = _load_benchmark_module()

    selected = bench.select_cases(["search_tsv", "cache_status"])

    assert [case.name for case in selected] == ["search_tsv", "cache_status"]


def test_select_cases_rejects_unknown_case():
    bench = _load_benchmark_module()

    try:
        bench.select_cases(["missing"])
    except ValueError as exc:
        assert "Unknown benchmark case" in str(exc)
    else:
        raise AssertionError("select_cases should reject unknown names")


def test_format_markdown_table_contains_core_columns():
    bench = _load_benchmark_module()
    summaries = [
        bench.Summary(
            name="search",
            iterations=2,
            min_ms=10.0,
            median_ms=12.5,
            mean_ms=12.5,
            max_ms=15.0,
            failures=0,
            command="brewq json",
        )
    ]

    table = bench.format_markdown_table(summaries)

    assert "| case | iters | min | median | mean | max | failures | command |" in table
    assert "| search | 2 | 10.0ms | 12.5ms | 12.5ms | 15.0ms | 0 | `brewq json` |" in table
