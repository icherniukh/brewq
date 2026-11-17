import pytest

from brewq import config


@pytest.fixture(autouse=True)
def _fresh_config_diagnostics():
    """Config diagnostics print once per process; reset between tests."""
    config._REPORTED.clear()
    yield
