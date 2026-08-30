# ADR 0007 — SOLID mapping

## Status
Accepted (2026-08-30)

## Decision
* **SRP** — three separate calculators (`RateCalculator`, `PremiumCalculator`,
  `PolicyLimitCalculator`); the use case orchestrates, the aggregate assembles.
* **OCP** — new adapters (a real GIS client, a different store, a Kafka
  publisher) are added without touching `domain/`.
* **LSP** — port contracts are exercised by shared behavioural expectations
  (`Null*` vs real adapters return the same shapes; integration tests assert
  both modes).
* **ISP** — ports are small and single-purpose: `Clock.now`,
  `EventPublisher.publish`, `GeographicRateProvider.adjustment_for`,
  `Logger.{info,warning,error}`, `SimulationRepository.{get,list,save}`.
* **DIP** — `domain/` and `application/` depend only on abstractions (including
  a `Logger` port, so no logging library leaks into those layers — enforced by
  `import-linter`, which forbids `structlog` there); concretions are wired in
  `presentation/api/dependencies.py`.
