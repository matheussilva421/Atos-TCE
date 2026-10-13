# Portal Atual + Preenchimento Manual Best-Effort Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir preenchimento manual best-effort de processos independentemente do status local e fazer a Mesa acompanhar automaticamente o formulário aberto na Área Restrita, com uma aba “Portal atual” que mostra campos, pendências, evidências e dispara o fill manual sem automatizar a conclusão do ato.

**Architecture:** Separar completude de dados de segurança de identidade. Um novo `PortalSelectionTracker` mantém somente em memória a observação recente do formulário, resolve a identidade pelo `Store`, expõe um estado público mínimo à Mesa e conserva o snapshot sanitizado apenas durante o TTL para o botão “Preencher dados encontrados”. O heartbeat existente da extensão alimenta esse tracker; a Mesa faz polling do estado e controla acompanhamento/pausa localmente. O fill continua usando `FillService.request_manual_fill()` e o mesmo `FILL_FORM` existente.

**Tech Stack:** Python 3 / `unittest`, SQLite Store existente, HTTP loopback `BaseHTTPRequestHandler`, Chrome/Edge MV3 JavaScript, Node `--test`, HTML/CSS/JS da Mesa, PowerShell packaging/verifier.

**Spec:** `docs/superpowers/specs/2026-10-01-portal-atual-best-effort-design.md`

## Global Constraints

- O clique final **Complementar Ato** permanece exclusivamente humano; não adicionar `SUBMIT`, `SEND`, `AUTO_SUBMIT`, `COMPLEMENT_ACT` ou `FINALIZE`.
- O relaxamento de status vale somente para `request_manual_fill()`; `request_fill(process_id)` continua limitado ao fluxo automático já autorizado.
- Identidade/formulário inseguro continua fail-closed: zero/múltiplos alvos, mismatch, geração inválida/stale ou identidade ambígua bloqueiam escrita.
- Nunca selecionar processo por similaridade, ordem visual ou “mais provável”; reutilizar `Store.resolve_process_identity()`.
- Valor não vazio divergente no portal deve ser preservado; os campos independentes continuam em best-effort.
- “Portal atual” é estado transitório em memória, TTL de **10 segundos**, e não altera `process.status`.
- O snapshot do formulário usado pela seleção atual pode existir somente em memória durante o TTL; não persistir em SQLite, logs, reliability telemetry ou resposta pública do GET.
- Heartbeat do portal continua em **1500 ms**; observação idêntica deve ser deduplicada e renovada no máximo a cada **5000 ms** para não expirar.
- Acompanhamento é **Portal → Mesa**; selecionar um processo na Mesa não navega o portal.
- O sidepanel não é requisito para o acompanhamento automático.
- Reutilizar o viewer/evidence APIs atuais; não criar outro renderer de PDF.
- Implementação invalida o AR1_BUILD antigo `e059793a412f3fe4c8b403fb3a58cfa02e26553c` para nova qualification.
- Todos os testes/smokes devem usar raízes descartáveis; não registrar runs no ledger real durante desenvolvimento.
- Após implementação, gerar novo ZIP limpo sem acervo e provar provenance contra o novo AR1_BUILD.

## Review Focus

1. **Race entre polling da Mesa e TTL:** seleção MATCHED expira entre renderização e clique em “Preencher dados encontrados”; o servidor deve recusar sem escrever e registrar a tentativa AR-1 como falha observável.
2. **Mudança de formulário durante um fill:** A é observado, o operador navega para B antes do write/readback; as guardas existentes de identity/generation devem bloquear A, nunca escrever em B.
3. **Heartbeat duplicado ou concorrente:** ticks repetidos não podem criar spam, regressão de estado ou publicar uma observação velha depois de uma mais nova.
4. **Usuário navegando manualmente na Mesa:** um refresh do mesmo processo observado não pode reabrir “Portal atual” nem roubar a subaba escolhida; somente mudança de process_id ou “Retomar acompanhamento” pode fazê-lo.
5. **Processo sem campos úteis ou com estado excepcional:** a UI deve mostrar a ficha e pendências sem inventar dados; status genérico `ERRO`/`REVISAR` não bloqueia manual fill, mas uma causa real de identidade insegura continua bloqueando.

---

## File Structure

**Create**
- `app/area_restrita/current_selection.py` — tracker transitório, TTL, resolução exata e acesso privado ao snapshot atual.
- `tests/test_current_selection.py` — testes unitários do tracker.
- `app/web/portal-current.js` — helpers puros de classificação de completude e decisão de follow.
- `app/web/tests/portal-current.test.mjs` — testes unitários dos helpers de UI.

