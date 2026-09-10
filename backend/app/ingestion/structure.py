"""Structure detection — the pipeline stage between normalization and
knowledge units:

    Normalized Content -> Structure Detection -> Knowledge Units

Generic (format-agnostic) on purpose: rather than every adapter
reimplementing hierarchy tracking, this module walks an already-ordered
`list[NormalizedContent]` once and fills in `section_path` wherever it
can, using whatever signal each item already carries. Two signals are
recognized today:

  * `metadata["heading_level"]` — an integer, set by adapters that can
    cheaply determine true multi-level structure (currently only
    `DOCXAdapter`, via its heading-style stack — see docx_adapter.py).
    Items carrying this build a real hierarchy: pushing/popping a
    heading stack exactly like a table of contents would, so a
    Section 4.2 paragraph gets `section_path = ["Working at Height",
    "Fall Protection"]`, not just its immediate heading.
  * A bare `section_title` with no `heading_level` (e.g. PDF's
    per-page best-effort heading guess) — treated as a single-element
    path, at LOW structural confidence, since a page-level heuristic
    cannot know whether that heading is nested under another one.

Where neither signal is present, `section_path` stays `None` and
`structure_confidence` is recorded as `"none"` — this module never
fabricates hierarchy it isn't reasonably confident about; see the
milestone's own instruction not to attempt "perfect structural
understanding" and to record lower confidence instead.

This function is pure and operates only on the in-memory list — it has
no database dependency, matching `app/ingestion/pipeline.py`'s own
constraint.
"""

from app.ingestion.normalized_content import NormalizedContent, NormalizedContentType


def detect_structure(items: list[NormalizedContent]) -> list[NormalizedContent]:
    """Return a new list of `NormalizedContent` with `section_path` (and
    `metadata["structure_confidence"]`) filled in. Does not mutate the
    input list's items (Pydantic models are copied, not edited in
    place) — callers get a distinct, structure-aware list back."""
    result: list[NormalizedContent] = []
    heading_stack: list[tuple[int, str]] = []  # (level, title), outermost first

    for item in items:
        heading_level = item.metadata.get("heading_level")

        if heading_level is not None and item.content_type == NormalizedContentType.TEXT:
            # A heading: pop anything at this level or deeper, then push
            # this one — a standard table-of-contents stack.
            while heading_stack and heading_stack[-1][0] >= heading_level:
                heading_stack.pop()
            heading_stack.append((heading_level, item.title or item.text.strip()))
            path = [title for _, title in heading_stack]
            result.append(
                _with_structure(item, section_path=path, confidence="high")
            )
            continue

        if heading_stack:
            # Body content following one or more tracked headings.
            path = [title for _, title in heading_stack]
            result.append(_with_structure(item, section_path=path, confidence="high"))
            continue

        if item.section_title:
            # No heading stack (e.g. PDF's per-page guess) but the
            # adapter itself supplied a single best-effort title — carry
            # it as a one-element path, explicitly lower confidence: a
            # page-level heuristic cannot know its true nesting depth.
            result.append(
                _with_structure(item, section_path=[item.section_title], confidence="low")
            )
            continue

        # No structural signal at all (e.g. a spreadsheet row, a slide
        # with no title, a table with no preceding heading).
        result.append(_with_structure(item, section_path=None, confidence="none"))

    return result


def _with_structure(
    item: NormalizedContent, *, section_path: list[str] | None, confidence: str
) -> NormalizedContent:
    metadata = dict(item.metadata)
    metadata["structure_confidence"] = confidence
    update = {"metadata": metadata}
    if section_path is not None:
        update["section_path"] = section_path
        if not item.section_title:
            update["section_title"] = section_path[-1]
    return item.model_copy(update=update)
