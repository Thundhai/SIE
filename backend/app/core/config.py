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


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Cached so environment variables are parsed once per process; tests that
    need different settings should construct Settings() directly instead of
    mutating the cached singleton.
    """
    return Settings()


settings = get_settings()
