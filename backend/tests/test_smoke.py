def test_imports_backend_package() -> None:
    import aithru_agent

    assert aithru_agent.__version__ == "0.1.0"
