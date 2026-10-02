"""Task 01D-A: the vendored Shared Contract (`sie_contract`).

Two independent concerns, each with its own test group below:

1. **The vendored package itself is genuinely usable** -- it imports, its
   version matches what this repository's `vendor/sie_contract/` claims to
   have vendored, its documented public API is actually present, and it
   still holds the same "never imports Commercial Core internals" property
   that `Thundhai/SIE-Commercial-Core`'s own `sie-contract/tests/
   test_private_model_isolation.py` proves at the source.

2. **The vendored copy has not silently drifted from its declared
   provenance** -- `vendor/sie_contract/PROVENANCE.json` records the exact
   source commit/version this copy came from and a hash of every file that
   makes up the package; this recomputes that same hash against what is
   actually on disk. See `vendor/sie_contract/PROVENANCE.md` for what to do
   if this test ever fails because a real contract update is in progress
   (re-vendor and update the recorded hash together -- never edit a
   vendored file in place without doing so).

Nothing here tests `CommercialCoreClient` -- it does not exist yet; see
`app/integrations/commercial_core.py`'s own docstring.
"""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

VENDOR_ROOT = Path(__file__).resolve().parent.parent / "vendor" / "sie_contract"
PROVENANCE_PATH = VENDOR_ROOT / "PROVENANCE.json"

# Mirrors Thundhai/SIE-Commercial-Core's own sie-contract/tests/
# test_private_model_isolation.py -- the private-implementation prefixes a
# Commercial Core checkout forbids `sie_contract` from importing. Kept
# identical here deliberately: this is the same invariant, checked against
# the same source files, from the consuming side.
FORBIDDEN_PREFIXES = (
    "app.intelligence",
    "app.predictions",
    "app.rag",
    "app.risk_assessment",
    "app.validation",
    "app.models",
    "app.services",
    "app.api",
    "app.main",
)

# The exact public API sie-contract/src/sie_contract/__init__.py's own
# __all__ declares as of contract version 0.2.0 (see PROVENANCE.json).
EXPECTED_EXPORTS = {
    "__version__",
    "ActorType",
    "ServiceIdentity",
    "TenantContext",
    "ErrorResponse",
    "KnownErrorCode",
    "AsOfWindow",
    "EvidenceReference",
    "EvidenceType",
    "Page",
    "AttentionCategoryStatus",
    "AttentionCategoryStatusDTO",
    "AttentionItemDTO",
    "AttentionPriority",
    "AttentionResultDTO",
    "AttentionScope",
    "IntelligenceContextCategoryStatus",
    "IntelligenceContextCategoryStatusDTO",
    "IntelligenceContextSummaryDTO",
    "DecisionReferenceDTO",
    "CitationReferenceDTO",
    "RAGAnswerDTO",
    "IntelligenceOverallStatus",
    "IntelligenceStatusDTO",
}


def _load_provenance() -> dict:
    assert PROVENANCE_PATH.is_file(), f"missing provenance metadata: {PROVENANCE_PATH}"
    return json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))


def _compute_source_tree_sha256(provenance: dict) -> str:
    """Mirrors PROVENANCE.json's own documented `hash_algorithm` exactly:
    sha256 over each `vendored_files` entry, in listed order, as
    `relative_posix_path + "\\n" + raw_file_bytes`."""
    digest = hashlib.sha256()
    for rel_path in provenance["vendored_files"]:
        file_path = VENDOR_ROOT / rel_path
        assert file_path.is_file(), f"provenance names {rel_path!r} but it is missing from disk: {file_path}"
        digest.update(rel_path.encode("utf-8"))
        digest.update(b"\n")
        digest.update(file_path.read_bytes())
    return digest.hexdigest()


# --- Group 1: the vendored package is genuinely usable --------------------------------------------


def test_sie_contract_imports_successfully():
    import sie_contract  # noqa: F401


def test_sie_contract_version_matches_expected_contract_version():
    import sie_contract

    assert sie_contract.__version__ == "0.2.0"


