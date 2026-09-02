# Remediation — blind adversarial audit (A1–A11 + minor items)

Round run 2026-09-02 against the committed build (`6b5b166`). Rules of the round
are in `docs/REMEDIATION_PROMPT.md`. Every finding has a regression test that
fails if its fix is reverted; the `tests/api/test_adversarial_audit.py` file
reproduces A1–A9 exactly as a permanent guard.

Gates after this round: `ruff check` / `ruff format --check` clean, `mypy
--strict` (71 files) clean, `import-linter` 2 contracts kept (`structlog` now
forbidden in the core), **353 non-integration tests + 6 integration = 359**,
100% non-integration coverage (statements + branches), 99.6% domain,
`docker build` + both `docker compose` smokes (stateless and persistence-on)
green.

Each fix was mutation-tested: reverting it turns at least one regression test
red (verified for A1 ceilings, A4 httpx pinning + POST body, A7 always-validate,
A8 `except` widening, A10 normalisation, and the aggregate GIS-band guard).

> **Follow-up fix (Red-Green-Refactor).** Hardening surfaced a regression in the
> new aggregate GIS-band guard: it was gated on `registration_location is not
> None`, so with GIS **off** and a location supplied — where the use case passes
> the neutral *zero* adjustment — a configured band that excludes zero
> (`GIS_MIN_ADJUSTMENT=0.01`) produced a spurious 422, contradicting ADR 0010.
> Fixed: zero is the neutral element and is always accepted; the band is only
> re-checked for non-zero adjustments.
> Guard: `tests/domain/test_calculation.py::test_zero_adjustment_is_always_accepted_even_if_the_band_excludes_zero`.

