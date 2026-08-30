# PROMPT DE EXECUÇÃO — Car Insurance Premium Simulator

> Documento vinculante para a fase de codificação. Complementa e prevalece sobre
> trechos conflitantes do plano executivo original e da errata.

## 0. Papel, contexto e regras invioláveis

Você atua como **Arquiteto/Engenheiro Sênior Python**, entregando código de produção. O repositório está **vazio** (só `.git`). Não há Python nem `uv` na máquina; **há Docker**. Portanto, tudo roda **Docker-first**: build, testes, lint, type-check e execução acontecem dentro de containers.

Regras que **não podem ser violadas**:

1. **DDD + SOLID + Clean Architecture.** A regra de dependência aponta sempre para o domínio. `domain/` não importa nada de `application/`, `infrastructure/` ou `presentation/`. `application/` não importa `infrastructure/` nem `presentation/`.
2. **`Decimal` em todo cálculo financeiro e de taxa. `float` é proibido** em `domain/` e `application/`. Conversão de entrada: `Decimal(str(valor))`.
3. **Ordem alfabética** de definições de função/método dentro de cada módulo e classe, e de parâmetros dentro de cada assinatura — exceto `self`, `cls` e ordem imposta por framework (parâmetros de rota FastAPI). Prefira **parâmetros keyword-only** (`*`) em qualquer função com 2+ parâmetros no domínio e na aplicação. Isso é verificado por teste AST (item 11).
4. **`domain/` e `application/` não importam `fastapi`, `pydantic`, `sqlalchemy`, `httpx`.** Verificado por `import-linter`.
5. **TDD por fase.** Cada fase tem um *gate* objetivo (item 12). Não avance sem o gate verde.
6. **Nada de banco, fila, cache ou broker além do especificado.** PostgreSQL só no caminho opcional de persistência.
7. **Sem segredos no repositório.** Tudo por env var, documentado em `.env.example`.
8. Para as **4 decisões de produto em aberto** (item 14), implemente os defaults documentados aqui e marque com `# PRODUCT-DECISION:` + ADR. Não bloqueie.

## 1. Stack fixada

| Item | Escolha |
|---|---|
| Linguagem | Python 3.12 |
| Dependências | `uv` (lockfile versionado) |
| API | FastAPI + Uvicorn |
| Schemas/Settings | Pydantic v2 + `pydantic-settings` |
| Persistência (opcional) | SQLAlchemy 2.x (estilo imperativo/`Mapped`), Alembic, `psycopg` (v3) |
| Testes | `pytest`, `pytest-cov`, `hypothesis`, `httpx`/`TestClient`, `testcontainers[postgres]` |
| Qualidade | `ruff` (lint+format), `mypy --strict`, `import-linter` |
| Logs | `structlog` com renderer JSON |
| Container | Dockerfile multi-stage, usuário não root, `HEALTHCHECK` |
| Orquestração | `docker-compose.yml` (serviços `api` e `db: postgres:16`) |
| CI | GitHub Actions |

## 2. Layout de diretórios (exato)

```
.
├── src/car_insurance/
│   ├── domain/
│   │   ├── aggregates/        premium_simulation.py
│   │   ├── entities/          (vazio nesta versão — aggregate root é a entidade)
│   │   ├── events/            premium_simulation_calculated.py
│   │   ├── services/          policy_limit_calculator.py, premium_calculator.py, rate_calculator.py
│   │   ├── value_objects/     address.py, money.py, percentage.py, rating_rules.py,
│   │   │                      simulation_id.py, vehicle_snapshot.py, vehicle_year.py
│   │   └── errors.py          exceções de domínio (DomainError e subclasses)
│   ├── application/
│   │   ├── dto/               calculate_premium_input.py, calculate_premium_output.py
│   │   ├── ports/             clock.py, event_publisher.py, geographic_rate_provider.py,
│   │   │                      simulation_repository.py
│   │   └── use_cases/         calculate_premium.py, get_simulation.py, list_simulations.py
│   ├── infrastructure/
│   │   ├── config/            settings.py, rules_factory.py
│   │   ├── events/            logging_event_publisher.py, outbox_event_publisher.py
│   │   ├── gis/               http_geographic_rate_provider.py, null_geographic_rate_provider.py
│   │   ├── persistence/       models.py, sqlalchemy_repository.py, null_repository.py,
│   │   │                      unit_of_work.py, alembic/ (env.py, versions/)
│   │   ├── observability/     logging.py, request_context.py
│   │   └── time/              system_clock.py
│   ├── presentation/
│   │   └── api/               app.py, dependencies.py, errors.py, schemas.py,
│   │                          routers/ (health.py, premiums.py)
│   └── main.py
├── tests/
│   ├── architecture/          test_import_rules.py, test_alphabetical_order.py
│   ├── domain/
│   ├── application/
│   ├── api/
│   ├── persistence/           (marca @pytest.mark.integration)
│   └── conftest.py
├── docs/adr/                  0001-*.md ...
├── alembic.ini
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── uv.lock
├── .github/workflows/ci.yml
└── README.md
```