**Modify**
- `app/area_restrita/fill_service.py` — separar elegibilidade automática da manual.
- `tests/test_fill_service.py` — status não-PRONTO, partial/zero-field e guards.
- `app/api/server.py` — propriedade do tracker e três rotas `current-selection`.
- `tests/test_api_server.py` — autenticação, payload público, fill da seleção atual e race/TTL.
- `extension/lib/api.js` — publicar/limpar observação corrente.
- `extension/background/router.js` — observar formulário no heartbeat, dedupe e keepalive.
- `extension/tests/api.test.mjs` — contrato HTTP novo.
- `extension/tests/router.test.mjs` — observação com sidepanel fechado, dedupe, A→B, ambiguidade.
- `app/web/index.html` — aba “Portal atual”, controles follow e workspace do viewer.
- `app/web/app.js` — polling da seleção, pause/resume, render da aba e botão de manual fill atual.
- `app/web/app.css` — layout PDF à esquerda / ficha à direita e cards.
- `app/web/tests/ui-wiring.test.mjs` — wiring do follow, tab e ausência de submit.
- `docs/notes/2026-09-30-area-restrita-reliability-reset-phase-1-handoff.md` — somente no fechamento, depois do novo build/ZIP.

---

### Task 1: Desacoplar status local do manual fill

**Files:**
- Modify: `app/area_restrita/fill_service.py`
- Test: `tests/test_fill_service.py`

**Interfaces:**
- Consumes: `Store.resolve_process_identity(process_key, interested_normalized, portal_act_id=None)`, `build_fill_plan(process, form_snapshot)`.
- Produces: `FillService.request_manual_fill(form_snapshot: Mapping[str, Any] | None) -> int` aceitando qualquer status local quando a identidade é exata; `FillService.request_fill(process_id: int) -> int` mantém a guarda automática; helper interno `_best_effort_satisfied(planned_fields: Mapping[str, Any] | None, field_results: Mapping[str, Any] | None) -> bool` separa sucesso da escrita de completude documental.

- [ ] **Step 1: Escrever RED para status não-PRONTO no manual fill**

Adicionar casos em `ManualFillRequestTests` que criem processo com `PENDENTE`, `IDENTIFICADO`, `BAIXADO`, `REVISAR`, `ERRO` e `PREENCHIDO`, com identidade e pelo menos um campo `found`, chamem `request_manual_fill(snapshot)` e afirmem que a request chega a `FILLING` sem alterar o status do processo.

- [ ] **Step 2: Escrever RED preservando a guarda do fluxo automático**

Atualizar/expandir `test_a_process_that_is_not_pronto_is_refused` para provar que `request_fill()` ainda recusa `PENDENTE`, `REVISAR`, `BAIXADO`, `ERRO` e `CONCLUÍDO`.

- [ ] **Step 3: Escrever RED para resultado parcial em processo REVISAR**

Criar teste em `FillServiceOutcomeTests`: processo começa `REVISAR`, dois campos são `found`, um write é parcial, a `fill_request` termina `PREENCHIDO`, mas `process.status` continua `REVISAR` e o evento `form_filled_partial` existe.

- [ ] **Step 4: Escrever RED para a nova semântica AR-1 best-effort**

Em `Ar1ManualFillReliabilityTests`, cobrir:
- plano com `cargo` elegível escrito/relido corretamente + outros mandatory sem proposta → `mandatory_satisfied == false`, `best_effort_satisfied == true`, `run_finished.passed == true`;
- campo presente em `plan.fields` com status `disabled`, resultado ausente ou `after != proposed` → `best_effort_satisfied == false`, `passed == false`;
- plano vazio → `best_effort_satisfied == true`, `mandatory_satisfied == false`, sem valor inventado;
- mismatch/generation/form ambiguity continuam `passed == false`.

Também substituir o teste antigo `test_a_process_that_is_not_pronto_never_matches`, que contradiz a nova regra.

- [ ] **Step 5: Rodar os RED**

Run:
~~~powershell
python -m unittest tests.test_fill_service.ManualFillRequestTests tests.test_fill_service.FillServiceOutcomeTests -v
~~~

Expected: os novos testes de status manual falham pela guarda `PRONTO/PREENCHIDO`; os testes de identidade existentes continuam passando.

- [ ] **Step 6: Implementar a separação mínima e o critério best-effort**

Em `app/area_restrita/fill_service.py`:
- renomear `FILLABLE_PROCESS_STATUSES` para `AUTOMATIC_FILLABLE_PROCESS_STATUSES`;
- usar essa constante somente em `request_fill()`;
- remover o gate de status de `request_manual_fill()`;
- atualizar docstrings/mensagens para “processo correspondente ao formulário” sem mencionar `PRONTO`;
- adicionar `_best_effort_satisfied(planned_fields, field_results)`: para cada chave de `plan.fields`, exigir resultado mapping com `status` `changed` ou `preserved`, `proposed` não-nulo e `after == proposed`; plano vazio retorna `true`; campos fora de `plan.fields` não reduzem esse resultado;
- em `_handle_fill_result()`, manter `mandatory_satisfied` como único critério de promoção de `process.status`, persistir `summary["best_effort_satisfied"]` e usar essa nova métrica para `reread_completed`/`run_finished.passed`;
- usar códigos `BEST_EFFORT_OK` e `BEST_EFFORT_FAILED` no boundary/final do AR-1;
- preservar todos os guards de identidade/generation.

