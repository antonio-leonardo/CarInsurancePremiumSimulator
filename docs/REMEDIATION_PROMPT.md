# PROMPT DE CORREÇÃO — Achados da auditoria adversarial

> Rodada de correção pós-build. Complementa `docs/EXECUTION_PROMPT.md`.
> Origem dos achados: auditoria cega (11 achados) + itens menores, todos
> reproduzidos ao vivo contra o worktree atual.

## 0. Contexto e regras da rodada de correção

O build está completo e com todos os gates verdes (287 testes, 100% cobertura), **mas ainda não commitado**. Uma auditoria cega encontrou 11 defeitos reais, confirmados por reprodução. Esta rodada corrige cada um.

**Regras invioláveis desta rodada:**

1. **Nada de escopo novo.** Sem novos endpoints, sem dispatcher de outbox, sem nova infraestrutura. Só correção.
2. **O contrato HTTP não muda.** Resposta do `calculate` continua com exatamente 5 campos; `car` com exatamente `make/model/value/year`.
3. **Fronteiras DDD mantidas.** Domínio e aplicação continuam sem `fastapi/pydantic/sqlalchemy/httpx` — e agora **sem `structlog`** (achado A11).
4. **Ordem alfabética** continua valendo; parâmetros novos são keyword-only.
5. **Cada correção precisa de um teste de regressão que falhe sem o fix.** Onde fizer sentido, no estilo mutation-killer (comentar o fix ⇒ teste vermelho).
6. **Todos os gates atuais permanecem verdes** ao final: `ruff check`, `ruff format --check`, `mypy --strict`, `import-linter` (com a lista estendida em A11), pytest ≥ 287 e cobertura ≥ 99% global / ≥ 95% domínio, `docker build`, e os dois smokes do compose.
7. Variável de config nova ⇒ documentar em `.env.example` **e** na matriz do `README.md` **e**, se for decisão de política, uma ADR.
8. Ao final, produzir `docs/REMEDIATION.md` mapeando cada achado → arquivos alterados → testes que o cobrem.
9. Adicionar `tests/api/test_adversarial_audit.py` reproduzindo **exatamente** os cenários abaixo como guarda permanente (o script de reprodução usado na auditoria serve de base).

---

## A1 — `Decimal → float` corrompe o eco; `car.value` sem teto → HTTP 500

**Defeito confirmado:** `car.value = 9007199254740993` é ecoado como `9007199254740992.0`; `car.value = 1e100` retorna **HTTP 500** (`InvalidOperation`) em vez de 422.

**Correção:**
- Adicionar tetos configuráveis de entrada: `MAX_VEHICLE_VALUE` (default `1e11`) e `MAX_BROKER_FEE` (default `1e9`). Aplicar como `le=` nos schemas Pydantic ⇒ acima do teto retorna **422**, nunca 500.
- `NumberOut` deve emitir **número JSON sem perda dentro da faixa permitida**: emitir `int` quando o `Decimal` for integral, senão `float` (lossless para magnitude `< 2^53` e escala ≤ `MONEY_DECIMAL_PLACES`, o que a faixa `≤ 1e11` garante). Não usar `float()` cru sobre valores fora dessa faixa.
- Envolver os 3 calculadores em `high_precision()` (`domain/calculation_context.py`) — se já feito na pass 2/3, apenas confirmar com teste.

**Aceite:**
- `value = 1e100` → 422 com corpo `ValidationErrorResponse`.
- `value = 99999999999.99`, `broker_fee = 12345.67` → ecoados **exatamente** (`Decimal(str(resp)) == entrada`).
- Property test sobre `value ∈ [1, 1e11]` com 2 casas: `Decimal(str(response.car.value)) == input`.
- `test_default_context_would_have_failed` prova que sem `high_precision()` daria `InvalidOperation`.

---

## A2 — Configuração de regra inválida não impede o startup

**Defeito confirmado:** com `VALUE_BAND_AMOUNT=0` a aplicação sobe, `/health/ready` retorna **200**, e só o 1º cálculo retorna 422.