## 3. Modelo de domínio

### Value Objects (frozen, validação no `__post_init__`/factory; imutáveis)

| VO | Conteúdo | Invariantes |
|---|---|---|
| `Money` | `amount: Decimal`, `currency: str` | finito; escala/arredondamento aplicados por `RatingRules`; operações só entre mesma moeda; factory `Money.of(amount, currency)` |
| `Percentage` | `value: Decimal` (fracionário: `0.10` = 10%) | finito; `>= 0`; usado para franquia, cobertura, taxas e ajuste GIS (este pode ser negativo — usar `Percentage.signed(...)` ou um `RateAdjustment` dedicado) |
| `VehicleYear` | `value: int` | `>= MIN_VEHICLE_YEAR` (default 1900, configurável); **não pode ser futuro** em relação ao ano do `Clock` — validado no use case, onde o ano corrente está disponível |
| `VehicleSnapshot` | `make, model: str`, `value: Money`, `year: VehicleYear` | strings não vazias, `len <= 120`; `value.amount > 0` |
| `Address` | `country: str` (obrigatório se `Address` presente), `region, city, line1, postal_code: str \| None` | `country` ISO-3166-1 alpha-2; demais opcionais, `len <= 180` |
| `RatingRules` | todos os parâmetros numéricos do cálculo + `rules_version` | carregado da config, validado integralmente; `age_rate_increment >= 0`, `value_band_amount > 0`, `coverage_percentage > 0`, `money_decimal_places >= 0`, `rate_decimal_places >= 0`, `minimum_applied_rate` representável em `rate_decimal_places`, modos de arredondamento válidos |
| `SimulationId` | `value: UUID` | factory `SimulationId.new()` |
| `GeographicRateAdjustment` | `value: Decimal` | `GIS_MIN_ADJUSTMENT <= value <= GIS_MAX_ADJUSTMENT`; **o domínio só conhece este VO** — nada de HTTP, chave de API ou fornecedor |

### Entidade / Aggregate Root

**`PremiumSimulation`** — identificada por `SimulationId`. É criada já completa e consistente por um factory method:

```
PremiumSimulation.calculate(
    *, broker_fee, clock, deductible_percentage,
    geographic_adjustment, registration_location, rules, vehicle,
)
```

Responsabilidades: orquestrar os três domain services na ordem canônica, montar os resultados como `Money`/`Percentage`, e **registrar** o evento `PremiumSimulationCalculated` em sua lista interna `pull_events()`. Não faz I/O.

### Domain Services (funções puras, sem estado)

- **`RateCalculator`** → `applied_rate` (item 4, pipeline completo, incluindo clamp e quantização).
- **`PremiumCalculator`** → `base_premium`, `deductible_discount`, `calculated_premium`.
- **`PolicyLimitCalculator`** → `base_policy_limit`, `deductible_value`, `policy_limit`.

### Domain Event

**`PremiumSimulationCalculated`** — imutável: `simulation_id`, `occurred_at`, `rules_version`, `applied_rate`, `calculated_premium`, `deductible_value`, `policy_limit`, `vehicle_make`, `vehicle_model`, `vehicle_year`. **Nunca** carrega endereço completo nem `broker_fee`/`deductible_percentage` crus além do necessário; se incluir localização, apenas `country`.

## 4. Regra de cálculo canônica — **VINCULANTE**