- [ ] **Step 7: GREEN focal**

Run:
~~~powershell
python -m unittest tests.test_fill_service -v
~~~

Expected: PASS.

- [ ] **Step 8: Commit**

~~~bash
git add app/area_restrita/fill_service.py tests/test_fill_service.py
git commit -m "feat: allow best-effort manual fill across process states"
~~~

---

### Task 2: Criar o tracker transitório de “Portal atual”

**Files:**
- Create: `app/area_restrita/current_selection.py`
- Create: `tests/test_current_selection.py`

**Interfaces:**
- Consumes: `Store.resolve_process_identity(...)`, `StoreError`.
- Produces:
  - `PORTAL_SELECTION_TTL_SECONDS = 10.0`
  - `class PortalSelectionError(RuntimeError)` com `code: str`
  - `PortalSelectionTracker(store: Store, *, ttl_seconds: float = 10.0, clock: Callable[[], float] = time.monotonic, utcnow: Callable[[], datetime] = _utcnow)`; definir `_utcnow() -> datetime` como `datetime.now(timezone.utc)`
  - `observe(form_snapshot: Mapping[str, Any]) -> dict[str, Any]`
  - `clear(code: str = "FORM_NOT_AVAILABLE") -> dict[str, Any]`
  - `public_state() -> dict[str, Any]`
  - `require_fill_snapshot() -> dict[str, Any]`

- [ ] **Step 1: RED para MATCHED/NOT_FOUND/AMBIGUOUS**

Em `tests/test_current_selection.py`, provar:
- identidade exata → `state == "MATCHED"`, `process_id` correto;
- processo inexistente → `NOT_FOUND` e sem `process_id`;
- `StoreError` de alias conflitante/múltiplo → `AMBIGUOUS` e sem escolha arbitrária.

- [ ] **Step 2: RED para validação estrutural e privacidade**

Provar que identity ausente, `generation` bool/zero/ausente e snapshot não-mapping geram `PortalSelectionError("INVALID")`; `public_state()` não inclui `form`, `fields`, `interestedNormalized`, cookies/tokens ou snapshot privado.

- [ ] **Step 3: RED para TTL e snapshot privado**

Com clock injetado:
- antes de 10 s, `require_fill_snapshot()` devolve uma cópia do snapshot MATCHED;
- aos 10 s ou depois, `public_state()` vira `NO_ACTIVE_FORM`, `require_fill_snapshot()` lança `PortalSelectionError("FORM_NOT_AVAILABLE")` e o snapshot é descartado.

- [ ] **Step 4: RED para clear/ambiguidade**

`clear("FORM_NOT_AVAILABLE")` → `NO_ACTIVE_FORM`; `clear("FORM_AMBIGUOUS")` → `AMBIGUOUS`; nenhum deles preserva snapshot fillable.

- [ ] **Step 5: RED para não mutar processo**

Capturar `process.status` antes/depois de `observe()` e afirmar igualdade.

- [ ] **Step 6: Rodar RED**

Run:
~~~powershell
python -m unittest tests.test_current_selection -v
~~~

Expected: FAIL porque o módulo/interface ainda não existe.

- [ ] **Step 7: Implementar `PortalSelectionTracker`**

Manter somente memória do processo do servidor. Usar `copy.deepcopy` para isolar o snapshot; armazenar monotonic expiry separadamente do timestamp ISO público; nunca escrever no `Store`.

- [ ] **Step 8: GREEN**

Run:
~~~powershell
python -m unittest tests.test_current_selection -v
~~~

Expected: PASS.

- [ ] **Step 9: Commit**

~~~bash
git add app/area_restrita/current_selection.py tests/test_current_selection.py
git commit -m "feat: track the current portal form in memory"
~~~

---

### Task 3: Expor current-selection e fill atual na API da Mesa

**Files:**
- Modify: `app/api/server.py`
- Modify: `tests/test_api_server.py`

**Interfaces:**
- Consumes: `PortalSelectionTracker.observe()`, `.clear()`, `.public_state()`, `.require_fill_snapshot()`; `FillService.request_manual_fill()`.
- Produces:
  - `MesaServer.portal_selection -> PortalSelectionTracker`
  - GET `/api/v1/portal/current-selection` (Mesa session)
  - POST `/api/v1/portal/current-selection` (extension auth)
  - POST `/api/v1/portal/current-selection/fill` (Mesa session)