**Correção:**
- `create_app()` deve materializar `RatingRules` (via `get_rating_rules()`) **no startup**, e a engine quando `PERSISTENCE_ENABLED=true`. Config inválida ⇒ exceção antes de aceitar tráfego ⇒ container sai com código ≠ 0.

**Aceite:**
- `VALUE_BAND_AMOUNT=0` (e qualquer regra inválida) ⇒ `create_app()` levanta; teste `with pytest.raises(...)`.
- Nenhuma instância com regra inválida chega a responder 200 em `/health/ready`.

---

## A3 — `MAX_DEDUCTIBLE_PERCENTAGE > 1` aceita franquia economicamente inválida

**Defeito confirmado:** `MAX_DEDUCTIBLE_PERCENTAGE=1.5` + `deductible_percentage=1.5` → **200** com `calculated_premium: -4950.0`, `policy_limit: -50000.0`.

**Correção:**
- `RatingRules.__post_init__`: exigir `0 <= max_deductible_percentage <= 1`.
- Schema: `deductible_percentage` ganha `le=1`.
- `Percentage` continua permitindo o valor cru; o teto é da regra/schema.
- Manter `deductible_percentage = 1.0` **válido** (decisão de produto: 100% permitido).

**Aceite:**
- `MAX_DEDUCTIBLE_PERCENTAGE=1.5` ⇒ boot falha (via A2).
- `deductible_percentage = 1.5` ⇒ 422; `= 1.0` ⇒ 200 com `calculated_premium == broker_fee` e `policy_limit == 0`.

---

## A4 — (o pior) Localização sensível vaza nos logs do GIS

**Defeito confirmado:** o `httpx` loga a URL completa em nível INFO (via `basicConfig` no root logger), incluindo `?city=SecretCity&postal_code=12345&region=SecretRegion`; e `_fallback` no modo `fail_open` loga `{exc!s}`, que contém a URL.

**Correção:**
- `configure_logging`: fixar os loggers `httpx` e `httpcore` em `WARNING` (ou acima).
- Adaptador GIS: **nunca** logar mensagem de exceção, URL, params ou qualquer campo de `Address`. Logar só `type(exc).__name__` + razão estática (`"gis.error"` / `"gis.fallback"`).
- Defense in depth: enviar os campos de localização no **corpo (JSON body de um POST)**, não na query string, para que nem um log de WARNING/ERROR do `httpx` possa carregá-los numa URL.
- Varredura: nenhum `address`, `city`, `postal_code`, `region`, `line1` em **nenhuma** chamada de log do projeto.

**Aceite:**
- Teste com GIS mockado retornando 500, nos dois `GIS_FAILURE_MODE`: capturar **toda** a saída de log (structlog + root stdlib) e afirmar que `SecretCity`, `12345`, `SecretRegion` **não aparecem**.
- Teste afirmando que, após `configure_logging`, `logging.getLogger("httpx").level >= WARNING`.

---

## A5 — Schema PostgreSQL contradiz a precisão configurável

**Defeito confirmado:** colunas fixas `Numeric(20,4)` (dinheiro) e `Numeric(12,8)` (taxa), mas `MONEY_DECIMAL_PLACES` / `RATE_DECIMAL_PLACES` aceitam qualquer `>= 0`.

**Correção:**
- Colunas monetárias e de taxa ⇒ `Numeric()` sem precisão/escala fixas (precisão variável).
- Ajustar a migration `0001_initial.py` de acordo.
- Manter `test_migration_matches_orm_models` (`compare_metadata` vazio) verde.

**Aceite:**
- Teste de integração: com `MONEY_DECIMAL_PLACES=6` e persistência ligada, um prêmio com 6 casas persiste e volta **idêntico** pelo histórico.

---

## A6 — Smoke de CI depende do ano de 2026

**Defeito confirmado:** o smoke usa `SystemClock` (relógio real) mas fixa carros 2016/2012 e afirma `9050`/`10850` — resultados válidos só em 2026.

