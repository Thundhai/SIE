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

    # Production authentication (OIDC/OAuth2) -- SIE Milestone 20:
    # Production Authentication & Identity Foundation v0.1. See
    # app/services/oidc_verifier.py for the token-verification
    # implementation these settings configure, and
    # app/api/deps_auth.py::get_authenticated_user_id for how a request is
    # routed here versus the DEV_MODE-only mechanism above.
    #
    # Provider-neutral by design: SIE never imports or hardcodes a
    # specific identity provider's SDK. Any standards-compliant OIDC
    # provider (Azure AD, Okta, Auth0, Google, a self-hosted Keycloak,
    # ...) is supported purely by configuring these values to that
    # provider's own issuer/audience/JWKS endpoint -- nothing provider-
    # specific lives in this codebase. OIDC_ISSUER, OIDC_AUDIENCE and
    # OIDC_JWKS_URL are all required together for a production Bearer
    # token to be accepted at all -- a deployment with DEV_MODE=False that
    # is missing any of the three fails closed (see
    # get_oidc_verifier()'s own docstring), never silently accepts the
    # token or falls back to DEV_MODE's header mechanism.
    OIDC_ISSUER: str | None = None
    OIDC_AUDIENCE: str | None = None
    # The provider's JWKS endpoint (e.g.
    # "https://your-tenant.example.com/.well-known/jwks.json"). SIE does
    # not perform OIDC discovery (`/.well-known/openid-configuration`)
    # itself -- a deployment supplies its provider's JWKS URL directly,
    # keeping the configuration surface small and explicit rather than an
    # extra network round trip at every process start.
    OIDC_JWKS_URL: str | None = None
    # Comma-separated list of accepted JWS algorithms, passed directly to
    # PyJWT's `algorithms=` (see app/services/oidc_verifier.py). PyJWT
    # itself refuses the "none" algorithm's signature-less tokens
    # regardless of this list; the default below is a real asymmetric
    # algorithm, not a placeholder a deployment would need to remember to
    # change to be secure.
    OIDC_ALGORITHMS: str = "RS256"
    # How long a fetched JWKS key set is cached before being re-fetched
    # (seconds) -- see PyJWT's PyJWKClient `lifespan` kwarg.
    OIDC_JWKS_CACHE_TTL_SECONDS: int = 3600
    # Human-facing label recorded on Identity.provider and audit metadata
    # for every identity this verifier resolves (e.g. "azuread", "okta")
    # -- display/filtering only, never the actual trust boundary (that's
    # OIDC_ISSUER) -- see app/models/identity.py.
    OIDC_PROVIDER_LABEL: str = "oidc"

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

    # Real embedding provider runtime configuration — SIE Milestone 21:
    # Real Semantic Embedding & Retrieval Productionization v0.1. Only
    # consulted when EMBEDDING_PROVIDER="sentence_transformers"
    # (app/embeddings/provider.py::SentenceTransformerEmbeddingProvider);
    # ignored by HashingEmbeddingProvider. All server-side configuration
    # only — there is no API parameter anywhere that lets a request
    # choose a model, a device, or a filesystem path (see that module's
    # own docstring, "Security").
    #
    # EMBEDDING_MODEL_NAME (above) doubles as this provider's
    # `model_name_or_path`: either a real model id resolvable via the
    # `sentence-transformers`/`huggingface_hub` download-and-cache
    # mechanism (e.g. "sentence-transformers/all-MiniLM-L6-v2" — see
    # docs/SEMANTIC_EMBEDDING.md's "Recommended production model"
    # section), or a local filesystem directory already containing a
    # saved sentence-transformers model (e.g. a pre-baked image layer, or
    # EMBEDDING_MODEL_CACHE_DIR populated ahead of time) — both are
    # standard, documented `SentenceTransformer(...)` constructor
    # behavior, not a special case added here.
    #
    # None (the default) lets sentence-transformers/torch pick
    # automatically (GPU if available, else CPU). Set explicitly
    # ("cpu"/"cuda"/"cuda:0"/"mps") to pin it — e.g. to guarantee a CPU-
    # only deployment never silently tries to allocate a GPU it doesn't
    # have, or the reverse.
    EMBEDDING_DEVICE: str | None = None
    # Where downloaded model weights are cached on disk, so a real
    # deployment's *second* process start (and every subsequent one)
    # reuses the already-downloaded model rather than re-fetching it —
    # see docs/SEMANTIC_EMBEDDING.md's "Model loading & lifecycle"
    # section. None lets sentence-transformers use its own default cache
    # directory (`~/.cache/torch/sentence_transformers` /
    # `SENTENCE_TRANSFORMERS_HOME`). Never committed to Git — this is a
    # runtime cache path, not a repository artifact (see backend/.gitignore).
    EMBEDDING_MODEL_CACHE_DIR: str | None = None
    # Passed straight to `SentenceTransformer.encode(batch_size=...)` —
    # the real, effective batching control (item 7): EmbeddingService
    # calls `embed_texts()` once with every chunk that needs embedding,
    # and the provider itself is what actually chunks that list into
    # batch_size-sized minibatches for the underlying model. Larger
    # values trade memory for throughput; 32 is sentence-transformers'
    # own documented default.
    EMBEDDING_BATCH_SIZE: int = 32
    # Documented, best-effort budget for one embed_texts() call — **not
    # currently enforced by preemption**. A real hard timeout on
    # synchronous CPU/GPU tensor inference would require running it in a
    # separate, killable process (subprocess isolation), which this
    # milestone deliberately does not introduce (see its own "do not
    # introduce Celery/background workers" exclusion) — a thread-based
    # `.result(timeout=...)` wrapper cannot actually stop CPU-bound
    # PyTorch work already running, so it would raise a timeout error
    # while silently leaking the still-running computation, which is
    # worse than not enforcing one at all. Recorded here so the
    # *configuration surface* exists and is documented (item 4), and so a
    # future worker-based embedding milestone (explicitly out of this
    # one's scope) has an obvious place to actually enforce it via
    # process-level cancellation.
    EMBEDDING_INFERENCE_TIMEOUT_SECONDS: float = 60.0

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

    # SIE Milestone 22: Enterprise Intelligence & Risk Analytics
    # Foundation v0.1 (see backend/docs/ENTERPRISE_INTELLIGENCE_RISK_ANALYTICS.md).
    # This section governs `app/intelligence/enterprise_*.py`,
    # `app/intelligence/concentration.py`, `app/intelligence/recurrence.py`
    # and `app/intelligence/risk_score.py` only -- the pre-existing
    # `INTELLIGENCE_*` settings above (trend/anomaly/signal/sufficiency)
    # are untouched and still govern `app/intelligence/trends.py`,
    # `anomaly.py`, `signals.py`. Every threshold below is a documented
    # *initial* default, not a scientifically validated one -- the same
    # standing caveat every other threshold in this file carries.
    #
    # The closed set of analysis windows this milestone's own endpoints
    # accept (item 4) -- deliberately a fixed, small vocabulary (not the
    # open `1..3650` range `GET .../analytics/*` accepts) so "invalid
    # window" is a real, testable 400, not merely a documented convention.
    ENTERPRISE_INTELLIGENCE_ALLOWED_WINDOW_DAYS: list[int] = [7, 30, 90, 180]
    ENTERPRISE_INTELLIGENCE_DEFAULT_WINDOW_DAYS: int = 30

    # Period-over-period trend classification (item 6) --
    # app/intelligence/enterprise_trend.py. The *combined* (current +
    # previous period) count of the primary lagging metric (total
    # INCIDENT events) must reach this many before a trend is classified
    # at all -- fewer -> INSUFFICIENT_DATA, never a score built on noise.
    # Above that floor, a percentage change at or beyond this fraction is
    # DETERIORATING (increase) or IMPROVING (decrease); anything narrower
    # is STABLE.
    ENTERPRISE_TREND_MIN_COMBINED_EVENTS: int = 5
    ENTERPRISE_TREND_CHANGE_THRESHOLD: float = 0.20

    # Recurrence/pattern detection (item 8) --
    # app/intelligence/recurrence.py. Occurrence-count bands for one
    # (site, event_type) or (site, event_subtype) combination within the
    # analysis window. A count of 1 is simply a single event, not a
    # pattern -- classify_recurrence() below WATCH begins.
    ENTERPRISE_RECURRENCE_WATCH_MIN: int = 2
    ENTERPRISE_RECURRENCE_RECURRING_MIN: int = 3
    ENTERPRISE_RECURRENCE_HIGH_MIN: int = 5

    # Risk concentration (item 7) -- app/intelligence/concentration.py.
    # A dimension (e.g. "which site") is only ranked at all once its
    # total population reaches this floor -- a single-event "100%
    # concentration" at one site is not statistically meaningful and must
    # never be presented as such. Above that floor, one contributor's
    # share of the total is banded into LOW/MODERATE/HIGH risk
    # contribution at these two cut points.
    ENTERPRISE_CONCENTRATION_MIN_POPULATION: int = 5
    ENTERPRISE_CONCENTRATION_MODERATE_THRESHOLD: float = 0.20
    ENTERPRISE_CONCENTRATION_HIGH_THRESHOLD: float = 0.50

    # SIE Milestone 23: Enterprise Intelligence Explainability & Anomaly
    # Foundation v0.1 (see backend/docs/ENTERPRISE_INTELLIGENCE_RISK_ANALYTICS.md).
    # Reuses the pre-existing INTELLIGENCE_ANOMALY_MIN_BASELINE_PERIODS
    # (minimum baseline periods required before a non-INSUFFICIENT_DATA
    # result) and INTELLIGENCE_ANOMALY_Z_SCORE_THRESHOLD (the |z| cutoff)
    # above unchanged -- both already existed and already govern
    # app/intelligence/anomaly.py::detect_anomaly(), the same function
    # this milestone's own app/intelligence/enterprise_anomaly.py calls.
    # This is the one genuinely new anomaly setting this milestone adds:
    # a cap on how many *preceding* periods are ever fetched as baseline,
    # even when an organization/site has far more history available --
    # bounds the per-metric query cost and keeps the baseline "recent
    # history", not "all of history since the beginning of time".
    ENTERPRISE_ANOMALY_BASELINE_PERIODS_MAX: int = 6

    # SIE Milestone 24: Enterprise Intelligence Pattern & Correlation
    # Foundation v0.1 (see backend/docs/ENTERPRISE_INTELLIGENCE_RISK_ANALYTICS.md).
    # Governs app/intelligence/association.py (the pre-existing, milestone
    # item 26/54 Pearson-correlation function, extended additively -- its
    # own two pre-existing parameters, `min_periods`/`threshold`, now
    # default from the two settings below rather than a hardcoded literal,
    # with identical default *values* so no pre-existing caller's or
    # test's behavior changes) and app/intelligence/enterprise_association.py
    # (this milestone's new multi-metric pairwise scan).
    #
    # Minimum aligned periods before a pair's correlation is computed at
    # all (item 7) -- fewer -> INSUFFICIENT_DATA, never a correlation
    # computed from two or three observations. Matches
    # INTELLIGENCE_ANOMALY_MIN_BASELINE_PERIODS's own default (4) for
    # consistency across this codebase's statistical foundations.
    ENTERPRISE_ASSOCIATION_MIN_PERIODS: int = 4
    # Upper bound on how many recent periods are ever fetched to build the
    # aligned metric vectors, even when far more history exists -- mirrors
    # ENTERPRISE_ANOMALY_BASELINE_PERIODS_MAX's identical rationale:
    # "recent history", not "all of history since the beginning of time".
    ENTERPRISE_ASSOCIATION_MAX_PERIODS: int = 6
    # The pre-existing `outcome` field's own threshold
    # (ASSOCIATION_OBSERVED vs. NO_ASSOCIATION_OBSERVED) -- unchanged
    # value (0.5), now centralized here instead of a literal default
    # argument.
    ENTERPRISE_ASSOCIATION_OBSERVED_THRESHOLD: float = 0.5
    # The new, finer six-value `AssociationClassification` band (item 5).
    # |r| >= STRONG -> STRONG_POSITIVE/STRONG_NEGATIVE;
    # MODERATE <= |r| < STRONG -> MODERATE_POSITIVE/MODERATE_NEGATIVE;
    # |r| < MODERATE -> WEAK. Documented *initial* defaults -- the same
    # standing caveat every other threshold in this file carries.
    ENTERPRISE_ASSOCIATION_STRONG_THRESHOLD: float = 0.7
    ENTERPRISE_ASSOCIATION_MODERATE_THRESHOLD: float = 0.4
    # No MAX_PAIRS setting: the association-eligible metric vocabulary
    # (app/intelligence/enterprise_association.py::SUPPORTED_ASSOCIATION_METRICS)
    # is a fixed, closed set of 7 metrics -- exactly 21 unordered pairs,
    # always, never scaling with event volume or organization size, so no
    # additional bound is needed (item 19's own "if required" caveat).

    # SIE Milestone 25: Enterprise Risk Assessment Foundation v0.1 (see
    # backend/docs/ENTERPRISE_INTELLIGENCE_RISK_ANALYTICS.md's own
    # "Risk assessment methodology" section). Governs
    # app/risk_assessment/risk_matrix.py -- the deterministic
    # likelihood x consequence -> risk-band calculation applied to both
    # inherent and residual risk (item 9's own worked example: 5x5=25,
    # 1x1=1). Both dimensions are a governed 1-5 integer scale (item 9);
    # these three thresholds are the upper (inclusive) bound of
    # LOW/MODERATE/HIGH -- anything above HIGH_MAX is CRITICAL.
    # Documented *initial* defaults, not a claim that this is universally
    # applicable to every client's own corporate risk matrix (item 9's
    # own explicit caveat).
    RISK_ASSESSMENT_LOW_MAX: int = 4
    RISK_ASSESSMENT_MODERATE_MAX: int = 9
    RISK_ASSESSMENT_HIGH_MAX: int = 16
    RISK_ASSESSMENT_METHODOLOGY_VERSION: str = "risk-assessment-v1"
    # The default analysis window used to compute an assessment's
    # read-only, never-persisted `intelligence_context` (item 26) --
    # reuses ENTERPRISE_INTELLIGENCE_DEFAULT_WINDOW_DAYS's own identical
    # default (30) for consistency, but kept as its own setting since a
    # risk assessment's window is conceptually independent of the
    # enterprise intelligence endpoints' own.
    RISK_ASSESSMENT_DEFAULT_WINDOW_DAYS: int = 30

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

    @property
    def oidc_algorithms_list(self) -> list[str]:
        """`OIDC_ALGORITHMS` parsed into a list -- see that field's own
        docstring. Blank entries are dropped the same way
        `cors_allowed_origins_list` drops them."""
        return [alg.strip() for alg in self.OIDC_ALGORITHMS.split(",") if alg.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Cached so environment variables are parsed once per process; tests that
    need different settings should construct Settings() directly instead of
    mutating the cached singleton.
    """
    return Settings()


settings = get_settings()