**POST observation contract:**
- form ativo: `{"active": true, "form": <readCurrentForm snapshot>}`
- sem formulário/ambíguo: `{"active": false, "code": "FORM_NOT_AVAILABLE"|"FORM_AMBIGUOUS"|"PORTAL_TAB_NOT_ACTIVE"}`

- [ ] **Step 1: RED de autenticação das três rotas**

Adicionar testes que provem:
- extension token é obrigatório no POST observation;
- Mesa session é obrigatória no GET e no POST fill;
- credencial errada recebe 401/403 seguindo os padrões existentes.

- [ ] **Step 2: RED para payload MATCHED mínimo**

POST de form exato → 200/202 com estado; GET → `MATCHED`, `process_id`, `process_key`, `generation`, `screen`, `observed_at`; afirmar explicitamente que o GET não contém `form`, `fields` ou `interestedNormalized`.

- [ ] **Step 3: RED para NOT_FOUND/AMBIGUOUS/NO_ACTIVE_FORM**

Cobrir processo inexistente, conflito que gera `StoreError`, `active:false FORM_AMBIGUOUS` e `active:false FORM_NOT_AVAILABLE`; nenhum estado não-MATCHED pode retornar `process_id`.

- [ ] **Step 4: RED do botão “Preencher dados encontrados”**

Com seleção MATCHED recente:
- POST `/api/v1/portal/current-selection/fill`;
- retorna 201 com `fill_request_id`, `state`, `mode:"manual"`;
- request criada é manual e não enfileira `OPEN_ACT`/`OPEN_NEXT_ACT`;
- o `FILL_FORM` usa o snapshot transitório observado.