```
car_age            = calculation_year - vehicle.year          # calculation_year vem do Clock
age_rate           = car_age * AGE_RATE_INCREMENT
value_units        = floor(vehicle.value / VALUE_BAND_AMOUNT)  # inteiro, truncado
value_rate         = value_units * VALUE_RATE_INCREMENT

raw_rate           = age_rate + value_rate + BASE_RATE + geographic_adjustment
clamped_rate       = max(raw_rate, MINIMUM_APPLIED_RATE)
applied_rate       = quantize(clamped_rate, RATE_DECIMAL_PLACES, RATE_ROUNDING_MODE)
                     # se MAXIMUM_APPLIED_RATE definido: aplicar min(...) ANTES da quantização

base_premium       = vehicle.value * applied_rate             # precisão plena
deductible_discount= base_premium * deductible_percentage     # precisão plena
calculated_premium = quantize(base_premium - deductible_discount + broker_fee, MONEY_*)

base_policy_limit  = vehicle.value * COVERAGE_PERCENTAGE       # precisão plena
deductible_value   = quantize(base_policy_limit * deductible_percentage, MONEY_*)
policy_limit       = quantize(base_policy_limit - (base_policy_limit * deductible_percentage), MONEY_*)
```

Regras de precisão (fechadas na errata):
- Entradas → `Decimal` imediatamente.
- **Nada** de quantização antecipada em `base_premium`, `deductible_discount`, `base_policy_limit`.
- Quantiza-se **apenas**: `applied_rate` (escala `RATE_DECIMAL_PLACES`) e os três valores monetários externos `calculated_premium`, `deductible_value`, `policy_limit` (escala `MONEY_DECIMAL_PLACES`).
- `vehicle.value` é ecoado após validação, **sem recálculo**.
- O **mesmo** `applied_rate` quantizado devolvido na resposta é o usado no cálculo do prêmio (resultado reproduzível).
- `geographic_adjustment` é **aditivo** (pontos percentuais), `Decimal("0")` quando GIS desabilitado.

### Tabela de fronteira (deve virar teste parametrizado)

| `vehicle.value` | `value_units` | contribuição de valor |
|---|---|---|
| 9999.99 | 0 | 0% |
| 10000.00 | 1 | 0.5% |
| 19999.99 | 1 | 0.5% |
| 20000.00 | 2 | 1% |
| 100000.00 | 10 | 5% |

### Exemplos de aceite (testes canônicos, `FixedClock` em 2026)

**A — carro 2016, valor 100000, franquia 0.10, cobertura 1.00, corretor 50:**
`car_age=10` → age_rate `0.05`; `value_units=10` → value_rate `0.05`; `applied_rate=0.100000`;
`base_premium=10000`; `deductible_discount=1000`; `calculated_premium=9050.00`;
`base_policy_limit=100000`; `deductible_value=10000.00`; `policy_limit=90000.00`.

**B — carro 2012, demais idênticos:**
`car_age=14` → age_rate `0.07`; `applied_rate=0.120000`;
`base_premium=12000`; `calculated_premium=10850.00`; `deductible_value=10000.00`; `policy_limit=90000.00`.

## 5. Configuração — env vars e `.env.example`

Todas validadas **no startup** (`pydantic-settings`); falha de validação impede a subida do processo.

```dotenv
# --- Regras de cálculo ---
AGE_RATE_INCREMENT=0.005
BASE_RATE=0
COVERAGE_PERCENTAGE=1.00
MINIMUM_APPLIED_RATE=0
MAXIMUM_APPLIED_RATE=            # vazio = sem teto (PRODUCT-DECISION)
MAX_DEDUCTIBLE_PERCENTAGE=1.0    # 1.0 = permite franquia de 100% (PRODUCT-DECISION)
MIN_VEHICLE_YEAR=1900
VALUE_BAND_AMOUNT=10000
VALUE_RATE_INCREMENT=0.005
RULES_VERSION=2026.08.0

# --- Precisão / moeda ---
CURRENCY_CODE=USD
MONEY_DECIMAL_PLACES=2
MONEY_ROUNDING_MODE=ROUND_HALF_UP
RATE_DECIMAL_PLACES=6
RATE_ROUNDING_MODE=ROUND_HALF_UP

# --- Tempo ---
BUSINESS_TIMEZONE=UTC

# --- Persistência (OPCIONAL) ---
PERSISTENCE_ENABLED=false
DATABASE_URL=postgresql+psycopg://insurance:insurance@db:5432/insurance
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
PERSISTENCE_FAILURE_MODE=fail_closed   # fail_closed | fail_open

# --- GIS (OPCIONAL, bônus) ---
GIS_ENABLED=false
GIS_BASE_URL=
GIS_API_KEY=
GIS_TIMEOUT_SECONDS=1.5
GIS_FAILURE_MODE=fail_closed           # fail_closed => 503 | fail_open => ajuste 0
GIS_MIN_ADJUSTMENT=-0.02
GIS_MAX_ADJUSTMENT=0.02

# --- Observabilidade ---
LOG_LEVEL=INFO
LOG_FORMAT=json
```