def test_sie_contract_exposes_the_expected_public_api():
    import sie_contract

    actual_exports = set(sie_contract.__all__)
    missing = EXPECTED_EXPORTS - actual_exports
    unexpected = actual_exports - EXPECTED_EXPORTS
    assert not missing, f"sie_contract is missing expected exports: {sorted(missing)}"
    assert not unexpected, (
        f"sie_contract exposes exports this test doesn't expect: {sorted(unexpected)} -- "
        "if this is a real, approved contract update, update EXPECTED_EXPORTS here as part "
        "of that same re-vendor."
    )
    for name in EXPECTED_EXPORTS:
        assert hasattr(sie_contract, name), f"sie_contract.__all__ names {name!r} but it isn't actually importable"


def test_sie_contract_source_never_imports_commercial_core_internals():
    """Static AST scan, not a runtime check -- catches an import even in a
    branch nothing else here happens to execute. Scans the vendored copy's
    own source tree directly, independent of PROVENANCE.json."""
    py_files = sorted((VENDOR_ROOT / "src" / "sie_contract").glob("*.py"))
    assert len(py_files) >= 5, f"expected multiple source files under {VENDOR_ROOT}, found {len(py_files)}"

    violations: list[str] = []
    for path in py_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "app" or alias.name.startswith("app.") or alias.name.startswith(FORBIDDEN_PREFIXES):
                        violations.append(f"{path.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "app" or module.startswith("app.") or module.startswith(FORBIDDEN_PREFIXES):
                    violations.append(f"{path.name}: from {module} import ...")
    assert violations == [], "vendored sie_contract must never import app.* (either repository's):\n" + "\n".join(violations)


def test_importing_sie_contract_does_not_pull_in_any_app_module():
    for mod_name in list(sys.modules):
        if mod_name == "app" or mod_name.startswith("app."):
            del sys.modules[mod_name]  # pragma: no cover -- defensive, should never fire

    import sie_contract  # noqa: F401

    app_modules_present = [name for name in sys.modules if name == "app" or name.startswith("app.")]
    assert app_modules_present == [], f"importing sie_contract pulled in app.* modules: {app_modules_present}"


# --- Group 2: the vendored copy matches its declared provenance -----------------------------------


def test_provenance_metadata_is_present_and_well_formed():
    provenance = _load_provenance()
    required_keys = {
        "source_repository",
        "source_path",
        "source_commit",
        "source_contract_version",
        "vendored_at",
        "vendored_files",
        "source_tree_sha256",
    }
    missing_keys = required_keys - provenance.keys()
    assert not missing_keys, f"PROVENANCE.json is missing required keys: {sorted(missing_keys)}"
    assert provenance["source_repository"] == "Thundhai/SIE-Commercial-Core"
    assert provenance["source_path"] == "sie-contract"
    assert isinstance(provenance["vendored_files"], list) and provenance["vendored_files"]


def test_contract_version_agrees_across_runtime_version_file_and_provenance():
    import sie_contract

    provenance = _load_provenance()
    version_file = VENDOR_ROOT / "VERSION"
    on_disk_version = version_file.read_text(encoding="utf-8").strip()

    assert sie_contract.__version__ == on_disk_version, (
        f"sie_contract.__version__ ({sie_contract.__version__!r}) disagrees with "
        f"vendor/sie_contract/VERSION ({on_disk_version!r})"
    )
    assert sie_contract.__version__ == provenance["source_contract_version"], (
        f"sie_contract.__version__ ({sie_contract.__version__!r}) disagrees with "
        f"PROVENANCE.json's source_contract_version ({provenance['source_contract_version']!r}) -- "
        "a version was bumped in one place without the other."
    )


def test_vendored_source_tree_has_not_drifted_from_the_recorded_provenance():
    """The one check that would fail if a vendored file were edited
    independently (per PROVENANCE.md's own explicit prohibition), or if
    PROVENANCE.json's own hash were updated without actually re-vendoring."""
    provenance = _load_provenance()
    recomputed = _compute_source_tree_sha256(provenance)
    assert recomputed == provenance["source_tree_sha256"], (
        "vendor/sie_contract's source tree does not match PROVENANCE.json's recorded "
        f"source_tree_sha256 (expected {provenance['source_tree_sha256']!r}, computed {recomputed!r}). "
        "If this is a real, approved contract update, re-vendor per PROVENANCE.md's own "
        "'How to actually update this vendored copy' section rather than editing files in place."
    )
