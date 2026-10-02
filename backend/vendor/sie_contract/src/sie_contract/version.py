"""Single source of truth for the contract's version.

Reads the sibling `VERSION` file at import time rather than hardcoding
the string twice (once here, once in pyproject.toml) -- pyproject.toml
is the package-install-time version (read by build tooling); this module
is the *runtime-discoverable* version (Phase 10's "Version: Contract
version is discoverable" requirement) a consumer can check without
needing `importlib.metadata` to have a real installed distribution
(e.g. when this package is vendored/imported straight from a checkout).
"""

from __future__ import annotations

from pathlib import Path

_VERSION_FILE = Path(__file__).resolve().parent.parent.parent / "VERSION"


def _read_version() -> str:
    try:
        return _VERSION_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        # Installed as a built distribution without the VERSION file
        # alongside it (e.g. from a wheel) -- fall back to package
        # metadata, which setuptools populates from pyproject.toml's
        # own [project].version at build time (kept in sync manually
        # with VERSION; tests/test_version.py checks they agree).
        try:
            from importlib.metadata import version as _pkg_version

            return _pkg_version("sie-contract")
        except Exception:  # pragma: no cover -- last-resort fallback only
            return "0.0.0+unknown"


__version__: str = _read_version()
