import pytest


@pytest.fixture(autouse=True)
def fast_retries(monkeypatch):
    from algo import nse
    monkeypatch.setattr(nse, "SLEEP", 0)