Alterar qualquer regra ⇒ **apenas reiniciar o container**. Sem recompilar, sem tocar em código.

## 6. Contrato HTTP — **VINCULANTE**

### `POST /api/v1/premiums/calculate` → **200**

Request:
```json
{
  "broker_fee": 50.0,
  "car": { "make": "Toyota", "model": "Corolla", "value": 100000.0, "year": 2012 },
  "deductible_percentage": 0.10,
  "registration_location": { "country": "US", "postal_code": "90001", "region": "CA" }
}
```
`registration_location` é opcional. Campos do request no nível superior: `broker_fee`, `car`, `deductible_percentage`, `registration_location`.

Response — **exatamente estes 5 campos no topo, nada mais**:
```json
{
  "applied_rate": 0.12,
  "calculated_premium": 10850.00,
  "car": { "make": "Toyota", "model": "Corolla", "value": 100000.0, "year": 2012 },
  "deductible_value": 10000.00,
  "policy_limit": 90000.00
}
```
`car` contém **exatamente** `make, model, value, year`. **Não** ecoar `broker_fee`, `deductible_percentage`, `registration_location`, IDs ou metadados. `applied_rate` é JSON number fracionário (`0.12` ⇒ 12%).

### `GET /api/v1/premiums/{simulation_id}` → **200 | 404**
Retorna o registro persistido (schema abaixo). **404 quando `PERSISTENCE_ENABLED=false`** ou id inexistente.

### `GET /api/v1/premiums?limit=&cursor=` → **200**
Lista paginada (cursor opaco). Lista vazia quando persistência desabilitada.

Schema do registro de histórico (contrato **aditivo**, separado do `calculate`):
```json
{
  "applied_rate": 0.12, "calculated_premium": 10850.00,
  "car": {}, "created_at": "2026-08-30T12:00:00Z",
  "deductible_value": 10000.00, "policy_limit": 90000.00,
  "rules_version": "2026.08.0", "simulation_id": "uuid"
}
```

### `GET /health/live` → **200** (processo vivo)
### `GET /health/ready` → **200 | 503**
Checa: settings carregadas; se `PERSISTENCE_ENABLED`, `SELECT 1` no banco.

### Erros
| Código | Quando | Corpo |
|---|---|---|
| **422** | Schema inválido **ou** invariante de entrada de domínio violada (valor ≤ 0, NaN, infinito, ano futuro, percentual fora de faixa, moeda divergente) | `{ "detail": [ { "loc": [], "msg": "...", "type": "..." } ] }` (formato FastAPI; erros de domínio mapeados para essa estrutura) |
| **503** | `GIS_ENABLED=true`, `GIS_FAILURE_MODE=fail_closed`, localização informada e fornecedor indisponível/timeout/resposta fora da faixa | `{ "detail": "geographic risk service unavailable" }` |
| **500** | Erro inesperado | `{ "detail": "internal error", "request_id": "..." }` — **sanitizado**, sem stack, sem segredos |

### OpenAPI
Sempre em `/openapi.json`, com `operationId` estável por rota.

## 7. Persistência opcional (PostgreSQL)

- **Porta** `application/ports/simulation_repository.py`: `SimulationRepository` com `get(self, *, simulation_id)`, `list(self, *, cursor, limit)`, `save(self, *, simulation)`. **Assíncrona ou síncrona** — escolha uma e mantenha coerência (recomendo síncrona + `SQLAlchemy` sync + threadpool do FastAPI, menos armadilhas).
- **Adapters**:
  - `NullSimulationRepository` — usado quando `PERSISTENCE_ENABLED=false`; `save` é no-op, `get`/`list` retornam vazio. Selecionado por injeção de dependência na composição raiz.
  - `SqlAlchemySimulationRepository` — mapeia uma tabela `premium_simulations` (colunas: `id UUID PK`, `created_at timestamptz`, `rules_version text`, `applied_rate numeric`, `calculated_premium numeric`, `deductible_value numeric`, `policy_limit numeric`, `currency_code text`, `vehicle_make/model text`, `vehicle_year int`, `vehicle_value numeric`, `location_country text NULL`). **Sem endereço completo.**
