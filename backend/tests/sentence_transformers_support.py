"""Shared support for `sentence-transformers`-dependent tests — SIE
Milestone 21: Real Semantic Embedding & Retrieval Productionization v0.1.

**Deliberately not a `backend/requirements.txt` dependency.** `torch`
(a transitive dependency of `sentence-transformers`) has no CPU-only
build reachable from this project's allowed package sources in a
network-restricted environment — the default PyPI wheel bundles a full
CUDA runtime (500+ MB), and PyTorch's own CPU-only package index
(`download.pytorch.org`) is not on this environment's/CI's allowed-host
list. Making `sentence-transformers`/`torch` a hard requirement would
mean every CI run — even ones that never touch embeddings — downloads
500+ MB on every invocation, exactly what item 17 of this milestone
explicitly warns against ("CI must not depend on downloading a large
[dependency] on every run").

So: `sentence-transformers` (and `torch`) remain a genuinely *optional*
dependency, exactly as `app/embeddings/provider.py`'s own lazy import
already treats it. Tests that need it skip cleanly (not fail) when it
isn't installed — mirroring `tests/postgres_support.py`'s identical
shape for the identical reason. In *this* development session's own
environment, both packages are already installed, so these tests run for
real, locally; CI's own `requirements.txt`-driven install does not
include them, so the same tests report as skipped there — the honest "CI
deterministic regression + separate real-model validation" split this
milestone asks for (see docs/SEMANTIC_EMBEDDING.md).
"""

from __future__ import annotations

import pytest


def _sentence_transformers_available() -> bool:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return True


SENTENCE_TRANSFORMERS_AVAILABLE = _sentence_transformers_available()

requires_sentence_transformers = pytest.mark.skipif(
    not SENTENCE_TRANSFORMERS_AVAILABLE,
    reason=(
        "The optional 'sentence-transformers' package (and its 'torch' "
        "dependency) is not installed in this environment -- see this "
        "module's own docstring for why it is not a hard requirements.txt "
        "dependency."
    ),
)


def build_tiny_offline_model(dimensions: int = 32):
    """A genuinely real, tiny `sentence_transformers.SentenceTransformer`
    built entirely offline (a local vocabulary + randomly-initialized,
    trainable `WordEmbeddings` -> `Pooling` -- no LSTM, no training step;
    fast enough to construct fresh in every test that needs one). Used
    only to exercise `SentenceTransformerEmbeddingProvider`'s own code
    (batching, dimension reporting, output validation) against a real
    model object -- never to claim anything about semantic quality (see
    `scripts/train_local_semantic_model.py` for the actually-trained
    model used for that, in `tests/evaluation/`).
    """
    import numpy as np
    from sentence_transformers import SentenceTransformer
    from sentence_transformers.sentence_transformer.modules import Pooling, WordEmbeddings
    from sentence_transformers.sentence_transformer.modules.tokenizer.whitespace import (
        WhitespaceTokenizer,
    )

    vocab = ["[UNK]", "safety", "harness", "height", "chemical", "spill", "confined", "space", "crane", "lift"]
    rng = np.random.default_rng(7)
    matrix = rng.normal(0, 0.3, size=(len(vocab), dimensions)).astype("float32")
    tokenizer = WhitespaceTokenizer(vocab=vocab, stop_words=[], do_lower_case=True)
    word_embeddings = WordEmbeddings(tokenizer=tokenizer, embedding_weights=matrix, update_embeddings=False)
    pooling = Pooling(embedding_dimension=dimensions, pooling_mode="mean")
    return SentenceTransformer(modules=[word_embeddings, pooling])
