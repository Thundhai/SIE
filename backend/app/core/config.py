"""Environment-based application configuration.

Settings are read from process environment variables (and a local .env file
in development, see .env.example) via pydantic-settings. Nothing in this
module hardcodes secrets or environment-specific values.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General
    APP_NAME: str = "SIE - Safety Intelligence Engine"
    APP_ENV: str = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # Identity & access (see app/api/deps_auth.py, app/services/identity_service.py)
    #
    # DEV_MODE gates the one development-only identity mechanism this
    # codebase has: a request header naming an existing user id, trusted
    # without any cryptographic verification (see
    # app/api/deps_auth.py::get_dev_authenticated_user_id). It defaults to
    # False specifically so a deployment that forgets to configure real
    # authentication fails closed (every authenticated route returns 501,
    # not "trust a header") rather than silently accepting spoofed
    # identity. This must never be set true in a production environment —
    # see the README's "Identity architecture" section.
    DEV_MODE: bool = False

    # Browser/CORS access (see app/main.py, cors_allowed_origins_list
    # below, docs/FRONTEND_ARCHITECTURE.md's "Browser integration"
    # section) -- SIE Enterprise Read API & Browser Integration
    # Foundation v0.1.
    #
    # Comma-separated list of EXACT browser origins allowed to call this
    # API cross-origin. Never "*" for an authenticated API -- an
    # allow-all origin combined with credentialed requests is exactly
    # what browsers themselves refuse to honor, and it would defeat the
    # whole point of an explicit, reviewable allowlist. The default below
    # is a local-development value only (the new SIE frontend's own
    # `vite --port=3000` dev server) -- any non-local deployment MUST set
    # this explicitly via the CORS_ALLOWED_ORIGINS environment variable
    # to its real frontend origin(s), or browser-based access is refused
    # entirely (fail closed, the same posture DEV_MODE already takes).
    CORS_ALLOWED_ORIGINS: str = "http://localhost:3000"

    # Ingestion (see app/ingestion/storage.py, app/ingestion/pipeline.py)
    #
    # Local-filesystem StorageProvider root. Development-only, per the
    # milestone spec — a production deployment swaps
    # get_storage_provider() for an object-storage-backed implementation
    # rather than pointing this at a "real" path.
    INGESTION_STORAGE_DIR: str = "var/ingested_files"
    # Hard cap on one uploaded file's size, enforced before any parsing
    # is attempted. 25 MiB is a reasonable default for the document/
    # spreadsheet/presentation formats this milestone supports.
    MAX_UPLOAD_SIZE_BYTES: int = 25 * 1024 * 1024

    # Chunking (see app/ingestion/chunking.py::StructureAwareChunkingStrategy).
    # Documented *initial* defaults, not scientifically validated optimal
    # values — see the README's "Knowledge Quality Pipeline" section.
    # Character-based rather than token-based: no tokenizer dependency is
    # introduced by this milestone (that belongs with the future
    # embedding layer, which knows which model's tokenizer to match).
    MIN_CHUNK_CHARACTERS: int = 200
    TARGET_CHUNK_CHARACTERS: int = 1000
    MAX_CHUNK_CHARACTERS: int = 1800
    OVERLAP_CHARACTERS: int = 150

    # Semantic embeddings (see app/embeddings/ and the README's "Semantic
    # Knowledge Architecture" section).
    #
    # EMBEDDING_DIMENSIONS is the single central source of truth for the
    # pgvector column width — app/models/embedding.py's `Vector(...)`
    # column and migrations/versions/0006_*.py both read this value
    # rather than each hardcoding a number. A pgvector column's dimension
    # is fixed at creation time, so changing this requires a new
    # migration (and re-embedding every chunk under a new
    # EMBEDDING_MODEL_VERSION — see EmbeddingService's module docstring;
    # embeddings from different dimensions/models are never compared).
    #
    # EMBEDDING_PROVIDER selects the EmbeddingProvider implementation via
    # app/embeddings/provider.py::get_embedding_provider() — a
    # configuration-based boundary, not a hardcoded import of one
    # provider. "hashing" (the default) is a deterministic, dependency-
    # free, offline embedding — not a trained semantic model — chosen
    # specifically so this milestone's tests and evaluation harness never
    # need network access or a downloaded model (see that module's
    # docstring for the full rationale and the documented real-model
    # extension point).
    EMBEDDING_PROVIDER: str = "hashing"
    EMBEDDING_MODEL_NAME: str = "sie-hashing-embedder"
    EMBEDDING_MODEL_VERSION: str = "v1"
    EMBEDDING_DIMENSIONS: int = 256
    # Do not embed INSUFFICIENT-quality or empty chunks unless a caller
    # explicitly opts in (see app/embeddings/embedding_service.py) —
    # this flag is that one central off-by-default switch, not scattered
    # per-call-site booleans.
    EMBED_INSUFFICIENT_QUALITY_CHUNKS: bool = False

    # Retrieval (see app/retrieval/retrieval_service.py). Documented
    # *initial* defaults calibrated against the deterministic hashing
    # provider above, the same "not scientifically validated optimal
    # values" spirit as the chunking settings — a different
    # EmbeddingProvider produces a different similarity-score
    # distribution and would need its own recalibration.
    RETRIEVAL_DEFAULT_TOP_K: int = 5
    RETRIEVAL_MAX_TOP_K: int = 50
    # Below this cosine similarity, a result is not returned at all (see
    # RetrievalService's NO_RELEVANT_EVIDENCE behavior). Calibrated
    # empirically against HashingEmbeddingProvider: unrelated text
    # consistently scores ~0.0, genuine topical matches score
    # ~0.14-0.45 — see tests/test_embedding_provider.py.
    RETRIEVAL_MIN_SIMILARITY: float = 0.12
    # Relevance-label bucket boundaries above the minimum — see
    # RetrievalService's HIGH/MODERATE/LOW labeling. Never called
    # "confidence" — see the README.
    RETRIEVAL_MODERATE_SIMILARITY: float = 0.20
    RETRIEVAL_HIGH_SIMILARITY: float = 0.30
    # Observability (see app/retrieval/retrieval_service.py). Off by
    # default — a query string may contain an organization's sensitive
    # operational detail ("the leak in tank 4 at the north site"), so it
    # is never written to logs unless a deployment explicitly opts in for
    # development/debugging. Query *length* and a query-content hash
    # (not the query itself) are always logged, enough to correlate
    # requests without exposing content.
    LOG_RETRIEVAL_QUERY_TEXT: bool = False

    # LLM / RAG (see app/llm/provider.py and app/rag/ — "Evidence-Grounded
    # RAG" in the README).
    #
    # LLM_PROVIDER selects the LLMProvider implementation via
    # app/llm/provider.py::get_llm_provider() — the same
    # configuration-based-boundary shape as EMBEDDING_PROVIDER above.
    # "fake" (the default) is a deterministic, offline test/dev provider —
    # not a real AI model — chosen for the identical reason
    # HashingEmbeddingProvider is the default embedding provider: tests
    # and CI must never require network access or a commercial API key.
    # It is a hard, not soft, error to let this default reach a real
    # deployment — see app/llm/provider.py's own "Guardrail" docstring
    # section and FakeLLMProviderInProductionError.
    LLM_PROVIDER: str = "fake"
    LLM_MODEL_NAME: str = "sie-fake-test-llm"
    LLM_MODEL_VERSION: str = "v1"
    LLM_TEMPERATURE: float = 0.0
    LLM_MAX_OUTPUT_TOKENS: int = 800
    LLM_TIMEOUT_SECONDS: float = 30.0
    # Only meaningful for LLM_PROVIDER=openai_compatible. None -> that
    # provider's own default (api.openai.com); set to a self-hosted
    # inference server's URL to point at one instead. Never a secret
    # itself, but see LLM_API_KEY just below.
    LLM_API_BASE_URL: str | None = None
    # Never committed, never logged — read once at provider construction
    # time (app/llm/provider.py::OpenAICompatibleLLMProvider) and never
    # placed in any LLMResponse, exception message, or API response. Unset
    # by default; LLM_PROVIDER=openai_compatible refuses to construct
    # without it rather than silently proceeding unauthenticated.
    LLM_API_KEY: str | None = None
    # Whether the configured non-fake provider sends the grounded context
    # (which may contain organization-private evidence) to a
    # network-reachable service outside this process. True by default —
    # the safe assumption for any provider a deployment configures — since
    # a genuinely self-hosted/private endpoint is the exception, not the
    # rule; a deployment that has one sets this False explicitly. Read by
    # RAGService's privacy boundary check — see
    # ALLOW_EXTERNAL_LLM_FOR_PRIVATE_DATA below.
    LLM_PROVIDER_IS_EXTERNAL: bool = True

    # Evidence selection / cost control (see
    # app/rag/evidence_selection.py). Selection happens before the LLM is
    # ever invoked — these are hard caps on what can reach a prompt at
    # all, not tuning knobs the LLM sees.
    RAG_MAX_EVIDENCE_ITEMS: int = 6
    RAG_MAX_CONTEXT_CHARACTERS: int = 6000
    # Deduplication threshold — see EvidenceSelectionService's own
    # docstring for the token-overlap measure this bounds.
    RAG_DEDUP_SIMILARITY_THRESHOLD: float = 0.85

    # Evidence sufficiency (see app/rag/sufficiency.py). Deterministic
    # rules, never delegated to the LLM — see that module's docstring for
    # the exact rule set this threshold participates in.
    RAG_SUFFICIENT_MIN_EVIDENCE_COUNT: int = 2

    # Source conflict detection (see app/rag/conflict.py) — a
    # deterministic, keyword-based heuristic, not machine learning. Two
    # requirement-type evidence statements are flagged as conflicting when
    # their topic-word overlap (Jaccard, after removing stopwords and
    # requirement/negation cue words) reaches this threshold and their
    # negation polarity differs. Documented *initial* default, not
    # scientifically tuned — see that module's own docstring.
    RAG_CONFLICT_TOPIC_OVERLAP_THRESHOLD: float = 0.3

    # Privacy boundary (milestone item 39): if any selected evidence is
    # ORGANIZATION-scoped (private, not GLOBAL) and the configured
    # LLMProvider.is_external is True, RAGService refuses to call it
    # unless this is explicitly True. Default False — the safe default;
    # a deployment that has confirmed its provider's data-handling terms
    # (or uses a genuinely private/self-hosted endpoint, which should also
    # set LLM_PROVIDER_IS_EXTERNAL=False) opts in explicitly. See the
    # README's "Privacy" section — SIE makes no claim about any specific
    # commercial provider's own privacy/data-retention policy.
    ALLOW_EXTERNAL_LLM_FOR_PRIVATE_DATA: bool = False

    # Observability (see app/rag/rag_service.py). Off by default, the
    # same reasoning as LOG_RETRIEVAL_QUERY_TEXT below: a RAG query or its
    # generated answer may contain an organization's sensitive operational
    # detail. Never written to logs or the audit trail unless a
    # deployment explicitly opts in.
    LOG_RAG_QUERY_TEXT: bool = False
    LOG_RAG_ANSWER_TEXT: bool = False

    # Intelligence & Predictive Analytics Foundation (see app/intelligence/
    # and the README's "Intelligence Architecture" section).
    #
    # Analytical windows (item 17) — never hard-coded at each call site.
    INTELLIGENCE_ANALYTICAL_WINDOWS_DAYS: list[int] = [7, 30, 90, 365]
    INTELLIGENCE_DEFAULT_WINDOW_DAYS: int = 30
    # Baseline period for trend/anomaly comparison (item 31) — the period
    # immediately preceding the analysis window, of this many days.
    INTELLIGENCE_BASELINE_WINDOW_DAYS: int = 90

    # Data sufficiency thresholds (item 30) — event counts in the
    # analysis window below LIMITED are INSUFFICIENT_DATA; below
    # SUFFICIENT are LIMITED_DATA. Documented *initial* defaults, not
    # statistically validated ones — same spirit as the retrieval/RAG
    # thresholds elsewhere in this codebase.
    INTELLIGENCE_SUFFICIENT_DATA_MIN_EVENTS: int = 10
    INTELLIGENCE_LIMITED_DATA_MIN_EVENTS: int = 3

    # Data freshness (item 32) — if the latest ingestion for a source
    # system is older than this many days, analytics surface STALE_DATA
    # rather than silently presenting old data as current.
    INTELLIGENCE_FRESHNESS_THRESHOLD_DAYS: int = 7

    # Trend analysis (item 23) — app/intelligence/trends.py. A trend
    # needs at least this many non-empty periods to be classified at all
    # (fewer -> INSUFFICIENT_DATA); the slope must clear this fraction of
    # the period mean (per period) to be called INCREASING/DECREASING
    # rather than STABLE.
    INTELLIGENCE_TREND_MIN_PERIODS: int = 3
    INTELLIGENCE_TREND_SLOPE_THRESHOLD: float = 0.1

    # Anomaly detection (item 24) — app/intelligence/anomaly.py. A
    # z-score-based method: needs at least this many baseline periods:
    # fewer -> INSUFFICIENT_DATA. |z| at or above the threshold ->
    # ANOMALOUS.
    INTELLIGENCE_ANOMALY_MIN_BASELINE_PERIODS: int = 4
    INTELLIGENCE_ANOMALY_Z_SCORE_THRESHOLD: float = 2.0

    # Risk signal thresholds (item 22) — app/intelligence/signals.py.
    # A current-window count must be at least this many multiples of its
    # baseline rate, AND at least this many events in absolute terms, to
    # be flagged as a surge/cluster signal. Documented initial defaults.
    INTELLIGENCE_SIGNAL_SURGE_MULTIPLIER: float = 2.0
    INTELLIGENCE_SIGNAL_MIN_EVENT_COUNT: int = 3
    # Below this rate, TRAINING_COMPLIANCE_DROP is flagged.
    INTELLIGENCE_TRAINING_COMPLIANCE_THRESHOLD: float = 0.8

    # Privacy (item 34) — safety event `description` free-text and any
    # `attributes` keys listed here are treated as sensitive: never
    # included in analytics feature/signal output, and never logged
    # verbatim (see app/intelligence/privacy.py).
    INTELLIGENCE_SENSITIVE_ATTRIBUTE_KEYS: list[str] = [
        "employee_name",
        "employee_id",
        "personal_id",
        "medical_details",
        "disciplinary_action",
    ]
    LOG_INTELLIGENCE_EVENT_DESCRIPTION: bool = False

    # Intelligence Platform Integration & Enterprise API v0.1 (see the
    # README's own section for this milestone).
    #
    # Rate limiting (item 13) — app/core/rate_limit.py. Off by default so
    # every existing test/local-dev flow is unaffected unless a
    # deployment opts in; a deployment that does should also read that
    # module's own docstring on why the in-memory implementation is not
    # multi-instance-safe. Read/write are separate budgets (a client
    # that's exhausted its write budget can still read).
    RATE_LIMIT_ENABLED: bool = False
    RATE_LIMIT_READ_REQUESTS_PER_MINUTE: int = 120
    RATE_LIMIT_WRITE_REQUESTS_PER_MINUTE: int = 60

    # Idempotency-Key (item 12) — app/core/idempotency.py. How long a
    # stored request/response pair is honored for replay before a reused
    # key is treated as a new request again.
    IDEMPOTENCY_KEY_TTL_HOURS: int = 24

    # Request size limits (item 14) — app/core/request_limits.py. Applied
    # to every request via Content-Length, before the body is ever
    # parsed; MAX_UPLOAD_SIZE_BYTES above remains the more specific,
    # already-enforced limit for a file upload's own multipart body, and
    # `RetrievalSearchRequest.query`/`RAGQueryRequest.query` already cap
    # query length at 2000 characters (pre-existing, unchanged).
    MAX_JSON_BODY_BYTES: int = 1 * 1024 * 1024  # 1 MiB

    # Database
    # Either set DATABASE_URL directly, or set the POSTGRES_* components and
    # let it be assembled below.
    DATABASE_URL: str | None = None

    POSTGRES_USER: str = "sie"
    POSTGRES_PASSWORD: str = "sie"
    POSTGRES_DB: str = "sie"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        """`CORS_ALLOWED_ORIGINS` parsed into a list of exact origins --
        never a wildcard (see that field's own docstring). Blank entries
        (a trailing comma, an unset/empty environment variable) are
        dropped rather than becoming a stray `''` origin string, which
        `CORSMiddleware` would never match against a real `Origin`
        header anyway but is confusing to see reflected in a startup log
        or test assertion. An empty *list* here (every configured entry
        blank, or the variable set to an empty string) means no
        cross-origin browser access is allowed at all -- fail closed,
        not "allow everything"."""
        return [origin.strip() for origin in self.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Cached so environment variables are parsed once per process; tests that
    need different settings should construct Settings() directly instead of
    mutating the cached singleton.
    """
    return Settings()


settings = get_settings()