**Correção:**
- O smoke calcula o `year` a partir do ano corrente para manter `car_age` constante:
  `YEAR=$(date -u +%Y); AGE10=$((YEAR-10)); AGE14=$((YEAR-14))` e posta esses anos.
- Assim `9050`/`10850` continuam corretos todo ano; as asserções ficam invariantes.

**Aceite:** revisar mentalmente para 2027 e 2030 — asserções continuam válidas sem mudança de código.

---

## A7 — Modo stateless ainda constrói a engine; DSN inválida → 500

**Defeito confirmado:** com `PERSISTENCE_ENABLED=false` e `DATABASE_URL=not-a-dsn`, `/health/ready` e `/calculate` retornam **500** (`ArgumentError`), porque `get_repository`/`get_event_publisher` dependem incondicionalmente de `get_unit_of_work` → `_engine()`.

**Correção:**
- `get_engine()` retorna `Engine | None` (None quando persistência desligada).
- `get_repository` / `get_event_publisher` retornam `NullSimulationRepository` / `LoggingEventPublisher` **sem depender** de `get_unit_of_work` quando desligado.
- `Settings._check_consistency`: validar o DSN com `sqlalchemy.engine.make_url` sempre que `PERSISTENCE_ENABLED=true` (já parcialmente feito — confirmar) e, se possível, sempre.
- `/health/ready` trata `engine is None` (persistência off ⇒ apenas `"ready"`).

**Aceite:**
- persistência off + `DATABASE_URL=not-a-dsn` ⇒ `/health/ready` 200, `/calculate` 200.
- persistência on + DSN inválido ⇒ boot falha.

---

## A8 — Resposta GIS malformada (`200 []`) → `TypeError` → 500

**Defeito confirmado:** `response.json()["adjustment"]` sobre `[]` levanta `TypeError`, não capturado por `except (httpx.HTTPError, KeyError, ValueError)` ⇒ 500 nos dois modos de falha.

**Correção:**
- Ampliar o `except` do adaptador para incluir `LookupError, TypeError` (e validar o formato antes de indexar).
- Rotear pelo modo de falha: `fail_closed` ⇒ 503; `fail_open` ⇒ ajuste 0 + WARNING.

**Aceite:**
- Testes com GIS mockado retornando `200 []`, `200 {}`, `200 {"adjustment":"abc"}`, `200 "x"`, `200 {"adjustment": null}`:
  - `fail_closed` ⇒ 503;
  - `fail_open` ⇒ `applied_rate` sem ajuste + log WARNING sem PII.

---

## A9 — Teto de taxa pode ser ultrapassado

**Defeito confirmado:** `MAXIMUM_APPLIED_RATE=0.1234565` (7 casas, `RATE_DECIMAL_PLACES=6`) ⇒ `applied_rate=0.123457` (> teto), porque o teto é aplicado **antes** da quantização e sua representabilidade não é validada.

**Correção:**
- `RatingRules.__post_init__`: validar que `maximum_applied_rate`, quando definido, é representável em `rate_decimal_places` (mesma checagem já feita para `minimum_applied_rate`).

**Aceite:**
- `MAXIMUM_APPLIED_RATE=0.1234565` ⇒ boot falha com mensagem clara.
- `=0.123456` ⇒ ok, e `applied_rate` nunca excede o teto.

---

## A10 — Swagger não cumpre o gate acordado (prompt §10)

**Defeitos confirmados:** 500 não documentado no `/calculate`; sem exemplos nomeados de 200/422/503/500; campos de resposta e de `Address` sem `description`/`examples`; comportamento "GIS off = ajuste 0" ausente; `/health/ready` não documenta 503; o corpo real do 422 traz `input` e `ctx` além de `loc/msg/type`.

