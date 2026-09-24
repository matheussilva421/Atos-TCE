# Atos-TCE — Plano Consolidado de Retomada da Área Restrita

**Data:** 2026-09-24  
**Branch canônica de retomada:** `codex/atos-tce-unified`  
**HEAD observado no GitHub em 2026-09-24:** `dcb9086fe5fdffe89022bfc14c07a85e728232df`  
**Base atual:** `main` em `b1d41e848c39cb61947b011501925c40f86793fb`  
**Situação Git observada:** `codex/atos-tce-unified` está 44 commits à frente de `main` e 0 atrás.

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans`. Do not restart already completed best-effort work. Treat this plan as an orchestration/retomada plan over the existing canonical specs and plans.

## 1. Objetivo

Retomar o trabalho existente sem duplicar arquitetura, usando o novo laboratório da Área Restrita (Chrome DevTools MCP + Playwright CLI + captura/fixtures sanitizadas) para fechar os gates reais que bloquearam os planos de:

1. Best-Effort Form Filling + Fundamento Legal v4;
2. Próximo Processo;
3. investigação/estabilização do portal legado.

O runtime final deve continuar totalmente standalone:

```text
START.cmd
  -> Mesa Local
  -> backend
  -> extensão MV3
  -> Área Restrita/e-Contas
```

Codex, MCP, Playwright CLI e Skills são ferramentas exclusivamente de desenvolvimento.

---

# 2. Fontes canônicas

Não reescrever nem substituir os documentos abaixo sem uma decisão explícita:

- `docs/superpowers/specs/2026-09-23-best-effort-form-filling-design.md`
- `docs/superpowers/plans/2026-09-23-best-effort-form-filling-implementation.md`
- `docs/superpowers/plans/2026-09-23-next-process-navigation-implementation.md`
- `docs/notes/2026-09-23-best-effort-form-filling-handoff.md`
- `docs/notes/2026-09-23-best-effort-fill-validation-handoff.md`
- `docs/notes/2026-09-23-area-restrita-next-navigation-discovery.md`
- `docs/notes/2026-09-24-git-reconciliation-handoff.md`

Novo complemento arquitetural:

- `docs/superpowers/specs/2026-09-24-area-restrita-lab-design.md`
- `docs/superpowers/plans/2026-09-24-area-restrita-reverse-engineering-plan.md`

---

# 3. Estado real de retomada

## 3.1 Best-effort / Fundamento Legal v4

**Não reimplementar Tasks 1–9.**

A branch unificada já contém, com testes:

- filtro canônico de opções legais selecionáveis;
- legal-foundation-v4 best available;
- preflight best-effort por campo;
- formulário parcial legível;
- filler por campo;
- preservação de valores divergentes;
- stale generation com uma releitura/replanejamento;
- resumo parcial;
- processo permanecendo `PRONTO` quando ainda há pendências;
- UI da Mesa mostrando alterados/preservados/revisar;
- integração backend + extensão.

### Pendência real

A **Task 10** ainda não está concluída porque falta validação supervisionada no portal real.

Portanto:

```text
Best-effort
Tasks 1–9: IMPLEMENTADAS
Task 10:
  automated gates: já executados em handoffs anteriores
  real portal qualification: PENDENTE
```

A validação exige cinco casos reais supervisionados e um caso de falha isolada de campo, sem automação do clique final.

---

## 3.2 Próximo Processo

**Nenhuma Task 1–8 de produção deve ser iniciada ainda.**

A Phase 0 foi parcialmente executada e já descobriu:

```yaml
navigation_strategy: native_control
marker_restore: not_needed
```

Foi observado:

- retorno nativo por `Proc./ Doc. Eletrônicos`;
- preservação do marcador nas amostras;
- abertura do ato alvo por identidade;
- travessia de fronteira de página;
- frame/lista + frame irmão;
- interessado único em casos observados;
- tempos de navegação aproximados.

### Pendências da Phase 0

Ainda faltam, antes da Task 1:

1. `SCAN_PAGE` vivo com a Mesa/extensão atual;
2. confirmar o valor bruto vivo do marcador;
3. reconciliar o delta `1198` salvo vs `1197` observado;
4. baseline estrita após ato concluído/revisado;
5. observar o retorno após clique final feito **manualmente pelo operador**;
6. caso multi-interessado, se houver caso controlado disponível;
7. atualizar/fechar a nota de discovery.

Logo:

```text
Next Process
Phase 0: PARCIAL / BLOQUEADA
Tasks 1–8: NÃO INICIADAS
```

---

# 4. Decisão arquitetural de retomada

O laboratório novo não é uma feature concorrente.

Ele passa a ser a infraestrutura que fecha os gates que os planos de 23/09 não conseguiam fechar.

```text
                     LABORATÓRIO

