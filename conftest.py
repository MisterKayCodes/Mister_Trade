# conftest.py
#
# Pytest configuration for the Mister Trade test suite.
# Sets asyncio mode to "auto" so all async test functions
# are automatically treated as coroutines — no need to
# decorate every test with @pytest.mark.asyncio manually.

import pytest

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )
