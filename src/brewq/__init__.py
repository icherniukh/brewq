"""brewq package."""


def __getattr__(name: str) -> str:
    # Resolved lazily: importlib.metadata costs more than the rest of startup.
    if name == "__version__":
        from importlib.metadata import PackageNotFoundError, version

        try:
            value = version("brewq")
        except PackageNotFoundError:
            value = "0.0.0"
        globals()["__version__"] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
