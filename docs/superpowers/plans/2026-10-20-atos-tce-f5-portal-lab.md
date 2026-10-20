# Atos-TCE F5 — REA / Portal Lab / Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Investigar o comportamento do portal com evidências seguras, promover fixtures para testes e qualificar capacidades antes de produção.

**Architecture:** Reutilizar `devtools/area-restrita`, `scripts/portal-lab` e a skill local; Chrome DevTools MCP observa a estrutura, Playwright CLI reproduz uma transição autorizada de cada vez, REA auxilia a análise. MV3 permanece o runtime; o Reliability Reset governa os gates reais.

**Tech Stack:** Python/unittest, Node node:test, PowerShell, MV3, Chrome QA/CDP loopback; REA/DevTools MCP/Playwright CLI somente desenvolvimento.

**Spec:** `docs/superpowers/specs/2026-10-20-atos-tce-mesa-extensao-json-portal-lab-design.md` §§13–17, `docs/superpowers/specs/2026-09-24-area-restrita-lab-design.md` e `docs/superpowers/specs/2026-09-30-area-restrita-reliability-reset-design.md`.

## Global Constraints
- L0 observa estrutura sem ler valores, cookies, tokens, credenciais ou conteúdo privado; L1 navegação, L2 preparação só com gate por sessão e operador; L3 conclusão é proibida a ferramentas.
- Chrome QA com autenticação humana e CDP `127.0.0.1`; nunca controlar perfil pessoal do operador.
- Sem dados reais identificáveis em Git. Somente fixtures fictícias/sanitizadas revisadas; sem HAR/traces brutos no ZIP.
- `extension/lib/area-snapshot.js` é o proprietário dos seletores runtime, não duplicar em REA ou scripts.
- REA e Playwright são ferramentas de desenvolvimento, não controladores autorizados do runtime. Análise de tráfego com proxy não faz parte da abordagem padrão.
- Reliability Reset: 20/20 execuções reais consecutivas **na mesma build** para QUALIFIED e 20/20 no portátil/Chrome normal para PRODUCTION, com revisão; fixture offline não substitui evidência real.
- Cada task futura: RED observado, GREEN mínimo, regressão, commit isolado e fresh reviewer; nenhum merge/release automático.

## Review Focus
1. Captura estrutural com conteúdo identificável é recusada antes do commit (T1).
2. Frames irmãos visíveis/ocultos e erro VBScript não provocam escolha de primeiro frame ou retry cego (T2).
3. Sem evidência positiva de conclusão após clique humano, nenhum `ACT_CONFIRMED_COMPLETED` é criado (T3).
4. 19/20, 20 testes sintéticos ou troca de build não promovem QUALIFIED (T4).
5. ZIP limpo não inclui ferramentas de desenvolvimento e permanece funcional sem elas (T5).

---

### Task F5-T1: Gate L0 e sanitização

**Files:** Modify `scripts/portal-lab/sanitize-capture.py`, `tests/test_portal_lab_contract.py`, `tests/test_devtools_runtime_boundary.py`; revisar `.agents/skills/area-restrita/references/safety.md`.

**Interfaces:** entrada de captura estrutural -> resultado sanitizado ou recusa; não persistir valores de formulário.

- [ ] **Step 1 — RED:** `PortalLabContractTests.test_reject_sensitive_capture`: exigir recusa de fixtures com identificador pessoal fictício, campo `value` sensível, query token ou cookie; somente atributos estruturais permitidos.
- [ ] **Step 2 — Observar RED:** `python -m unittest tests.test_portal_lab_contract tests.test_devtools_runtime_boundary -v`; FAIL na nova asserção.
- [ ] **Step 3 — GREEN:** Reaproveitar sanitizador existente, corrigindo apenas lacunas demonstradas; validar perfil Chrome QA, baseline e CDP loopback antes de L0 real.
- [ ] **Step 4 — Verificar:** Focado PASS; `python -m unittest discover -s tests -p "test_*.py" -q` PASS; revisão manual das saídas.
- [ ] **Step 5 — Commit:** `git add scripts/portal-lab/sanitize-capture.py tests/test_portal_lab_contract.py tests/test_devtools_runtime_boundary.py && git commit -m "test: harden portal lab L0 sanitization"`.
- [ ] **Step 6 — Review:** Fresh reviewer de privacidade verifica PII, armazenamento, logs e origem do navegador.

### Task F5-T2: Contratos estruturais e fixtures REA

**Files:** Modify `devtools/area-restrita/portal-contract.json`, `devtools/area-restrita/fixtures/`, `extension/tests/portal-contract.test.mjs`; `extension/lib/area-snapshot.js` somente após RED comprovado.

**Interfaces:** LIST, INTERESTED, FORM, TRANSITIONING, AMBIGUOUS, SESSION_EXPIRED; estrutura conhecida dos cinco campos, sem escrita jurídica.

- [ ] **Step 1 — RED:** `hidden_form_does_not_compete`, `two_visible_forms_block`, `vbscript_modality_error_is_unavailable`: assert `state === "AMBIGUOUS"` quando dois formulários candidatos válidos estão visíveis; erros não autorizam escrita.
- [ ] **Step 2 — Observar RED:** `node --test extension/tests/portal-contract.test.mjs` FAIL.
- [ ] **Step 3 — GREEN:** Usar REA para hipóteses, DevTools MCP para leitura estrutural, Playwright CLI para transição autorizada isolada; fixture sanitizada -> teste RED -> correção mínima no dono de seletor.
- [ ] **Step 4 — Verificar:** Focado PASS, `(cd extension && node --test)` PASS; distinguir `NOT_OBSERVED_REAL` de prova live.
- [ ] **Step 5 — Commit:** `git add devtools/area-restrita/portal-contract.json devtools/area-restrita/fixtures extension/tests/portal-contract.test.mjs extension/lib/area-snapshot.js && git commit -m "test: align portal contract with safe observations"`.
- [ ] **Step 6 — Review:** Fresh reviewer confirma frame exato, nenhuma escolha por índice, privacidade e mínimo escopo.