- [ ] **Step 5: RED da race TTL (Review Focus #1)**

Expirar a seleção entre GET e POST fill. O POST deve:
- retornar 409 `current_selection_not_fillable`;
- não criar `fill_request`;
- não enfileirar comando de write;
- registrar a tentativa AR-1 como falha equivalente a `FORM_NOT_AVAILABLE`, sem duplicar terminal.

- [ ] **Step 6: Rodar RED**

Run:
~~~powershell
python -m unittest tests.test_api_server -v
~~~

Expected: novos endpoints ausentes/falhando.

- [ ] **Step 7: Implementar propriedade e rotas**

Em `MesaServer`, criar lazy property `portal_selection`. Registrar:
- `Route(...current-selection, "handle_portal_current_selection", "mesa")`;
- `Route(...current-selection, "post_portal_current_selection", "extension")`;
- `Route(...current-selection/fill, "post_portal_current_selection_fill", "mesa")`.

No fill atual, obter `require_fill_snapshot()` e chamar `self.mesa.fill.request_manual_fill(snapshot)`. Em stale/no-active race, chamar `record_manual_attempt_failure("FORM_NOT_AVAILABLE")` antes da resposta 409; não contar NOT_FOUND/AMBIGUOUS como tentativa porque a UI não oferecerá o botão nesses estados.

- [ ] **Step 8: GREEN focal**

Run:
~~~powershell
python -m unittest tests.test_current_selection tests.test_api_server tests.test_fill_service -v
~~~

Expected: PASS.

- [ ] **Step 9: Commit**

~~~bash
git add app/api/server.py tests/test_api_server.py
git commit -m "feat: expose current portal selection to the mesa"
~~~

---

### Task 4: Publicar a observação pelo heartbeat da extensão

**Files:**
- Modify: `extension/lib/api.js`
- Modify: `extension/background/router.js`
- Test: `extension/tests/api.test.mjs`
- Test: `extension/tests/router.test.mjs`

**Interfaces:**
- Consumes: `readCurrentForm() -> {ok, form?, code?, error?}`.
- Produces:
  - `api.publishCurrentSelection(observation) -> {ok,status,payload,error}`
  - `observeCurrentForm() -> Promise<{published:boolean, signature:string|null, ...}>` dentro do router
  - `PORTAL_SELECTION_KEEPALIVE_MS = 5000`
  - `installRouter({ ..., now = Date.now })` para clock testável.

- [ ] **Step 1: RED do cliente HTTP**

Em `api.test.mjs`, chamar `publishCurrentSelection({active:true, form})` e afirmar POST exato em `/api/v1/portal/current-selection`, bearer/client headers existentes e body inalterado.

- [ ] **Step 2: RED: heartbeat funciona com sidepanel fechado**

Em `router.test.mjs`, instanciar router sem qualquer mensagem de sidepanel, com `nextCommand() -> null` e form válido nos frames. Uma chamada a `router.poll()` deve chamar `publishCurrentSelection({active:true, form})`.

- [ ] **Step 3: RED: dedupe + keepalive (Review Focus #3)**

Com `now()` injetado:
- t=0 form A → publica;
- t=1500 mesmo A → não publica;
- t=5000 mesmo A → publica keepalive;
- assinatura deve usar `processKey + interestedNormalized + portalActId + generation + screen`.

- [ ] **Step 4: RED: A → B publica imediatamente**

Antes dos 5000 ms, trocar resposta de A para B; B deve ser publicado imediatamente e nunca ser substituído por um resultado A atrasado do mesmo ciclo.

- [ ] **Step 5: RED: no-form e ambiguous limpam**

`FORM_NOT_AVAILABLE`/`PORTAL_TAB_NOT_ACTIVE` → `{active:false, code}`; `FORM_AMBIGUOUS` → clear ambíguo. Repetição idêntica deve ser deduplicada.

- [ ] **Step 6: RED: command polling continua prioritário**

Com comando real pendente, provar que `poll()` continua reportando resultado/lease como antes; adicionar observação não pode quebrar claim/result nem transformar `POLL_COMMANDS` em comando de submit.

- [ ] **Step 7: Rodar RED**

Run:
~~~powershell
node --test extension/tests/api.test.mjs extension/tests/router.test.mjs
~~~

Expected: FAIL nos novos contratos.

- [ ] **Step 8: Implementar API + observer**

Adicionar `publishCurrentSelection()` ao `createApi`. No router, manter assinatura/timestamp em memória do worker e chamar `observeCurrentForm()` dentro do heartbeat `poll()`, usando o leitor existente; não adicionar novo MESSAGE_TYPE nem COMMAND_TYPE.

- [ ] **Step 9: GREEN e contrato proibido**

Run:
~~~powershell
node --test extension/tests/api.test.mjs extension/tests/router.test.mjs extension/tests/protocol.test.mjs extension/tests/portal-contract.test.mjs
~~~

Expected: PASS e nenhum tipo proibido aparece.

- [ ] **Step 10: Commit**

~~~bash
git add extension/lib/api.js extension/background/router.js extension/tests/api.test.mjs extension/tests/router.test.mjs
git commit -m "feat: publish the current portal form from heartbeat"
~~~

---

### Task 5: Implementar o estado de follow da Mesa sem roubar foco

**Files:**
- Create: `app/web/portal-current.js`
- Create: `app/web/tests/portal-current.test.mjs`
- Modify: `app/web/app.js`
- Modify: `app/web/index.html`
- Modify: `app/web/tests/ui-wiring.test.mjs`

**Interfaces:**
- Consumes: GET `/api/v1/portal/current-selection`, `selectProcess(processId, options)`.
- Produces em `portal-current.js`:
  - `PORTAL_SELECTION_POLL_MS = 1000`
  - `KNOWN_PORTAL_FIELDS` com os sete campos/labels da spec
  - `classifyPortalProcess(process) -> {state, foundCount, pendingCount, conflictCount}`
  - `followAction({followPortal, selectedId, portalProcessId, activeTab}, observation) -> {portalProcessId, selectProcessId, openPortalTab}`.

- [ ] **Step 1: RED dos helpers de completude**

Testar:
- todos os seis mandatory `found` → `COMPLETO`;
- 1–5 mandatory `found` → `PARCIAL`;
- zero `found` → `SEM_DADOS`;
- `process.status == "DIVERGENCIA"` ou qualquer field com `status == "conflict"` → `CONFLITO`.

- [ ] **Step 2: RED da decisão de follow (Review Focus #4)**

Testar:
- MATCHED A + follow ativo + nenhuma seleção → selecionar A e abrir Portal atual;
- refresh MATCHED A quando A já está selecionado → não trocar tab;
- MATCHED B depois de A → selecionar B e abrir Portal atual;
- follow pausado → atualizar `portalProcessId`, mas não selecionar;
- NOT_FOUND/AMBIGUOUS/NO_ACTIVE_FORM → nunca selecionar.

- [ ] **Step 3: RED do wiring da aba/controles**

Em `ui-wiring.test.mjs`, exigir:
- tab `data-tab="portal"`;
- controles `portal-follow-toggle` e `portal-follow-status`;
- `state.followPortal`, `state.portalProcessId`, `refreshPortalSelection()`;
- polling em 1000 ms com guarda contra chamadas sobrepostas.

- [ ] **Step 4: RED da seleção manual pausando**

Modificar assinatura de `selectProcess` para `selectProcess(processId, { source = "manual", openTab = null } = {})`. Teste deve provar que apenas `source === "manual"` para processo diferente do observado coloca `followPortal=false`; seleção originada do portal não pausa.

- [ ] **Step 5: Rodar RED**

Run:
~~~powershell
node --test app/web/tests/portal-current.test.mjs app/web/tests/ui-wiring.test.mjs
~~~

Expected: FAIL.

- [ ] **Step 6: Implementar helpers e state**

Criar o módulo puro; importar no `app.js`. Adicionar polling independente do refresh de 5 s, com `portalPollRunning` para evitar overlap.

- [ ] **Step 7: Implementar pause/resume**

- clique manual em outro processo → “Acompanhamento pausado”;
- botão → `followPortal=true`;
- se `portalProcessId` ainda corresponde a MATCHED atual, selecionar com `source:"portal"`, `openTab:"portal"`;
- pausar não apaga `portalProcessId`.

- [ ] **Step 8: GREEN**

Run:
~~~powershell
node --test app/web/tests/*.test.mjs
~~~

Expected: PASS.

- [ ] **Step 9: Commit**

~~~bash
git add app/web/portal-current.js app/web/tests/portal-current.test.mjs app/web/app.js app/web/index.html app/web/tests/ui-wiring.test.mjs
git commit -m "feat: follow the current portal process in the mesa"
~~~

---

### Task 6: Construir a aba “Portal atual”, evidências e fill atual

**Files:**
- Modify: `app/web/index.html`
- Modify: `app/web/app.js`
- Modify: `app/web/app.css`
- Modify: `app/web/portal-current.js`
- Modify: `app/web/tests/portal-current.test.mjs`
- Modify: `app/web/tests/ui-wiring.test.mjs`
- Modify: `tests/test_api_server.py` somente se o wiring revelar contrato de API faltante.

**Interfaces:**
- Consumes: `GET /api/v1/processes/<id>`, `GET /api/v1/processes/<id>/evidence/<field>`, viewer existente, POST `/api/v1/portal/current-selection/fill`.
- Produces:
  - `renderPortalCurrent(process)`
  - `startCurrentPortalFill()`
  - refactor compartilhado `followFillRequest(processId, fillRequestId) -> Promise<void>` usado pelo fill antigo e pelo fill atual.

- [ ] **Step 1: RED dos field models**

Em `portal-current.test.mjs`, provar que cada um dos sete campos vira modelo `ENCONTRADO` ou `PENDENTE`, sem inventar valor; conflitos conhecidos produzem `REVISAR`.

- [ ] **Step 2: RED do layout**

Em `ui-wiring.test.mjs`, exigir `detail-workspace`; quando tab é `portal`, classe `portal-layout` coloca viewer/evidência e ficha no workspace. Não criar segundo `canvas`/PDF renderer.

- [ ] **Step 3: RED dos botões Copiar/Ver evidência**

Exigir que cards encontrados chamem `navigator.clipboard.writeText(value)` e `openFieldEvidence(process.id, fieldName)`; pendentes não oferecem cópia de valor inexistente.

- [ ] **Step 4: RED do manual fill atual**

Com observação MATCHED do mesmo `process.id`, “Preencher dados encontrados” chama somente:
~~~text
POST /api/v1/portal/current-selection/fill
~~~
e acompanha a `fill_request` retornada. Não chamar `/api/v1/processes/<id>/fill` neste botão e não chamar navegação.

- [ ] **Step 5: RED de estados não filláveis**

NOT_FOUND, AMBIGUOUS, NO_ACTIVE_FORM ou MATCHED para outro process_id → botão ausente/desabilitado com mensagem explicativa.

- [ ] **Step 6: RED do resumo parcial**

Após fill terminal incompleto, mostrar contagem `alterados`, `preservados`, `para revisar` e instrução explícita de corrigir/concluir manualmente.

- [ ] **Step 7: Rodar RED**

Run:
~~~powershell
node --test app/web/tests/*.test.mjs
~~~

Expected: FAIL nos novos elementos.

- [ ] **Step 8: Implementar layout e cards**

Reutilizar `openFieldEvidence()`, `openDocument()`, `renderFillSummary()` e o `#pdf-viewer` existente. O CSS deve ser responsivo: duas colunas em largura suficiente e uma coluna em viewport estreita.

- [ ] **Step 9: Refatorar polling de fill sem alterar semântica**

Extrair o loop terminal de `startFill()` para `followFillRequest(processId, fillRequestId)`. `startFill()` automático continua usando `/processes/<id>/fill`; `startCurrentPortalFill()` usa current-selection/fill.

- [ ] **Step 10: GREEN UI**

Run:
~~~powershell
node --test app/web/tests/*.test.mjs
~~~

Expected: PASS.

- [ ] **Step 11: Verificar ausência de finalização automática**

Run:
~~~powershell
node --test extension/tests/protocol.test.mjs extension/tests/portal-contract.test.mjs app/web/tests/ui-wiring.test.mjs
~~~

Expected: PASS; nenhum submit/finalize.

- [ ] **Step 12: Commit**

~~~bash
git add app/web/index.html app/web/app.js app/web/app.css app/web/portal-current.js app/web/tests/portal-current.test.mjs app/web/tests/ui-wiring.test.mjs
git commit -m "feat: add the portal current review workspace"
~~~

---

### Task 7: Fechar races cross-component e Reliability Reset

**Files:**
- Modify: `tests/test_fill_service.py`
- Modify: `tests/test_api_server.py`
- Modify: `extension/tests/router.test.mjs`
- Modify: `app/web/tests/portal-current.test.mjs`
- Modify runtime files somente se um RED desta task provar defeito.

**Interfaces:**
- Consumes: todo o contrato implementado nas Tasks 1–6.
- Produces: cobertura explícita dos cinco itens de Review Focus e semântica AR-1 coerente.

- [ ] **Step 1: Testar mudança A→B durante write (Review Focus #2)**

Criar/ajustar teste integrado do fill: request criada para A, resultado/readback reporta B → request `BLOQUEADO`, run AR-1 `passed:false`, nenhum status de B alterado.

- [ ] **Step 2: Testar seleção excepcional sem dados (Review Focus #5)**

Processo `ERRO` ou `REVISAR` com zero campos `found`, identidade exata → manual request não falha por status, não inventa fields, termina com pendências, `mandatory_satisfied == false`, `best_effort_satisfied == true` e AR-1 `passed:true`.

- [ ] **Step 3: Testar stale current-selection após render (Review Focus #1)**

Revalidar no nível HTTP que o clique stale gera no máximo um terminal AR-1 e zero `FILL_FORM`.

- [ ] **Step 4: Testar heartbeat concorrente/antigo (Review Focus #3)**

No router, simular duas leituras sequenciais com A lento e B atual dentro do modelo de execução suportado; garantir que a assinatura publicada não regrede para A. Se a implementação serializa `poll()` por `running`, o teste deve provar essa serialização em vez de inventar concorrência impossível.

- [ ] **Step 5: Testar subaba manual preservada (Review Focus #4)**

MATCHED A repetido com `state.tab="documentos"` não força `portal`; mudança A→B ou resume explícito força `portal`.

- [ ] **Step 6: Rodar suítes focais**

Run:
~~~powershell
python -m unittest tests.test_current_selection tests.test_fill_service tests.test_api_server -v
node --test extension/tests/api.test.mjs extension/tests/router.test.mjs extension/tests/protocol.test.mjs extension/tests/portal-contract.test.mjs
node --test app/web/tests/*.test.mjs
~~~

Expected: PASS.

- [ ] **Step 7: Corrigir somente RED reproduzível**

Aplicar mudanças mínimas nos owners corretos; não adicionar retries/sleeps para esconder race.

- [ ] **Step 8: Repetir suítes focais**

Expected: PASS.

- [ ] **Step 9: Commit de hardening, se houve mudança**

~~~bash
git add <somente arquivos tocados>
git commit -m "fix: harden portal current best-effort flow"
~~~

---

### Task 8: Revisão, gates globais, novo AR1_BUILD e ZIP limpo

**Files:**
- Modify: `docs/notes/2026-09-30-area-restrita-reliability-reset-phase-1-handoff.md`
- No product code unless review produces um defeito reproduzível.

**Interfaces:**
- Consumes: branch implementada e packaging provenance existente.
- Produces: novo `AR1_BUILD`, ZIP limpo verificado, handoff e estado `manual_form_fill=EXPERIMENTAL` em 0/20.

- [ ] **Step 1: Executar review independente**

Usar `superpowers:requesting-code-review` com foco em:
- bypass de identidade;
- snapshot transitório vazando/persistindo;
- current-selection stale;
- heartbeat/follow races;
- mudança involuntária do automatic fill;
- qualquer submit/finalize;
- regressão de package provenance.

- [ ] **Step 2: Corrigir achados reproduzíveis com TDD**

Cada achado deve ganhar RED focal antes da correção; reexecutar o gate relevante.

- [ ] **Step 3: Rodar gates completos**

~~~powershell
python -m unittest discover -s tests -p "test_*.py" -q
npm test --prefix extension
node --test app/web/tests/*.test.mjs
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass `
  -File .\work\tce-extractor\verify-project.ps1
git diff --check
~~~

Expected: zero falhas. Registrar contagens reais, não reutilizar números antigos.

- [ ] **Step 4: Confirmar árvore limpa e congelar o build**

~~~powershell
git status --short
git rev-parse HEAD
git fetch origin --prune
~~~

Se houver alterações, commitá-las e repetir os gates afetados. O SHA limpo final desta etapa passa a ser `AR1_BUILD`.

- [ ] **Step 5: Gerar ZIP limpo sem acervo a partir do AR1_BUILD**

Usar somente `packaging/build-portable.ps1` e o fluxo de provenance já existente. Se o HEAD avançar depois apenas por handoff, usar worktree limpa no `AR1_BUILD`.

Exemplo:
~~~powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass `
  -File .\packaging\build-portable.ps1 `
  -OutputPath .\dist\Atos-TCE-portable-clean.zip `
  -Force
~~~

- [ ] **Step 6: Verificar provenance e smoke**

~~~powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass `
  -File .\packaging\verify-package.ps1 `
  -ZipPath .\dist\Atos-TCE-portable-clean.zip `
  -ExpectedBuildId <AR1_BUILD>

Get-FileHash .\dist\Atos-TCE-portable-clean.zip -Algorithm SHA256
~~~

Expected:
- verifier PASS;
- `package-manifest build_id == AR1_BUILD`;
- `health.build_id == AR1_BUILD`;
- nenhum `data/`, DB real, PDF do acervo, profile, cookie ou token no ZIP.

- [ ] **Step 7: Smoke funcional descartável do Portal atual**

Em data root temporário/fixture sanitizada:
- Mesa inicia;
- current-selection GET começa `NO_ACTIVE_FORM`;
- extensão/fixture publica MATCHED;
- GET retorna process_id correto sem snapshot privado;
- fill current selection cria request manual quando snapshot existe;
- clear/TTL remove fillability.

Não usar portal real nem ledger real nesta etapa.

- [ ] **Step 8: Preparar Reliability Reset no novo build**

Na raiz real, sem executar tentativa:
~~~powershell
python scripts/portal-reliability/capability-state.py `
  --data-root data `
  --capability manual_form_fill `
  --experimental `
  --build <AR1_BUILD>
~~~

Confirmar:
~~~text
state = EXPERIMENTAL
real_dev_streak = 0
portable_streak = 0
~~~

Não apagar ledger histórico de outros builds.

- [ ] **Step 9: Atualizar handoff**

Registrar:
- novo AR1_BUILD;
- contagens dos gates;
- ZIP filename/entries/size/SHA-256;
- provenance/smoke;
- nova semântica: status local não é gate do manual fill;
- Portal atual/follow/pause;
- instrução do primeiro run real;
- AR-2/AR-3 continuam fechados.

- [ ] **Step 10: Commit docs-only do handoff**

~~~bash
git add docs/notes/2026-09-30-area-restrita-reliability-reset-phase-1-handoff.md
git commit -m "docs: hand off portal current AR-1 build"
git push origin codex/area-restrita-reliability-reset
~~~

O commit docs-only pode deixar a branch à frente do `AR1_BUILD`; documentar explicitamente que os bytes do pacote correspondem ao SHA congelado.

- [ ] **Step 11: STOP antes do portal real**

Não executar AR-1 real sem operador autenticado. A próxima ação humana é:
1. iniciar Mesa com `ATOS_TCE_BUILD_ID=<AR1_BUILD>` e `ATOS_TCE_RELIABILITY_ENVIRONMENT=real-dev`;
2. recarregar a extensão;
3. abrir um formulário real;
4. confirmar que a Mesa acompanha automaticamente o processo correto;
5. clicar **uma vez** em “Preencher dados encontrados” ou no manual fill equivalente;
6. inspecionar um único `run_finished`.

Se `passed:true`, sequência = 1/20. Se `passed:false` ou terminal ausente, parar e usar `superpowers:systematic-debugging`.

---

## Definition of Done

- [ ] Manual fill não depende de `PRONTO/PREENCHIDO`.
- [ ] Automatic fill mantém a guarda anterior.
- [ ] Partial fill preserva status incompleto do processo.
- [ ] `mandatory_satisfied` e `best_effort_satisfied` permanecem separados.
- [ ] Partial/no-op seguro pode passar AR-1; falha de campo presente em `plan.fields` continua falhando AR-1.
- [ ] Tracker atual é 100% transitório e TTL=10 s.
- [ ] Snapshot privado nunca aparece no GET, DB, logs ou reliability telemetry.
- [ ] Heartbeat publica com sidepanel fechado.
- [ ] Dedupe + keepalive=5 s funcionam.
- [ ] Mesa acompanha A→B automaticamente quando follow está ativo.
- [ ] Seleção manual pausa e Retomar restaura.
- [ ] Repetição do mesmo processo não rouba a subaba do usuário.
- [ ] Portal atual mostra campos, pendências, copy e evidência usando o viewer existente.
- [ ] “Preencher dados encontrados” usa somente current-selection/fill e não navega.
- [ ] NOT_FOUND/AMBIGUOUS/STALE nunca escrevem.
- [ ] Nenhum submit/finalize foi introduzido.
- [ ] Cinco Review Focus têm teste explícito.
- [ ] Gates globais verdes.
- [ ] Novo AR1_BUILD congelado.
- [ ] ZIP limpo sem acervo passa provenance/smoke.
- [ ] Reliability Reset preparado em EXPERIMENTAL 0/20.
- [ ] Handoff atualizado e execução para antes do primeiro run real.