| # | Finding (one line) | Files changed | Tests |
|---|---|---|---|
| **A1** | `Decimal→float` echo corruption; `car.value` unbounded → 500 | `infrastructure/config/settings.py` (`max_vehicle_value`, `max_broker_fee` + validation), `application/use_cases/calculate_premium.py` (ceiling check → 422), `presentation/api/dependencies.py`, `.env.example`, `README.md`, `docs/adr/0013-input-ceilings.md` | `tests/api/test_adversarial_audit.py::test_a1_*`; `tests/api/test_audit_regressions.py::test_huge_value_is_422_not_500`, `::test_large_integer_value_echo_is_exact`; `tests/domain/test_large_and_tiny_values.py::test_default_context_would_have_failed` |
| **A2** | Invalid rule config does not stop startup | `presentation/api/app.py` (`create_app` materialises `get_rating_rules()` + engine) — already in place; `docs/adr/0016-startup-config-validation.md` | `tests/api/test_adversarial_audit.py::test_a2_bad_rule_config_prevents_boot`; `tests/api/test_audit_regressions.py::test_bad_rule_config_prevents_boot` |
| **A3** | `MAX_DEDUCTIBLE_PERCENTAGE > 1` → negative premium | `domain/value_objects/rating_rules.py` (`0 ≤ x ≤ 1`), `presentation/api/schemas.py` (`deductible_percentage` `le=1`) — already in place; `docs/adr/0003-value-bands.md` amendment | `tests/api/test_adversarial_audit.py::test_a3_*`; `tests/api/test_error_contract.py::test_deductible_at_maximum_allowed`, `::test_deductible_just_above_maximum_rejected` |
| **A4** | Sensitive location leaks into GIS logs | `infrastructure/gis/http_geographic_rate_provider.py` (GET+query → **POST+JSON body**; `_fallback` logs only `type(exc).__name__`), `infrastructure/observability/logging.py` (`httpx`/`httpcore` pinned to `WARNING`) — pinning already in place; `docs/adr/0010-gis-adjustment.md` | `tests/api/test_adversarial_audit.py::test_a4_gis_failure_never_logs_the_location`, `::test_a4_httpx_loggers_are_pinned_to_warning`; `tests/api/test_audit_regressions.py::test_gis_fallback_log_has_no_location`; `tests/infrastructure/test_gis_http.py` (body, not query) |
| **A5** | PG schema fixes precision that config leaves open | `infrastructure/persistence/models.py`, `.../alembic/versions/0001_initial.py` — unbounded `Numeric()` already in place | `tests/api/test_adversarial_audit.py::test_a5_numeric_columns_are_unbounded`; `tests/persistence/test_persistence.py::test_six_decimal_place_premium_round_trips_identically`, `::test_migration_matches_orm_models` |
| **A6** | CI smoke hard-codes 2026 | `.github/workflows/ci.yml` — `YEAR=$(( $(date -u +%Y) - 10 ))` / `- 14` already in place | `tests/api/test_adversarial_audit.py::test_a6_ci_smoke_derives_the_year_dynamically` |
| **A7** | Stateless mode still builds the engine; bad DSN → 500 | `infrastructure/config/settings.py` (`make_url` validates shape **always**), `presentation/api/dependencies.py` (`get_engine()->Engine|None`) — engine gating already in place; `docs/adr/0009-optional-persistence.md` | `tests/api/test_adversarial_audit.py::test_a7_*`; `tests/infrastructure/test_adapters.py::test_persistence_off_tolerates_an_unreachable_dsn`, `::test_malformed_dsn_fails_boot_even_with_persistence_off`; `tests/api/test_audit_regressions.py::test_stateless_ignores_an_unreachable_dsn`, `::test_malformed_dsn_stops_the_boot` |
| **A8** | Malformed GIS `200 []` → `TypeError` → 500 | `infrastructure/gis/http_geographic_rate_provider.py` (`except` includes `LookupError, TypeError`; explicit `isinstance(body, dict)` guard) — `except` widening already in place | `tests/api/test_adversarial_audit.py::test_a8_malformed_gis_body_routes_through_failure_mode` (5 bodies × 2 modes); `tests/api/test_audit_regressions.py::test_gis_list_body_is_not_a_500` |
| **A9** | Rate ceiling can be exceeded | `domain/value_objects/rating_rules.py` (`maximum_applied_rate` must be representable at `rate_decimal_places`) — already in place | `tests/api/test_adversarial_audit.py::test_a9_*`; `tests/api/test_audit_regressions.py::test_bad_rule_config_prevents_boot[MAXIMUM_APPLIED_RATE]` |
| **A10** | Swagger gate not met; 422 body carries `input`/`ctx` | `presentation/api/errors.py` (new `RequestValidationError` handler normalising to `loc/msg/type`), `presentation/api/schemas.py` (`ErrorItem` `extra="forbid"`; `examples` on every response/Address field), `presentation/api/routers/premiums.py` (named `openapi_examples` for request + 200/422/500/503), `docs/adr/0008-http-status-codes.md` | `tests/api/test_openapi_contract.py::test_error_responses_are_documented`, `::test_calculate_has_named_examples`; `tests/api/test_openapi_hardening.py::test_calculate_documents_200_422_500_503_with_models_and_examples`; `tests/api/test_error_contract.py::test_domain_error_body_has_fastapi_shape`, `::test_schema_error_also_422` (`== {loc,msg,type}`) |
| **A11** | `structlog` imported in the application layer | `application/ports/logger.py` (`Logger` Protocol + `bind`), `infrastructure/observability/structlog_logger.py` (`bind`), `application/use_cases/calculate_premium.py` (`logger.bind(simulation_id=…)`), `pyproject.toml` + `tests/architecture/test_guards_are_effective.py` (`structlog` forbidden) — port/adapter/guard already in place; `docs/adr/0014-logger-port.md` | `tests/infrastructure/test_adapters.py::test_structlog_logger_bind_returns_a_logger_carrying_fields`; `tests/architecture/test_guards_are_effective.py`; `tests/architecture/test_import_rules.py` |

## Minor items

| Item | Files | Tests |
|---|---|---|
| `# PRODUCT-DECISION:` markers at the decision sites | `domain/value_objects/rating_rules.py`, `infrastructure/config/settings.py` (`maximum_applied_rate`, `currency_code`, `max_deductible_percentage`, input ceilings), `domain/value_objects/address.py` | `tests/architecture` (marker scan is manual; ADR cross-refs 0002/0003/0005/0013) |
| Aggregate rejects a future model year on its own | `domain/aggregates/premium_simulation.py` (already in place) | `tests/domain/test_calculation.py::test_aggregate_rejects_a_future_model_year` |
| Aggregate re-checks the GIS adjustment is in `[gis_min, gis_max]` (zero always allowed) | `domain/value_objects/rating_rules.py` (`gis_min/max_adjustment` fields), `infrastructure/config/rules_factory.py`, `domain/aggregates/premium_simulation.py` | `tests/domain/test_calculation.py::test_aggregate_rejects_an_out_of_band_geographic_adjustment`, `::test_zero_adjustment_is_always_accepted_even_if_the_band_excludes_zero`; `tests/domain/test_vo_branches.py::test_rating_rules_rejects_inverted_gis_band` |
| Outbox atomicity — outbox insert failure rolls back the parent row | (behaviour of `SqlAlchemySimulationRepository.save` + `UnitOfWork.transaction`) | `tests/persistence/test_repository_sqlite.py::test_outbox_insert_failure_rolls_back_the_parent_row` |
| Base images / actions pinned by tag, not digest — conscious decision | `docs/adr/0015-image-tags-not-digests.md` | n/a (ADR) |