**Correção:**
- Documentar `500` (`InternalErrorResponse`) no `/calculate` e `503` (`MessageResponse`) em `/health/ready`.
- Exemplos nomeados via `responses=`/`openapi_examples`: sucesso (Exemplo A), 422, 503, 500.
- Todo campo de request/response e de `Address` com `description` + `examples`.
- Nota na descrição do endpoint: "localização aceita com `GIS_ENABLED=false` ⇒ ajuste geográfico zero".
- **Normalizar o corpo do 422**: handler de `RequestValidationError` que remodela para exatamente `{"detail": [{"loc","msg","type"}]}` — coerente com a errata ("contrato exato") e com `ValidationErrorResponse`.

**Aceite:**
- `test_openapi_contract` reforçado: 200/422/500 documentados no calculate, 503 no `/health/ready`, presença dos exemplos nomeados.
- Um 422 real (schema **e** domínio) tem corpo com itens contendo **somente** `loc/msg/type`.

---

## A11 — `structlog` importado na camada de aplicação

**Defeito confirmado:** `application/use_cases/calculate_premium.py` faz `import structlog`; os guards (`import-linter` e `test_guards_are_effective`) não proíbem.

**Correção:**
- Criar port `application/ports/logger.py` — `Logger` Protocol mínimo: `bind(**fields) -> Logger`, `info(event, **fields)`, `warning(...)`, `error(...)` (parâmetros keyword-only, ordem alfabética).
- `CalculatePremium` recebe um `Logger` por injeção; remover `import structlog` de `application/`.
- Adaptador `infrastructure/observability/structlog_logger.py`.
- Estender a lista `forbidden_modules` do `import-linter` **e** `_FORBIDDEN_IN_CORE` em `test_guards_are_effective.py` com `structlog`.

**Aceite:**
- `grep -rn "structlog" src/car_insurance/application src/car_insurance/domain` ⇒ vazio.
- `import-linter` e o guard AST **falham** se `structlog` reaparecer no core (provar com o meta-teste).

---

## Itens menores (agrupar num commit)

- **Marcadores `# PRODUCT-DECISION:`** (exigidos pelo prompt §14): adicionar no código exatamente onde as decisões vivem — default de `max_deductible_percentage`, `maximum_applied_rate = None`, `currency_code = "USD"`, forma do `Address` — cada um referenciando a ADR correspondente.
- **Ano futuro no agregado**: `PremiumSimulation.calculate` rejeita `vehicle.year > now.year` por si (defense in depth; hoje só o use case faz). Teste no nível do agregado.
- **Faixa intrínseca do `GeographicRateAdjustment`**: manter `within()` como o construtor que os adaptadores devem usar; o agregado passa a assertar que o ajuste recebido está em `[gis_min, gis_max]` (expor esses limites em `RatingRules`). Teste com adaptador fake devolvendo `0.5`.
- **Atomicidade do outbox**: teste de integração simulando falha no `commit`/insert do outbox ⇒ a linha-pai também sofre rollback e `SimulationRepositoryError` é levantada.
- **Digests de imagem**: fixar imagens base e actions por digest (`python:3.12-slim@sha256:…`, `postgres:16@sha256:…`, `actions/*@<sha>`), ou registrar em ADR a decisão consciente de manter tags.

---

## Entregáveis finais desta rodada

- [ ] 11 achados + menores corrigidos, cada um com teste de regressão que falha sem o fix.
- [ ] `tests/api/test_adversarial_audit.py` com os cenários A1–A9 reproduzidos como guarda permanente.
- [ ] `import-linter` estendido (`structlog`); guard AST idem.
- [ ] Todos os gates verdes; cobertura ≥ 99% global / ≥ 95% domínio.
- [ ] `.env.example` + matriz do README atualizados (`MAX_VEHICLE_VALUE`, `MAX_BROKER_FEE`, e o que mais surgir).
- [ ] ADRs novas/atualizadas: 0003 (franquia ≤ 1), 0008 (500/503 documentados + normalização do 422), 0010 (GIS sem PII), + uma para o `Logger` port, uma para os tetos de entrada, uma para materialização no startup.
- [ ] `docs/REMEDIATION.md`: tabela achado → arquivos → testes.
- [ ] Só então: primeiro commit (worktree ainda 100% untracked em `main`).
