# Car Insurance Premium Simulator

A production-shaped backend that simulates a car insurance premium. Built
**Docker-first** with DDD, SOLID and Clean Architecture; every financial value is
a `Decimal`; every rule is configuration.

## Architecture

```
presentation/   FastAPI app, Pydantic schemas, routers, error mapping, composition root
      |
infrastructure/ adapters: settings, system clock, SQLAlchemy repo + Alembic + outbox,
      |         HTTP/null GIS providers, structlog logging
      |
application/    use cases (CalculatePremium, GetSimulation, ListSimulations),
      |         ports (Protocols), DTOs                       -- imports domain only
      |
domain/         value objects, PremiumSimulation aggregate, pure domain services,
                domain event, domain errors                  -- imports stdlib only
```

The dependency rule points inward and is enforced by `import-linter`
(`tests/architecture/test_import_rules.py`). `domain/` and `application/` may not
import `fastapi`, `pydantic`, `sqlalchemy` or `httpx`. See
[docs/adr](docs/adr) for the twelve decision records.

### Delivery mechanism — Flask / FastAPI / Django

The HTTP layer is **FastAPI only** (ADR 0011). The architecture is hexagonal, so
a Flask or Django front end would be a new adapter under `presentation/` that
maps HTTP to `application/use_cases` and back, reusing `application/` and
`domain/` unchanged.

## Calculation

`calculation_year` comes from an injectable `Clock` (business timezone
configurable).

```
car_age            = calculation_year - car.year
age_rate           = car_age * AGE_RATE_INCREMENT
value_units        = floor(car.value / VALUE_BAND_AMOUNT)
value_rate         = value_units * VALUE_RATE_INCREMENT

raw_rate           = age_rate + value_rate + BASE_RATE + geographic_adjustment
applied_rate       = quantize(clamp(raw_rate, MINIMUM_APPLIED_RATE, MAXIMUM_APPLIED_RATE))

base_premium       = car.value * applied_rate            # full precision
deductible_discount= base_premium * deductible_percentage
calculated_premium = quantize(base_premium - deductible_discount + broker_fee)

base_policy_limit  = car.value * COVERAGE_PERCENTAGE     # full precision
deductible_value   = quantize(base_policy_limit * deductible_percentage)
policy_limit       = quantize(base_policy_limit - base_policy_limit * deductible_percentage)
```

Only `applied_rate` and the three external money values are quantised; the same
quantised `applied_rate` returned in the response is the one used in the premium.

**`deductible_percentage`: use `0.10` for 10%.**

## Run it (Docker)

```bash
cp .env.example .env

# stateless API only (no database)
docker compose up --build --no-deps api
# -> http://localhost:8000/docs   /redoc   /openapi.json

curl -X POST http://localhost:8000/api/v1/premiums/calculate \
  -H 'content-type: application/json' \
  -d '{"broker_fee":50.0,"car":{"make":"Toyota","model":"Corolla","value":100000.0,"year":2016},"deductible_percentage":0.10}'
```

```json
{
  "applied_rate": 0.1,
  "calculated_premium": 9050.0,
  "car": { "make": "Toyota", "model": "Corolla", "value": 100000.0, "year": 2016 },
  "deductible_value": 10000.0,
  "policy_limit": 90000.0
}
```

### With PostgreSQL persistence

```bash
PERSISTENCE_ENABLED=true docker compose up --build   # brings up api + db
```

`alembic upgrade head` runs automatically in the entrypoint when
`PERSISTENCE_ENABLED=true`. History endpoints then work:

* `GET /api/v1/premiums/{simulation_id}` → `200 | 404`
* `GET /api/v1/premiums?limit=&cursor=` → paginated page

With persistence **off** these return `404` / an empty page and the `calculate`
contract is unchanged.

## Tests and quality gates

```bash
uv sync --extra dev
uv run pytest -m "not integration"     # unit, application, api, architecture
uv run pytest -m integration           # persistence (testcontainers + Docker)
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run lint-imports
```

Coverage gates (CI): **>= 95%** in `domain/`, **>= 90%** overall.

## Configuration matrix