- **Evento + outbox**: quando persistência ligada, use `OutboxEventPublisher` — grava `PremiumSimulationCalculated` em tabela `event_outbox` na **mesma transação** do `save` (Unit of Work em `infrastructure/persistence/unit_of_work.py`). Sem persistência, `LoggingEventPublisher` (structlog).
- **Falha ao persistir**: `PERSISTENCE_FAILURE_MODE=fail_closed` ⇒ **500**; `fail_open` ⇒ 200 + `logger.error`. O cálculo (núcleo) nunca depende do banco — a gravação é efeito colateral pós-cálculo no use case.
- **Migrations**: Alembic, `alembic upgrade head` roda no entrypoint do container `api` **apenas se** `PERSISTENCE_ENABLED=true`.
- **`docker-compose.yml`**: serviço `db: postgres:16` com `healthcheck` (`pg_isready`), volume nomeado; `api` com `depends_on: db (condition: service_healthy)`. Perfil default sobe os dois; documentar `PERSISTENCE_ENABLED=false` para rodar só a `api`.
- **Testes**: `tests/persistence/` com `testcontainers[postgres]` (marca `integration`); e um teste garantindo que, com `PERSISTENCE_ENABLED=false`, `GET /api/v1/premiums/{id}` → 404 e o `POST` continua idêntico ao contrato.

## 8. GIS opcional (bônus)

- **Porta** `GeographicRateProvider.adjustment_for(self, *, address) -> GeographicRateAdjustment`.
- `NullGeographicRateProvider` (default) ⇒ `GeographicRateAdjustment(Decimal("0"))`.
- `HttpGeographicRateProvider` ⇒ chama serviço externo (`httpx`), timeout `GIS_TIMEOUT_SECONDS`, valida resposta na faixa `[GIS_MIN_ADJUSTMENT, GIS_MAX_ADJUSTMENT]`; fora da faixa ⇒ erro. Falha/timeout/fora-de-faixa: `fail_closed` ⇒ propaga como 503; `fail_open` ⇒ ajuste 0 + `logger.warning`.
- **Localização informada com `GIS_ENABLED=false`**: aceita, ajuste **zero**, comportamento documentado no Swagger. **Nunca** adicionar `warnings` ao corpo.
- `applied_rate` final nunca abaixo de `MINIMUM_APPLIED_RATE` (o clamp já cobre isso).
- Logs/eventos: **nunca** endereço completo, **nunca** `GIS_API_KEY`.
- A estrutura de `Address` usada aqui é a mínima do item 3; se o fornecedor real exigir mais, abrir ADR antes.

## 9. Observabilidade

- Middleware `request_context`: gera/propaga `request_id` (header `X-Request-ID` se presente), coloca em `contextvar`, injeta em todos os logs e na resposta 500.
- `structlog` com saída JSON: campos `timestamp`, `level`, `event`, `request_id`, `rules_version`, `route`, `status_code`, `duration_ms`.
- **Nunca logar**: `registration_location` além de `country`, `broker_fee`, `GIS_API_KEY`, `DATABASE_URL` com credenciais.
- Log de negócio por cálculo: `applied_rate`, `calculated_premium`, `vehicle_year`, `country` (se houver), `simulation_id`.

## 10. Swagger / OpenAPI — entregável formal da Fase 4

- `/docs` (Swagger UI) e `/redoc` ativos.
- Tags: `Premiums`, `Health`.
- `title`, `description` (com a lógica de cálculo resumida e a frase **"`deductible_percentage`: use `0.10` para 10%"**), `version` = `RULES_VERSION`.
- Todo campo de request/response com `description`, `examples` e limites.
- Exemplos nomeados de resposta: sucesso (exemplo A do item 4), `422`, `503`, `500`.
- Botão **Try it out** funcional contra a app rodando em Docker.
- Teste automatizado de contrato: valida presença dos paths, `operationId`s, `required` fields, schemas de request/response e os exemplos. **A Fase 4 só é aprovada com esse teste verde.**

