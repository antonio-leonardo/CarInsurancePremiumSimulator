# ADR 0015 — Base images and actions pinned by tag, not digest

## Status
Accepted (2026-09-02)

## Context
The adversarial audit raised that `Dockerfile` (`python:3.12-slim`),
`docker-compose.yml` (`postgres:16`) and the CI workflow
(`actions/checkout@v4`, `astral-sh/setup-uv@v3`) reference mutable tags rather
than immutable `@sha256:` / commit-SHA digests, so a rebuild is not guaranteed
bit-reproducible.

## Decision
Keep the tags. Reproducibility of the **application** is anchored by
`uv.lock` (every Python dependency pinned by version **and** hash) and by the
Alembic migration being run — not `metadata.create_all` — in tests and the
entrypoint. The base OS layer is deliberately allowed to receive patch updates:

* `python:3.12-slim` / `postgres:16` — we *want* the latest security patches for
  the `3.12` / `16` line on each rebuild; a frozen digest would silently rot.
* `actions/*` — pinned to a major tag, which the publisher maintains as a
  moving pointer to vetted releases.

A digest pin would be revisited if this service moved to an environment with a
supply-chain policy that mandates it (e.g. SLSA level 3), at which point a
Renovate/Dependabot digest-bump workflow would be added to keep the pins fresh.

## Consequences
* Rebuilds pick up base-image CVE fixes automatically.
* The trade-off (a compromised upstream tag could inject a bad layer) is
  accepted for a coding-exercise service and is mitigated by the hash-locked
  Python layer, which is where application code and its dependencies live.
