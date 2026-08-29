import importlib

import app.main as main_mod


def test_docs_enabled_by_default():
    # The test process has ENABLE_DOCS unset, so docs stay on (dev behavior).
    from app.main import app

    assert app.docs_url == "/docs"
    assert app.redoc_url == "/redoc"
    assert app.openapi_url == "/openapi.json"


def test_docs_disabled_when_enable_docs_false(monkeypatch):
    monkeypatch.setattr(main_mod.settings, "enable_docs", False)
    importlib.reload(main_mod)
    try:
        assert main_mod.app.docs_url is None
        assert main_mod.app.redoc_url is None
        assert main_mod.app.openapi_url is None
    finally:
        monkeypatch.setattr(main_mod.settings, "enable_docs", True)
        importlib.reload(main_mod)