## 11. Estratégia de testes e portões de qualidade

- **`pytest`** em `domain`, `application`, `api`, `persistence`, `architecture`.
- **Cobertura**: `--cov=src/car_insurance`, gate **≥ 95% em `domain/`** e **≥ 90% global**. CI falha abaixo disso.
- **Clock injetável** (`FixedClock`) em todo teste que dependa do ano.
- **Fronteira**: parametrizar `9999.99, 10000, 19999.99, 20000` (valor) e `year` tal que `car_age` ∈ `{0, 1, 10, 14}`.
- **Entradas inválidas**: valor negativo/zero, `NaN`, `Infinity`, ano futuro, ano < `MIN_VEHICLE_YEAR`, `deductible_percentage` < 0 ou > `MAX_DEDUCTIBLE_PERCENTAGE`, `broker_fee` negativo, moeda divergente, string vazia.
- **Franquia de 100%** (`deductible_percentage = 1.0`): teste explícito ⇒ `calculated_premium == broker_fee` (quantizado) e `policy_limit == 0`.
- **Property-based (`hypothesis`)**:
  - monotonicidade: `applied_rate` não decresce com `year` menor (carro mais velho) nem com `value` maior;
  - `0 <= deductible_value <= base_policy_limit`;
  - `policy_limit == base_policy_limit - deductible_value` (dentro da tolerância de arredondamento);
  - `calculated_premium` cresce com `applied_rate` mantidos os demais;
  - `applied_rate >= MINIMUM_APPLIED_RATE` sempre.
- **`tests/architecture/test_import_rules.py`**: `import-linter` — camadas e proibição de `fastapi`/`pydantic`/`sqlalchemy`/`httpx` em `domain` e `application`.
- **`tests/architecture/test_alphabetical_order.py`**: AST — para cada `.py` de `src/`, checa ordem alfabética de `FunctionDef`/`AsyncFunctionDef` no módulo, de métodos em cada `ClassDef`, e de parâmetros (posicionais + keyword-only, menos `self`/`cls`) em cada assinatura. Permitir isenção pontual via comentário `# alpha-order: framework`.
- **`ruff check`**, **`ruff format --check`**, **`mypy --strict`** — todos gate de CI.
- **Docker**: build reproduzível, imagem final sem toolchain de build, `USER` não root, `HEALTHCHECK` batendo em `/health/live`; **smoke test** no CI (`docker compose up`, `POST` do exemplo A, asserção do JSON, `docker compose down`).

## 12. Sequência de fases e critérios de aceite (gates)

| Fase | Entrega | Gate (pronto quando) |
|---|---|---|
| **0** | ADRs (item 13); `.env.example`; este contrato revisado | ADRs revisados e aprovados |
| **1** | `pyproject.toml` + `uv.lock`; layout; `Settings` com validação no startup; `Dockerfile`; `docker-compose.yml`; `main.py` mínimo | `docker compose up api` sobe e `/health/live` responde 200 |
| **2** | Value objects, `PremiumSimulation`, os 3 domain services, evento | Testes unitários de domínio verdes; exemplos A e B batem; fronteiras batem; `mypy`/`ruff` limpos |
| **3** | Use cases `CalculatePremium`, `GetSimulation`, `ListSimulations`; todas as portas; publishers/repos `Null` | Testes de aplicação com `FixedClock`, `FakeGeographicRateProvider`, `FakeEventPublisher`, `FakeRepository` verdes |
| **4** | FastAPI: `schemas.py`, routers, mapeamento de erros, OpenAPI + Swagger completos | Testes HTTP verdes; **teste de contrato OpenAPI verde**; `/docs` e `/redoc` renderizam |
| **5** | Config externa completa + observabilidade | Teste provando que override de env (`AGE_RATE_INCREMENT`, `VALUE_BAND_AMOUNT`, `MONEY_DECIMAL_PLACES`...) muda o resultado sem tocar código; logs JSON com `request_id`, sem PII |
| **6** | `README.md`, ADRs finalizados, CI GitHub Actions | CI verde (lint, types, testes, cobertura, arquitetura, build Docker, smoke test) |
| **7** | Persistência PostgreSQL opcional: SQLAlchemy repo, Alembic, outbox, UoW, endpoints de histórico, `db` no compose | Testes `integration` (testcontainers) verdes nos **dois modos**; `PERSISTENCE_ENABLED=false` mantém o contrato do `calculate` intacto e histórico → 404; `ready` checa DB |
| **8** | GIS opcional | Testes de integração do adapter; `fail_closed` ⇒ 503; `fail_open` ⇒ ajuste 0; ajuste sempre em `[-0.02, +0.02]`; sem PII em logs/eventos |

