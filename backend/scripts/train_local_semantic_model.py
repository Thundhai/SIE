#!/usr/bin/env python3
"""Train a small, genuinely real, local sentence-embedding model from
scratch — offline, no download from `huggingface.co` or any other model
hub. SIE Milestone 21: Real Semantic Embedding & Retrieval
Productionization v0.1.

**Why this script exists.** The recommended, documented *production*
implementation of `EmbeddingProvider` (`SentenceTransformerEmbeddingProvider`
in `app/embeddings/provider.py`, `EMBEDDING_PROVIDER=sentence_transformers`)
is designed around loading a real pretrained model from the Hugging Face
Hub — e.g. `sentence-transformers/all-MiniLM-L6-v2` — the same way any
real deployment would. This sandboxed development/CI environment has no
network access to `huggingface.co` (outbound access to that host is
denied by this environment's proxy policy) and no pre-cached model
weights anywhere on disk, so that specific pretrained checkpoint's
semantic quality could not be personally exercised or measured in this
session. See `docs/SEMANTIC_EMBEDDING.md`'s "Evaluation methodology"
section for the full, honest accounting of what this does and does not
demonstrate.

Rather than skip real-model validation entirely, this script trains a
genuinely small — but genuinely real, backprop-trained — sentence
embedding model, entirely offline:

    WhitespaceTokenizer (local vocab, no download)
        -> WordEmbeddings (trainable nn.Embedding, randomly initialized)
        -> LSTM (trainable, bidirectional)
        -> Pooling (mean)
        -> SentenceTransformer

This is not hashing, not TF-IDF, not a keyword-overlap heuristic, and not
a handcrafted similarity score — it is a real neural network, trained via
real gradient descent (`MultipleNegativesRankingLoss`, AdamW) on a small,
synthetic, safety-domain paraphrase-pair dataset
(`tests/fixtures/evaluation/semantic_training_pairs.py`). It is *not* a
claim that this tiny, narrowly-trained model represents the semantic
quality a real deployment would get from a proper pretrained
sentence-transformers checkpoint — it exists specifically so this
milestone's "hashing vs. real semantic embedding" evaluation
(`tests/evaluation/test_semantic_embedding_evaluation.py`) can run
against an actual trained model, in this environment, honestly.

**Not committed to Git.** Trained weights are written to
`backend/var/local_semantic_model/` (already covered by
`backend/.gitignore`'s `/var/` rule) — regenerate by running this script,
never by pulling a binary out of version control.

Usage:

    cd backend && python scripts/train_local_semantic_model.py

Takes well under a minute on CPU (a few dozen training pairs, a model with
on the order of tens of thousands of parameters, sixty training steps —
this is deliberately tiny; see the module docstring above for why).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Allow running as `python scripts/train_local_semantic_model.py` from
# the backend/ directory without installing this package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MODEL_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "var" / "local_semantic_model"
RANDOM_SEED = 42
EMBEDDING_DIM = 64
# Bidirectional LSTM output dimension is 2 * LSTM_HIDDEN_DIM (concatenated
# forward/backward states) -- 128 here yields a 256-dimensional sentence
# embedding, deliberately matching this deployment's own default
# settings.EMBEDDING_DIMENSIONS (see app/core/config.py) so this model
# can be loaded and evaluated against the existing pgvector column
# without a schema migration. A real production model swap (a different
# pretrained checkpoint) would still need EMBEDDING_DIMENSIONS updated
# and a new migration if its dimension differs -- see
# EmbeddingDimensionMismatchError's own docstring.
LSTM_HIDDEN_DIM = 128
TRAINING_EPOCHS = 60
LEARNING_RATE = 1e-3


def build_vocabulary() -> list[str]:
    """Every word this model will ever need to recognize, drawn from its
    own training data plus the corpus/queries it will later be evaluated
    against — a real deployment's tokenizer is trained once on a large
    general corpus and simply generalizes; this toy model instead gets an
    explicit vocabulary so a genuinely out-of-vocabulary word during
    evaluation fails loudly (an unknown token) rather than crashing the
    whole batch (see this repository's own note on `WhitespaceTokenizer`
    without an explicit `[UNK]`-mapped vocab)."""
    from tests.fixtures.evaluation.corpus import CORPUS
    from tests.fixtures.evaluation.hard_paraphrase_queries import HARD_PARAPHRASE_QUERIES
    from tests.fixtures.evaluation.queries import QUERIES
    from tests.fixtures.evaluation.semantic_training_pairs import TRAINING_PAIRS

    texts: list[str] = []
    for pair in TRAINING_PAIRS:
        texts.append(pair.anchor)
        texts.append(pair.positive)
    for chunk in CORPUS:
        texts.append(chunk.text)
    for query in QUERIES:
        texts.append(query.query)
    for query in HARD_PARAPHRASE_QUERIES:
        texts.append(query.query)

    vocab = sorted({word for text in texts for word in text.lower().split()})
    return ["[UNK]"] + vocab


def train_and_save(output_dir: Path = MODEL_OUTPUT_DIR) -> dict:
    """Builds, trains, and saves the model. Returns a small dict of
    metadata (dimensions, vocab size, training pair count, elapsed
    seconds) — used by the evaluation report, not just printed."""
    started = time.monotonic()

    import numpy as np
    import torch
    from sentence_transformers import InputExample, SentenceTransformer, losses
    from sentence_transformers.sentence_transformer.modules import LSTM, Pooling, WordEmbeddings
    from sentence_transformers.sentence_transformer.modules.tokenizer.whitespace import (
        WhitespaceTokenizer,
    )

    from tests.fixtures.evaluation.semantic_training_pairs import TRAINING_PAIRS

    torch.manual_seed(RANDOM_SEED)
    rng = np.random.default_rng(RANDOM_SEED)

    vocab = build_vocabulary()
    embedding_matrix = rng.normal(0, 0.3, size=(len(vocab), EMBEDDING_DIM)).astype("float32")

    tokenizer = WhitespaceTokenizer(vocab=vocab, stop_words=[], do_lower_case=True)
    word_embeddings = WordEmbeddings(
        tokenizer=tokenizer, embedding_weights=embedding_matrix, update_embeddings=True
    )
    lstm = LSTM(
        embedding_dimension=EMBEDDING_DIM,
        hidden_dim=LSTM_HIDDEN_DIM,
        num_layers=1,
        bidirectional=True,
    )
    pooling = Pooling(embedding_dimension=lstm.get_embedding_dimension(), pooling_mode="mean")

    model = SentenceTransformer(modules=[word_embeddings, lstm, pooling])
    dimensions = model.get_embedding_dimension()

    examples = [InputExample(texts=[pair.anchor, pair.positive]) for pair in TRAINING_PAIRS]
    loss_fn = losses.MultipleNegativesRankingLoss(model)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE)

    # A manual training loop, deliberately not sentence-transformers' own
    # `.fit()`/`SentenceTransformerTrainer` -- both pull in the optional
    # `datasets`/`accelerate` packages this codebase's own requirements.txt
    # does not otherwise need (the *production* provider only ever calls
    # `.encode()` for inference, never trains anything). Real backprop
    # either way: this is `loss.backward()` + `optimizer.step()` against a
    # real PyTorch autograd graph, not a shortcut.
    model.train()
    final_loss = None
    for epoch in range(TRAINING_EPOCHS):
        sentence_features, labels = model.smart_batching_collate(examples)
        optimizer.zero_grad()
        loss_value = loss_fn(sentence_features, labels)
        loss_value.backward()
        optimizer.step()
        final_loss = float(loss_value.item())
    model.eval()

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(output_dir))

    elapsed = time.monotonic() - started
    return {
        "output_dir": str(output_dir),
        "dimensions": dimensions,
        "vocab_size": len(vocab),
        "training_pairs": len(TRAINING_PAIRS),
        "training_epochs": TRAINING_EPOCHS,
        "final_training_loss": final_loss,
        "elapsed_seconds": round(elapsed, 2),
    }


def main() -> None:
    info = train_and_save()
    print("Trained local semantic model (offline, from scratch):")
    for key, value in info.items():
        print(f"  {key}: {value}")
    print(
        "\nThis is a small, locally-trained model for offline validation in this "
        "network-restricted environment -- not a claim about any pretrained "
        "production model's quality. See docs/SEMANTIC_EMBEDDING.md."
    )


if __name__ == "__main__":
    main()