### Task F5-T3: Matriz L1/L2 e prova pós-clique humano

**Files:** Create `docs/notes/2026-10-20-area-restrita-investigation-matrix.md`; Modify `tests/test_portal_lab_contract.py` e `.agents/skills/area-restrita/references/workflow.md`.

**Interfaces:** matriz com `scenario,level,authorization,observed_real,fixture,test,unresolved`; `level=L3` sempre recusado.

- [ ] **Step 1 — RED:** `PortalLabContractTests.test_l2_requires_human_gate_and_l3_forbidden`: caso L2 sem autorização deve falhar; L3 nunca passa.
- [ ] **Step 2 — Observar RED:** `python -m unittest tests.test_portal_lab_contract -v` FAIL.
- [ ] **Step 3 — GREEN:** Documentar campos e máscaras, aba/frame, interessado, erros de modalidade e sinal de conclusão pós-clique manual. L1/L2 somente após gate específico. Se prova de conclusão não for inequívoca, F4-T1 continua bloqueado.
- [ ] **Step 4 — Verificar:** Teste PASS, matriz rastreável e sanitizada; sem alegar varredura live enquanto não executada.
- [ ] **Step 5 — Commit:** `git add docs/notes/2026-10-20-area-restrita-investigation-matrix.md tests/test_portal_lab_contract.py .agents/skills/area-restrita/references/workflow.md && git commit -m "docs: define gated portal investigation and evidence matrix"`.
- [ ] **Step 6 — Review:** Reviewer independente rejeita comandos finais, inferência de sucesso e gates omissos.

### Task F5-T4: Contadores de qualificação por build/ambiente

**Files:** Modify `app/area_restrita/reliability.py`, `tests/test_area_restrita_reliability.py`; Create `tests/test_reliability_qualification_gate.py`.

**Interfaces:** ledger atual com capability, build SHA, environment, sequência consecutiva real, status `UNQUALIFIED/EXPERIMENTAL/QUALIFIED/PRODUCTION`.

- [ ] **Step 1 — RED:** `test_19_of_20_cannot_qualify`, `test_new_build_resets_streak`, `test_portable_requires_second_twenty`; assert state != `QUALIFIED` em 19 sucessos.
- [ ] **Step 2 — Observar RED:** `python -m unittest tests.test_reliability_qualification_gate -v` FAIL.
- [ ] **Step 3 — GREEN:** Aplicar regra às capabilities aplicáveis AR-1–AR-6, separando offline/real-dev/real-portable e reset após falha, sem requalificação por decreto.
- [ ] **Step 4 — Verificar:** Focado PASS e `python -m unittest tests.test_area_restrita_reliability -v` PASS. Execuções live requerem gate prévio L1/L2 específico.
- [ ] **Step 5 — Commit:** `git add app/area_restrita/reliability.py tests/test_area_restrita_reliability.py tests/test_reliability_qualification_gate.py && git commit -m "test: enforce twenty consecutive real qualification attempts"`.
- [ ] **Step 6 — Review:** Fresh reviewer verifica 20/20+20/20, identidade exata, SHA e regressão de capability PRODUCTION.

### Task F5-T5: Verificação do ZIP de extração limpa

**Files:** Modify `packaging/verify-package.ps1`, `tests/test_packaging_contract.py`, `tests/test_devtools_runtime_boundary.py`.

**Interfaces:** rejeitar `devtools/`, `.agents/`, `tmp/portal-lab/`, `node_modules/`, perfis, traces e dependência em Node/REA/MCP/Playwright no pacote.

- [ ] **Step 1 — RED:** `PackagingContractTests.test_devtools_never_in_zip`: um pacote de teste contendo a pasta de laboratório é rejeitado, enquanto versão limpa passa.
- [ ] **Step 2 — Observar RED:** `python -m unittest tests.test_packaging_contract tests.test_devtools_runtime_boundary -v` FAIL.
- [ ] **Step 3 — GREEN:** Atualizar manifesto/verificador para runtime raiz e reconstruir o ZIP em fase autorizada usando packaging/build-portable.ps1; realizar smoke em extração limpa, sem alterar o legado por semelhança.
- [ ] **Step 4 — Verificar:** Python raiz, `(cd extension && node --test)`, `node --test app/web/tests/*.test.mjs` PASS; `powershell.exe -NoProfile -File .\packaging\verify-package.ps1 -ZipPath .\dist\Atos-TCE-portable.zip` PASS após build autorizado.
- [ ] **Step 5 — Commit:** `git add packaging/verify-package.ps1 tests/test_packaging_contract.py tests/test_devtools_runtime_boundary.py && git commit -m "test: verify standalone runtime excludes development tools"`.
- [ ] **Step 6 — Review:** Reviewer valida ZIP, state machine, ausência de dados reais e handoff.

## Exit gate
- [ ] Todos os tasks RED/GREEN, commits, reviewers e evidências sanitizadas.
- [ ] Sem L3 por automação. Cada capability só pode ser promovida após 20/20 real-dev + 20/20 portátil e revisão explícita.
- [ ] ZIP limpa e funciona sem ferramentas do laboratório.
- [ ] Handoff para aceite humano. Nenhum merge ou release autorizado por este plano.