Fases 7 e 8 são independentes e podem ser puladas sem quebrar 0–6.

## 13. ADRs a produzir na Fase 0

1. Clean Architecture + regra de dependência; por que sem repositório/banco no núcleo.
2. `Decimal` em toda parte; política de precisão (só saídas quantizadas; pipeline da taxa).
3. Bandas de valor **discretas com `floor`**; banda e incremento configuráveis; sem `VALUE_BANDING_MODE`.
4. Idade por ano-calendário; `Clock` injetável; fuso configurável; ano futuro rejeitado.
5. Contrato de resposta estreito (`car` = `make/model/value/year`); round-trip completo depende de decisão do PO.
6. DDD mínimo: `PremiumSimulation` como entidade + aggregate root contendo value objects; evento publicado por adapter de logging (sem inventar fila/entrega durável).
7. Mapeamento SOLID: SRP (calculadores separados), OCP (novos adapters sem tocar domínio), LSP (contratos de porta verificados por testes compartilhados de adapter), ISP (portas pequenas), DIP (domínio/aplicação independentes de framework).
8. Status HTTP: 200 (cálculo), 422 (schema + invariantes), 503 (GIS fail-closed), 500 (sanitizado).
9. Persistência opcional por configuração; outbox na mesma transação; `fail_closed` default.
10. GIS: domínio só conhece `GeographicRateAdjustment`; fail-closed default; sem PII.
11. **Somente FastAPI.** Flask e Django citados como conhecidos; a arquitetura hexagonal permitiria adapters equivalentes reusando `application/use_cases` sem tocar em `domain/`.
12. Requisito de ordem alfabética: escopo (funções, métodos, parâmetros), isenções (`self`/`cls`/rota FastAPI), verificação por AST.

## 14. Decisões de produto em aberto — defaults aplicados, marcar `# PRODUCT-DECISION:`

1. **Franquia de 100%**: **permitida** (`MAX_DEDUCTIBLE_PERCENTAGE=1.0`). Resultado: prêmio = taxa do corretor, limite = 0. Teste explícito.
2. **Teto de taxa**: **sem teto** por default (`MAXIMUM_APPLIED_RATE` vazio). Piso = `MINIMUM_APPLIED_RATE=0`.
3. **Moeda**: **USD** (`CURRENCY_CODE=USD`).
4. **Formato de `Address`** para o bônus GIS: VO mínimo do item 3; fechar antes da Fase 8 se o fornecedor exigir mais.

Se o PO decidir diferente, ajustar config/ADR **antes** de implementar o trecho afetado — nenhum desses bloqueia as Fases 0–6.

## 15. Definition of Done

- [ ] `docker compose up` sobe `api` (+ `db` se `PERSISTENCE_ENABLED=true`) e o exemplo A retorna o JSON esperado.
- [ ] `POST /api/v1/premiums/calculate` cumpre o contrato dos 5 campos exatos.
- [ ] Exemplos A e B, tabela de fronteira e testes de invariantes verdes.
- [ ] Cobertura ≥ 95% domínio / ≥ 90% global.
- [ ] `ruff`, `mypy --strict`, `import-linter`, teste AST de ordem alfabética, teste de contrato OpenAPI — todos verdes no CI.
- [ ] Imagem Docker não root, com `HEALTHCHECK`, build reproduzível, smoke test no CI.
- [ ] Overrides de env mudam o resultado sem alterar código.
- [ ] Logs JSON com `request_id`, sem PII/segredos.
- [ ] `README.md` com: arquitetura, como rodar via Docker, matriz de variáveis, como ligar persistência e GIS, exemplos de request/response, e nota sobre Flask/FastAPI/Django.
- [ ] ADRs 1–12 no repositório.
