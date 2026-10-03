"""Task 01D-F3 architecture integrity: Public SIE never imports the
Commercial Core Enterprise Intelligence implementation in-process, and
never queries `commercial_core`-schema tables directly -- the HTTP
boundary (`app/integrations/commercial_core.py` ->
`get_enterprise_intelligence()` -> `cc_service`) is the only path.
Mirrors `tests/test_database_boundary_separation.py::
test_no_proprietary_commercial_core_application_code_in_public_sie`'s
own static-scan pattern.
"""

from __future__ import annotations

import pathlib

APP_DIR = pathlib.Path(__file__).resolve().parent.parent / "app"

#: Private Commercial Core module names the M43-IP-03 extraction moved
#: out of this repository entirely -- see app/api/v1/intelligence.py's
#: own module docstring. Enterprise Intelligence's own entry point and
#: every sibling computation module it depends on.
_EXTRACTED_ENTERPRISE_INTELLIGENCE_MODULES = (
    "app.intelligence.enterprise_intelligence_service",
    "app.intelligence.enterprise_indicators",
    "app.intelligence.enterprise_trend",
    "app.intelligence.enterprise_anomaly",
    "app.intelligence.enterprise_association",
    "app.intelligence.concentration",
    "app.intelligence.recurrence",
    "app.intelligence.risk_score",
    "app.intelligence.explanations",
)


def test_enterprise_intelligence_implementation_module_does_not_exist_in_public_sie():
    """`enterprise_intelligence_service.py` (and its sibling computation
    modules) were extracted to Commercial Core by M43-IP-03 -- they must
    never exist in this repository at all, not merely be unimported."""
    intelligence_dir = APP_DIR / "intelligence"
    assert not (intelligence_dir / "enterprise_intelligence_service.py").exists()
    assert not (intelligence_dir / "enterprise_indicators.py").exists()
    assert not (intelligence_dir / "enterprise_trend.py").exists()
    assert not (intelligence_dir / "enterprise_anomaly.py").exists()
    assert not (intelligence_dir / "enterprise_association.py").exists()


def test_no_app_module_imports_the_extracted_enterprise_intelligence_implementation():
    """Static text scan, independent of whether the module actually
    exists on disk (so this still catches a reintroduced import even if
    someone also reintroduced the file) -- mirrors test 10's own
    `app.recommendation`/`recommendation_candidates` scan exactly."""
    violations: list[str] = []
    for py_file in APP_DIR.rglob("*.py"):
        text_content = py_file.read_text(encoding="utf-8")
        for module_name in _EXTRACTED_ENTERPRISE_INTELLIGENCE_MODULES:
            if module_name in text_content:
                violations.append(f"{py_file}: references {module_name}")
    assert violations == [], "Public SIE must never import the extracted Enterprise Intelligence implementation:\n" + "\n".join(violations)


def test_commercial_core_client_module_imports_no_commercial_core_implementation():
    """`app/integrations/commercial_core.py` is the one file that knows
    how to reach Enterprise Intelligence -- over HTTP only. Proves it
    imports neither the private implementation nor a raw DB session for
    that purpose (it already has no `db: Session` parameter anywhere in
    `HttpCommercialCoreClient`/`get_enterprise_intelligence()` -- this
    is the static-import half of that same guarantee)."""
    source = (APP_DIR / "integrations" / "commercial_core.py").read_text(encoding="utf-8")
    for module_name in _EXTRACTED_ENTERPRISE_INTELLIGENCE_MODULES:
        assert module_name not in source, f"commercial_core.py references {module_name}"
    assert "commercial_core.ontology_concepts" not in source
    assert "FROM commercial_core." not in source
    assert "schema=\"commercial_core\"" not in source


def test_enterprise_intelligence_route_never_queries_commercial_core_schema_directly():
    """`GET /intelligence/enterprise`'s own route function and response
    shaper never issue SQL against the `commercial_core` schema -- the
    `db: Session` dependency it receives (shared with every other route
    in this router, required by FastAPI's own dependency shape) is never
    read inside `enterprise_intelligence()`'s own body; the only call it
    makes is `client.get_enterprise_intelligence(...)`, an HTTP call."""
    source = (APP_DIR / "api" / "v1" / "intelligence.py").read_text(encoding="utf-8")
    # Isolate the Enterprise Intelligence route's own function body
    # (up to the next top-level "def "/"@router" line) rather than
    # scanning the whole file, which legitimately contains real `db.`
    # usage for the unrelated, generic ingestion routes above it.
    start = source.index("def enterprise_intelligence(")
    end = source.index("\n@router.get(\"/sites/{site_id}\"", start)
    route_body = source[start:end]

    assert "db." not in route_body, "the Enterprise Intelligence route must never query the database directly"
    assert "commercial_core." not in route_body
    assert "ontology_concepts" not in route_body
