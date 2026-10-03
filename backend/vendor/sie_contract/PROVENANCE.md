# Provenance — vendored `sie_contract`

**This directory is a controlled, vendored copy. Do not edit it independently.**

Everything under `src/sie_contract/`, plus `pyproject.toml` and `VERSION`, is a
byte-for-byte copy of the `sie-contract` package as it exists at a specific
commit of `Thundhai/SIE-Commercial-Core`. It is copied here, rather than
installed as a private Git dependency or from a package registry, because
Task 01D's architecture audit (see that memo) found no distribution
mechanism already in place that Public SIE's Render build could use to
reach that private repository without new credential provisioning.
Vendoring needs none: Public SIE's build never has to authenticate to
`Thundhai/SIE-Commercial-Core` to obtain this code.

See `PROVENANCE.json` for the machine-readable record
(`tests/test_sie_contract_vendored.py` reads it directly):

- **Source repository:** `Thundhai/SIE-Commercial-Core`
- **Source path:** `sie-contract/` (that repository's own contract package)
- **Source commit:** `9b0c2c652e99bb08ae07b0a4a1d569af95d49e80` (`claude/task-01d-f3-enterprise-intelligence-boundary` — Task 01D-F3's own Enterprise Intelligence-boundary branch, **not yet merged to `main`**; re-vendor again from `main` once that branch merges)
- **Source contract version:** `0.4.0`
- **Vendored:** 2026-10-03

## Why this exists, and why it is not a decision to redesign anything

This bridge exists to unblock a Public SIE `sie_contract` dependency without
any of: creating a new repository, publishing a package, or adding a private
Git dependency (all explicitly out of scope for this step — see the
architecture-decision memo this vendoring implements). It does not implement
a real `CommercialCoreClient`, does not change any intelligence-endpoint
behavior, and does not touch the contract's own DTO/API design in any way —
every file here reads identically to its source.

## How drift is caught

`PROVENANCE.json`'s `source_tree_sha256` is a hash over every file listed in
`vendored_files`, computed in that exact order. `tests/
test_sie_contract_vendored.py` recomputes that same hash against the files
actually on disk and fails if it disagrees — whether because a file was
edited independently, added, or removed, or because `PROVENANCE.json`
itself was edited without a matching re-vendor. The same test also checks
`sie_contract.__version__` against both `VERSION` and this file's own
`source_contract_version`, so a version bump in one place that wasn't
carried to the others is caught the same way.

## How to actually update this vendored copy

1. In `Thundhai/SIE-Commercial-Core`, resolve `sie-contract`'s own change
   through that repository's normal process — this file is never where a
   contract change is authored.
2. Re-copy `pyproject.toml`, `VERSION`, and every `src/sie_contract/*.py`
   file from the new source commit into this directory, replacing the
   existing copies exactly (no merge, no partial update).
3. Recompute `source_tree_sha256` (see `PROVENANCE.json`'s own
   `hash_algorithm` field for the exact procedure) and update
   `source_commit`, `source_contract_version`, and `vendored_at` together,
   in the same change.
4. Run `tests/test_sie_contract_vendored.py` — a mismatch anywhere in
   step 3 fails loudly rather than silently drifting.