Chrome dedicado
   |
Chrome DevTools MCP
   |
Playwright CLI
   |
captura before/after
   |
sanitização
   |
portal-contract / fixture
   |
teste RED
   |
runtime existente
```

Portanto:

- **não** criar outro motor de preenchimento;
- **não** criar outro motor de navegação;
- **não** duplicar seletores;
- **não** substituir a extensão por Playwright;
- **não** iniciar `OPEN_NEXT_ACT` antes do discovery fechar.

---

# 5. Nova ordem de execução

## Fase A — Congelar a branch canônica e provar baseline

### A1. Trabalhar a partir de `codex/atos-tce-unified`

Antes de qualquer alteração:

```powershell
git fetch origin --prune
git switch codex/atos-tce-unified
git pull --ff-only origin codex/atos-tce-unified
git status --short
git rev-parse HEAD
git rev-list --left-right --count origin/main...HEAD
```

Esperado:

```text
working tree clean
HEAD >= dcb9086...
branch ahead of main
```

### A2. Não promover/mergear para `main` ainda

O plano original falava em promoção de branches intermediárias. A reconciliação de 24/09 já criou `codex/atos-tce-unified`.

Essa branch deve ser tratada como fonte canônica de desenvolvimento até os gates reais finais.

### A3. Rodar baseline atual

```powershell
python -m unittest discover -s tests -p "test_*.py" -q
npm test --prefix extension
node --test app/web/tests/*.test.mjs
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass `
  -File .\work\tce-extractor\verify-project.ps1
git diff --check
```

Nenhuma implementação nova começa se o baseline estiver vermelho.

---

# Fase B — Instalar somente a infraestrutura mínima do Portal Lab

Executar do plano `2026-09-24-area-restrita-reverse-engineering-plan.md`:

1. boundary laboratório/runtime;
2. Chrome dedicado/CDP;
3. Chrome DevTools MCP;
4. Playwright CLI;
5. capturador estrutural;
6. sanitizador;
7. comparador before/after;
8. Skill `area-restrita`.

## Gate B

Antes de usar no portal:

```text
[ ] Chrome dedicado
[ ] CDP somente 127.0.0.1
[ ] sem cookies/tokens em fixtures
[ ] raw evidence ignorada pelo Git
[ ] sanitizador testado
[ ] packaging não inclui laboratório
[ ] L0/L1/L2/L3 definido
```

Nenhuma mudança funcional de runtime nesta fase.

---

# Fase C — Usar o laboratório para concluir Best-Effort Task 10

Esta fase vem **antes** de implementar Próximo Processo.

## C1. Reexecutar gates do código já implementado

Não modificar best-effort antes de testar o estado unificado.

## C2. Abrir sessão real supervisionada

Fluxo:

```text
operador autentica
  -> agente L0 observa
  -> operador escolhe ato controlado
  -> extensão abre/prepara
  -> FILL_FORM
  -> agente observa DOM/resultados
  -> operador revisa
  -> NÃO automatizar conclusão
```

## C3. Casos obrigatórios

Validar:

1. ECE 20/2020 não literal;
2. EC 41/2003;
3. EC 47/2005;
4. CF art. 40;
5. correspondência fraca/não literal.

Para cada um:

- identidade sanitizada no handoff público;
- texto documental;
- catálogo DOM;
- opção escolhida;
- confidence/margin/hard conflict;
- field results;
- releitura;
- status final da fill request;
- status documental do processo.

Dados identificáveis ficam em artefato privado, não no Git.

## C4. Caso best-effort crítico

Criar/usar caso controlado no qual:

```text
campo A -> gravável
campo B -> gravável
campo C -> ausente/disabled/divergente
```

Aceitação:

```text
A/B preenchidos
C warning
nenhum rollback global
processo continua retryable se C obrigatório
```

## C5. Se houver divergência

Nunca patch direto.

Sequência obrigatória:

```text
captura real
  -> sanitizar
  -> fixture
  -> teste RED
  -> correção mínima
  -> GREEN
```

## Gate C

Best-effort Task 10 só fecha quando a validação supervisionada for documentada.

---

# Fase D — Fechar a Phase 0 do Próximo Processo usando o laboratório

O novo laboratório deve substituir a investigação improvisada, não o plano funcional.

## D1. Obter `SCAN_PAGE` vivo

Com Mesa + extensão atuais.

Registrar:

- `source_scope`;
- marcador label/value;
- página;
- total pages;
- identidades anonimizadas;
- ordem.

## D2. Reconciliar 1198 vs 1197

Não aceitar simplesmente “lista mudou”.

Determinar se é:

- item removido;
- item adicionado;
- duplicata no scan salvo;
- concluído que saiu;
- diferença de classificação;
- erro de paginação;
- drift de marcador;
- alteração legítima do portal.

Se não houver como determinar o item por dados públicos, usar hashes/identidades sanitizadas.

## D3. Validar retorno pós-conclusão manual

O operador:

1. revisa formulário;
2. executa manualmente `Complementar Ato`;
3. agente observa somente o resultado.

Registrar:

```text
FORM
 -> manual final action
 -> ?
 -> Proc./ Doc. Eletrônicos
 -> LIST
```

Mapear frames antes/depois.

## D4. Baseline estrita

Três medições:

```text
ato concluído/revisado
  -> próximo exato
  -> formulário alvo pronto
```

## D5. Caso multi-interessado

Se existir caso controlado disponível, observar.

Se não existir, documentar explicitamente que a evidência real não cobre múltiplos interessados; o runtime deve continuar fail-closed e usar testes sintéticos para a ambiguidade.

## D6. Atualizar discovery note

Só marcar Phase 0 fechada quando todas as evidências mandatórias estiverem registradas.

## Gate D

**Somente depois desse gate** começar `Next Process Task 1`.

---

# Fase E — Implementar Próximo Processo Tasks 1–8

Executar o plano canônico de 23/09 sem reinventá-lo.

## E1. Task 1 — NavigationService

Mesa escolhe o próximo alvo a partir da ordem do scan.

A extensão não escolhe row por posição.

## E2. Task 2 — API `/api/v1/portal/next-act`

Mesa/sidepanel enviam somente identidade/processo atual.

Backend escolhe o alvo.

## E3. Task 3 — `OPEN_NEXT_ACT`

Orquestração no router.

Usar o conhecimento da Phase 0:

```yaml
navigation_strategy: native_control
marker_restore: not_needed
```

Se a Phase 0 final contradisser isso, corrigir SPEC/plan antes do código.

## E4. Task 4 — Return to list

Implementar **somente** o mecanismo observado.

Não adicionar fallback especulativo:

```text
native_control
OR history_back
OR direct_route
```

não os três.

## E5. Tasks 5–6 — Sidepanel + Mesa

Adicionar Próximo Processo.

Não disparar preenchimento automaticamente.

## E6. Task 7 — Hardening

Cobrir:

- cross-page;
- stale target;
- marker drift;
- multiple frames;
- vanished process;
- exact target identity;
- last confirmed identity.

## E7. Task 8 — Real validation

Comparar tempo automatizado com baseline da Phase 0.

---

# Fase F — Converter conhecimento do portal em contrato permanente

Depois de C + D, consolidar o Portal Lab.

Criar/promover:

```text
devtools/area-restrita/portal-contract.json
devtools/area-restrita/fixtures/list-page.json
devtools/area-restrita/fixtures/interested.json
devtools/area-restrita/fixtures/form.json
devtools/area-restrita/fixtures/buttons.json
```

O contrato é oracle/teste/documentação.

**Não é um segundo runtime.**

`extension/lib/area-snapshot.js` continua sendo o dono operacional dos seletores.

---

# Fase G — Reduzir `SCREEN_NOT_NAVIGABLE` somente com evidência

Depois do mapeamento real, revisar os erros.

Possíveis estados/códigos:

```text
FRAME_TRANSITIONING
ROW_ACTION_NOT_FOUND
INTERESTED_NOT_FOUND
FORM_NOT_AVAILABLE
FORM_AMBIGUOUS
FORM_IDENTITY_MISMATCH
TARGET_NOT_FOUND
MARKER_MISMATCH
SCREEN_NOT_NAVIGABLE
```

Regra:

`SCREEN_NOT_NAVIGABLE` continua existindo para estado realmente desconhecido.

Não converter todos os casos em retry.

---

# Fase H — Gate standalone final

Provar novamente que todas as ferramentas agentic são só de desenvolvimento.

ZIP permitido:

```text
app/
extension/
runtime/
START.cmd
README.md
licenses/
...
```

ZIP proibido:

```text
devtools/
.agents/
.playwright-cli/
node_modules/
tmp/portal-lab/
chrome-devtools-mcp
playwright-cli
```

Build:

```powershell
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass `
  -File .\packaging\build-portable.ps1
```

Verify:

```powershell
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass `
  -File .\packaging\verify-package.ps1 `
  -ZipPath .\dist\Atos-TCE-portable.zip
```

O smoke não deve ter Node/MCP/Playwright no PATH.

---

# 6. Ordem final resumida

```text
codex/atos-tce-unified
        |
        v
[A] baseline atual
        |
        v
[B] Portal Lab mínimo
        |
        +--------------------------+
        |                          |
        v                          v
[C] fechar Best-Effort        [D] fechar Next Phase 0
    Task 10                       discovery
        |                          |
        +------------+-------------+
                     |
                     v
              [E] Next Tasks 1–8
                     |
                     v
              [F] portal-contract
                     |
                     v
              [G] erros/estados
                     |
                     v
              [H] standalone gate
                     |
                     v
                 MERGE/RELEASE
```

---

# 7. Coisas que NÃO devem ser feitas

- Não reexecutar Tasks 1–9 do best-effort como se estivessem ausentes.
- Não descartar a branch `codex/atos-tce-unified`.
- Não começar `navigation_service.py` antes de fechar Phase 0.
- Não usar Playwright como runtime final.
- Não substituir a extensão pelo MCP.
- Não criar um segundo mapa de seletores.
- Não corrigir navegação somente aumentando delay/retry.
- Não inferir o próximo processo pela row seguinte.
- Não automatizar `Complementar Ato` final.
- Não promover processo para `PREENCHIDO` apenas porque a fill request terminou.
- Não incluir traces/HAR/perfis/cookies no Git ou ZIP.

---

# 8. Critério de conclusão global

```text
[ ] branch unificada preservada e baseline verde
[ ] Portal Lab funcional e isolado do runtime
[ ] Best-Effort Task 10 validada em portal real
[ ] cinco casos legais reais documentados
[ ] caso best-effort parcial real documentado
[ ] Next Phase 0 concluída
[ ] delta scan/list reconciliado
[ ] marcador vivo confirmado
[ ] retorno após conclusão manual observado
[ ] Next Tasks 1–8 implementadas
[ ] exact target identity comprovada
[ ] nenhum submit/finalize automatizado
[ ] portal-contract/fixtures sanitizados
[ ] Python/extension/web/project gates verdes
[ ] ZIP não contém ferramentas de desenvolvimento
[ ] extração limpa funciona sem IA/MCP/Playwright
```

## Estratégia recomendada

**Subagent-driven**, com revisão independente por fase.

Não paralelizar:

- validação real Best-Effort e mudanças no filler;
- Phase 0 e implementação de Next;
- mudanças em `area-snapshot.js`, `navigate.js` e `router.js` que dependam do mesmo comportamento real.

O laboratório pode ser preparado em paralelo com testes puramente offline, mas qualquer ação no Chrome autenticado deve ser serial e deliberada.