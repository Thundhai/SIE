"""Request size limits — Intelligence Platform Integration & Enterprise
API v0.1, item 14.

`RequestSizeLimitMiddleware` enforces one thing, before any parsing
happens: a plain JSON request body may not exceed
`settings.MAX_JSON_BODY_BYTES`, checked from the `Content-Length` header
so an oversized request is rejected before its body is even read into
memory. **Multipart file uploads are exempt** — `app/api/v1/ingestion.py`
already enforces its own, more specific `MAX_UPLOAD_SIZE_BYTES` limit
once it has the actual file in hand (existing behavior, unchanged; see
that module and `app/ingestion/pipeline.py`) — this middleware would
otherwise apply a JSON-sized ceiling to a legitimately larger document
upload.

Two more specific limits were already enforced at the schema level,
closer to what they're actually about, before this milestone — unchanged
here, just confirmed still intact:

  * batch size — `app/schemas/intelligence.py::SafetyEventBatchCreate.events`
    caps at 1000 (`max_length=1000`).
  * retrieval/RAG query length — `RetrievalSearchRequest.query`/
    `RAGQueryRequest.query` cap at 2000 characters (`max_length=2000`;
    see `app/schemas/retrieval.py`/`app/schemas/rag.py`).
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings

# Never applied to a multipart/form-data body (file uploads) or a GET/DELETE
# with no body -- see module docstring.
_LIMITED_CONTENT_TYPE_PREFIXES = ("application/json",)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        content_type = request.headers.get("content-type", "")
        if content_type.startswith(_LIMITED_CONTENT_TYPE_PREFIXES):
            content_length = request.headers.get("content-length")
            if content_length is not None:
                try:
                    size = int(content_length)
                except ValueError:
                    size = None
                if size is not None and size > settings.MAX_JSON_BODY_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "detail": (
                                f"Request body ({size} bytes) exceeds the maximum allowed size "
                                f"({settings.MAX_JSON_BODY_BYTES} bytes) for a JSON request."
                            ),
                            "error": {
                                "code": "VALIDATION_ERROR",
                                "message": "Request body too large.",
                                "request_id": getattr(request.state, "request_id", None),
                            },
                        },
                    )
        return await call_next(request)