| Variable | Default | Meaning |
|---|---|---|
| `AGE_RATE_INCREMENT` | `0.005` | rate added per year of vehicle age |
| `BASE_RATE` | `0` | flat additive rate |
| `COVERAGE_PERCENTAGE` | `1.00` | base policy limit as a fraction of vehicle value |
| `MINIMUM_APPLIED_RATE` | `0` | rate floor; must be representable at `RATE_DECIMAL_PLACES` |
| `MAXIMUM_APPLIED_RATE` | _(empty)_ | rate ceiling; empty = none; if set, must be representable at `RATE_DECIMAL_PLACES` |
| `MAX_DEDUCTIBLE_PERCENTAGE` | `1.0` | largest accepted deductible; **`0 ≤ x ≤ 1`** (above 100% would make the premium negative) |
| `MIN_VEHICLE_YEAR` | `1900` | oldest accepted model year |
| `VALUE_BAND_AMOUNT` | `10000` | width of a value band |
| `VALUE_RATE_INCREMENT` | `0.005` | rate added per value band |
| `RULES_VERSION` | `2026.08.0` | stamped on responses, events, OpenAPI `version` |
| `CURRENCY_CODE` | `USD` | ISO-4217 currency |
| `MONEY_DECIMAL_PLACES` / `MONEY_ROUNDING_MODE` | `2` / `ROUND_HALF_UP` | money quantisation |
| `RATE_DECIMAL_PLACES` / `RATE_ROUNDING_MODE` | `6` / `ROUND_HALF_UP` | rate quantisation |
| `BUSINESS_TIMEZONE` | `UTC` | timezone for the calendar-year calculation |
| `PERSISTENCE_ENABLED` | `false` | turn PostgreSQL persistence on |
| `DATABASE_URL` | `postgresql+psycopg://insurance:insurance@db:5432/insurance` | DB DSN |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | `5` / `10` | SQLAlchemy pool |
| `PERSISTENCE_FAILURE_MODE` | `fail_closed` | `fail_closed` → 500, `fail_open` → 200 + log |
| `GIS_ENABLED` | `false` | turn the geographic risk provider on |
| `GIS_BASE_URL` / `GIS_API_KEY` | _(empty)_ | external GIS service |
| `GIS_TIMEOUT_SECONDS` | `1.5` | GIS HTTP timeout |
| `GIS_FAILURE_MODE` | `fail_closed` | `fail_closed` → 503, `fail_open` → adjustment 0 + log |
| `GIS_MIN_ADJUSTMENT` / `GIS_MAX_ADJUSTMENT` | `-0.02` / `0.02` | accepted adjustment range |
| `LOG_LEVEL` / `LOG_FORMAT` | `INFO` / `json` | structlog |

Changing any rule = **restart the container**. No rebuild, no code change.
Every value is validated at startup — an invalid rule set (e.g.
`VALUE_BAND_AMOUNT=0`, `MAX_DEDUCTIBLE_PERCENTAGE=1.5`) or, with persistence on,
a malformed `DATABASE_URL`, stops the process rather than failing the first
request. When persistence is **off**, `DATABASE_URL` is ignored entirely and no
database engine is created.

`broker_fee` and `car.value` are capped at `1e11` at the HTTP schema (a value
above that is a `422`, never a `500`); within that range the `Decimal → JSON
number` projection is exact.

## Observability

Structured JSON logs (`structlog`) with `timestamp`, `level`, `event`,
`request_id`, `rules_version`, `route`, `status_code`, `duration_ms`. A
`request_id` is generated per request (or taken from a well-formed
`X-Request-ID`; a hostile value is replaced) and echoed on the response header
and in the sanitised `500` body. The registration location is never logged
beyond its `country` — the GIS adapter logs only the *type* of a failure, never
the request URL, and the `httpx` logger is pinned to `WARNING`. `broker_fee`,
`GIS_API_KEY` and DB credentials are never logged.

The application layer logs through a small `Logger` port (bound to structlog in
infrastructure), so `domain/` and `application/` import no logging library —
`import-linter` forbids `structlog` there alongside the web/ORM stack.

## Known trade-offs

* `Decimal` values are serialised to JSON numbers via an int/float projection;
  it is exact because inputs are capped (see above), but a client that needs
  arbitrary-precision decimals over the wire would want a custom encoder.
* Base image references use tags (`python:3.12-slim`, `postgres:16`), not
  digests — pin to digests for byte-reproducible builds in a regulated setting.
* The outbox table is written transactionally but this repo ships no relay/
  dispatcher (out of scope — see ADR 0006).
