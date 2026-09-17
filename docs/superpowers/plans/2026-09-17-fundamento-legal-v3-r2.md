# Fundamentação Legal v3 — Implementation Plan R2

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Before implementation, use `superpowers:using-git-worktrees` and work outside `main`.

**Goal:** tornar `fundamento_legal` fail-closed, obrigatoriamente dependente de `LegalContext` válido, classificado pelo catálogo real do TCE/RN e protegido por uma segunda barreira antes de qualquer `APPLY_FIELDS`, sem regredir o fluxo de piloto atualmente presente no `main`.

**Architecture:** o Service Worker será o único proprietário da aquisição do contexto jurídico por meio de `ensureLegalContext()`, com resolução em três níveis: cache válido, sidecar atual e reconstrução pontual. A classificação jurídica migra para `legal-foundation-v3`, transforma opções cruas `{value,label}` em assinaturas estruturadas e separa compatibilidade jurídica, crosswalk, hard rejects e score. O painel apenas consome a decisão; não busca contexto e não pode escrever fundamento sem `LegalDecision v3` automática.

**Tech Stack:** JavaScript ES modules, Node `node:test`, Chrome Extension Manifest V3, Python 3.14 `unittest`, serviço HTTP loopback autenticado, JSON sidecars, PowerShell para gates/empacotamento.

**Spec:** `docs/superpowers/specs/2026-09-17-fundamento-legal-v3-design.md`

**Supersedes:** `docs/superpowers/plans/2026-09-17-fundamento-legal-v3.md`

**Reviewed baseline:** `main` em `a5a4f16ae8068acbb4ff366e5e31fae49c9cfbbf` ou commit posterior que contenha integralmente `fa90605192d4ade824e0f71efbc45cfc4b34c588`.

## Drift review incorporated in R2

Depois do plano original (`3f6bd8ee96a96891dfe2aecefdfa3fe21e84ee9a`), o `main` recebeu dois commits. O único código de produção alterado foi `background/automation-controller.js`, acompanhado de `tests/automation-controller.test.mjs`; a lógica de `LegalContext`, matcher, crosswalk, painel e serviço Python não foi modificada.

A alteração nova do piloto é requisito a preservar: quando o usuário não digita marcador no painel, o controlador lê `snapshot.marker` já selecionado no portal, trava `label/value` na execução e não inventa nem escolhe outro marcador. O smoke real desta R2 deve usar essa regra. O launcher `work/tce-extractor/.codex-live-pilot.py` permanece ferramenta local não rastreada e não deve ser adicionado ao Git.

O último gate registrado antes desta revisão mostrou extensão/web/python verdes, mas não registrou o término do estágio PowerShell. Portanto esta R2 começa com um baseline obrigatório antes da primeira mudança de código.

## Global Constraints

- `LegalContext` continua no schema atual e na extração `legal-context-v4`; a versão das regras passa para `legal-foundation-v3`.
- `fundamento_legal` nunca pode cair no matcher genérico, com ou sem contexto.
- Se contexto não puder ser recuperado/reconstruído, somente `fundamento_legal` fica bloqueado; os demais campos continuam disponíveis.
- Recuperação deve ser pontual por processo/interessado; não reprocessar o lote inteiro.
- Reaproveitar texto nativo, cache OCR e PDF local já existente; não disparar coleta global para corrigir um único contexto.
- Similaridade lexical nunca cria compatibilidade jurídica; ela só participa depois da filtragem estrutural.
- Cargo `Professor` é contexto; não inventa CF art. 40, § 5º sem referência expressa.
- `proventos integrais` não significa, por si só, integralidade/paridade.
- EC + ECE não é conflito global. ECE/RN 20/2020 art. 2º pode ser cláusula de preservação ao lado de EC 41/2003.
- Thresholds permanecem: AUTO `confidence >= 0.90` e `margin >= 0.12`; REVIEW `confidence >= 0.75`.
- Escrita de fundamento exige `status=selected`, `decision_state=AUTO_SELECTED`, `hard_conflict=false`, thresholds satisfeitos, `rules_version=legal-foundation-v3` e `option_value` existente no catálogo atual.
- REVIEW, TRUE_TIE, CONTEXT_BLOCKED e PENDING jamais são escritos, nem no fluxo manual “Preencher campos disponíveis”.
- Preservar a regressão do piloto: marcador vazio no painel significa usar o marcador já selecionado no portal; não reintroduzir exigência de marcador digitado nem envio de `filter_marker` nesse cenário.
- Não adicionar `work/tce-extractor/.codex-live-pilot.py`, perfis Playwright, logs, HARs, traces, SQLite operacional ou outros dados privados ao Git.
- Não alterar regras jurídicas fora das regressões cobertas; não fazer refactors não relacionados.
- Cada tarefa segue RED → GREEN → refactor mínimo → testes → commit.

---

### Task 0: Congelar baseline atual e provar que o novo `main` está saudável

**Files:**
- Read only: `docs/notes/2026-09-17-portal-capture-launcher-fix-handoff.md`
- Read only: `work/tce-extractor/portable/extensao-complementar-ato/background/automation-controller.js`
- Read only: `work/tce-extractor/portable/extensao-complementar-ato/tests/automation-controller.test.mjs`
- Verify: `work/tce-extractor/verify-project.ps1`

**Interfaces:**
- Consumes: `main` contendo a correção `fa90605192d4ade824e0f71efbc45cfc4b34c588`.
- Produces: baseline conhecido antes de qualquer alteração v3; nenhuma modificação de produção.

- [ ] **Step 1: criar worktree a partir do `main` atual**

Use `superpowers:using-git-worktrees`. A branch da implementação deve partir do `origin/main` atual, não do commit antigo do plano.

Verificar:

```powershell
git fetch origin
git rev-parse origin/main
git merge-base --is-ancestor fa90605192d4ade824e0f71efbc45cfc4b34c588 origin/main
```

Expected: o terceiro comando retorna código 0.

- [ ] **Step 2: confirmar que o drift relevante está presente**

```powershell
git log --oneline --decorate -5
rg -n 'pilot without a typed marker locks the marker already selected in the portal' work/tce-extractor/portable/extensao-complementar-ato/tests/automation-controller.test.mjs
```

Expected: teste regressivo do marcador selecionado está presente.

- [ ] **Step 3: rodar o teste focal do controlador antes de tocar em v3**

```powershell
cd work/tce-extractor/portable/extensao-complementar-ato
node --test tests/automation-controller.test.mjs
```

Expected no baseline revisado: PASS. A contagem registrada no handoff anterior era 18 testes; nova contagem maior é aceitável se verde.

- [ ] **Step 4: concluir o gate que estava incompleto**

```powershell
cd work/tce-extractor
powershell -ExecutionPolicy Bypass -File .\verify-project.ps1
```

Expected: comando termina com exit code 0 e todos os estágios, inclusive PowerShell, exibem conclusão verde.

- [ ] **Step 5: confirmar descoberta Python ampla**

```powershell
python -m unittest discover -s . -p 'test_*.py' -q
```

Expected: 0 failures.

- [ ] **Step 6: registrar baseline local sem commit de código**

```powershell
git status --short
```

Expected: worktree limpa. Se o baseline falhar antes de qualquer mudança v3, interromper a implementação e tratar essa falha separadamente; não atribuí-la à fundamentação v3.

---

### Task 1: Fechar definitivamente o fallback legado de `fundamento_legal`

**Files:**
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/lib/matcher.js`
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/tests/matcher.test.mjs`

**Interfaces:**
- Consumes: `resolveLegalFoundation({ context, options })` existente.
- Produces: `rankPortalOptions()` retorna match bloqueado e `optionValue:null` sempre que `field === "fundamento_legal"` e não houver contexto.
- Produces: `legalDecision.decision_state === "CONTEXT_BLOCKED"` para ausência de contexto.

- [ ] **Step 1: escrever RED que reproduz o bug atual**

```js
test("fundamento legal nunca usa matcher legado sem LegalContext", () => {
  const result = rankPortalOptions({
    field: "fundamento_legal",
    documentaryValue: "Art. 8º da EC 20/1998",
    options: [
      { value: "legacy-20", label: "Civil - Artigo 8º da Emenda Constitucional nº 20/1998" },
    ],
    context: null,
  });

  assert.equal(result.kind, "pending");
  assert.equal(result.optionValue, null);
  assert.equal(result.optionLabel, null);
  assert.equal(result.legalDecision.status, "pending");
  assert.equal(result.legalDecision.decision_state, "CONTEXT_BLOCKED");
  assert.equal(result.legalDecision.reason, "LEGAL_CONTEXT_REQUIRED");
});
```

- [ ] **Step 2: confirmar RED**

```powershell
cd work/tce-extractor/portable/extensao-complementar-ato
node --test tests/matcher.test.mjs
```

Expected: novo teste falha porque o caminho atual ainda pode cair no matcher genérico quando `context` é nulo.

- [ ] **Step 3: implementar guard do campo inteiro**

Em `matcher.js`, a decisão deve ocorrer antes de qualquer ranking genérico:

```js
function missingLegalContextMatch(reason = "LEGAL_CONTEXT_REQUIRED") {
  return {
    kind: "pending",
    optionIndex: -1,
    optionValue: null,
    optionLabel: null,
    score: 0,
    reasons: [reason],
    legalDecision: {
      status: "pending",
      decision_state: "CONTEXT_BLOCKED",
      automatic: false,
      option_value: null,
      option_label: null,
      method: "none",
      confidence: 0,
      margin: 0,
      hard_conflict: false,
      reason,
      reasons: [reason],
      warnings: [],
      ranking: [],
    },
  };
}

export function rankPortalOptions({ field, documentaryValue, hints = {}, options = [], context = null }) {
  if (field === "fundamento_legal") {
    if (context === null || context === undefined) return missingLegalContextMatch();
    const legalDecision = resolveLegalFoundation({ context, options });
    // adaptar exclusivamente a decisão jurídica; não cair no matcher genérico
  }

  // somente campos não jurídicos seguem para o matcher genérico
}
```

- [ ] **Step 4: remover testes legados que fingem classificar fundamento sem contexto**

```powershell
rg -n 'field:\s*"fundamento_legal"' tests/matcher.test.mjs
```

Casos de peso/Dice/professor sem contexto devem migrar para os testes estruturais das Tasks 2–3; os casos sem contexto restantes devem testar somente fail-closed.

- [ ] **Step 5: rodar focal e commit**

```powershell
node --test tests/matcher.test.mjs
git add lib/matcher.js tests/matcher.test.mjs
git commit -m "fix: fail closed legal foundation without context"
```

---

### Task 2: Derivar assinatura jurídica do catálogo cru do portal

**Files:**
- Create: `work/tce-extractor/portable/extensao-complementar-ato/lib/catalog-option-signature.js`
- Create: `work/tce-extractor/portable/extensao-complementar-ato/tests/catalog-option-signature.test.mjs`
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/lib/portal-legal-crosswalk.js`

**Interfaces:**
- Consumes: `parseLegalReferencesV2(text)` e `normalizeLegalText(text)`.
- Produces: `buildCatalogOptionSignature(option, index)` com `{class_id, scope, modality, proportionality, teacher_rule, references, value, label, selectable}`.

- [ ] **Step 1: criar RED com `{value,label}` puro**

```js
import test from "node:test";
import assert from "node:assert/strict";
import { buildCatalogOptionSignature } from "../lib/catalog-option-signature.js";

test("detecta transição EC41 geral sem metadata artificial", () => {
  const result = buildCatalogOptionSignature({
    value: "general",
    label: "Civil - Artigo 6º, incisos I a IV e artigo 7º, ambos da Emenda Constitucional nº 41/2003 c/c o artigo 2º da Emenda Constitucional nº 47/2005",
  }, 0);
  assert.equal(result.class_id, "EC41_TRANSITION_GENERAL");
  assert.equal(result.scope, "civil");
  assert.equal(result.teacher_rule, false);
});

test("detecta regra docente por CF art. 40 § 5º", () => {
  const result = buildCatalogOptionSignature({
    value: "teacher",
    label: "Civil - Artigo 6º, incisos I a IV e artigo 7º, ambos da Emenda Constitucional nº 41/2003 c/c o artigo 40, § 5º, Constituição Federal e artigo 2º da Emenda Constitucional nº 47/2005",
  }, 0);
  assert.equal(result.class_id, "EC41_TRANSITION_TEACHER");
  assert.equal(result.teacher_rule, true);
});
```

No mesmo arquivo incluir casos explícitos para `EC47_ART3`, `EC41_ART6A_EC70`, `EC20_ART8`, CF art. 40 §1º III `a`, CF art. 40 §1º III `b`, opção militar e placeholder não selecionável.

- [ ] **Step 2: confirmar RED**

```powershell
node --test tests/catalog-option-signature.test.mjs
```

Expected: módulo ainda não existe.

- [ ] **Step 3: implementar assinatura estrutural**

```js
import { normalizeLegalText } from "./normalizer.js";
import { parseLegalReferencesV2 } from "./legal-reference-parser-v2.js";

function paragraphHas(reference, number) {
  return reference.paragraphs.some((item) => item.number === String(number));
}

function referenceHas(references, type, number, article, suffix = "") {
  return references.some((reference) => (
    reference.diploma_type === type
    && reference.diploma_number === String(number)
    && reference.article === String(article)
    && (reference.article_suffix ?? "") === suffix
  ));
}

function cf40Paragraph5(references) {
  return references.some((reference) => (
    reference.diploma_type === "cf"
    && reference.article === "40"
    && paragraphHas(reference, "5")
  ));
}
```

Derivar `class_id`, `scope`, `modality`, `proportionality` e `teacher_rule` das referências. A presença literal de `"paragrafo 5"` não pode ser requisito.

- [ ] **Step 4: remover duplicação de `portal-legal-crosswalk.js`**

Substituir `optionParts`/`inferClassId`/`candidateSignature` pela assinatura importada; `portal-legal-crosswalk.js` não deve manter uma segunda inferência textual divergente.

- [ ] **Step 5: rodar focal e commit**

```powershell
node --test tests/catalog-option-signature.test.mjs tests/legal-reference-parser-v2.test.mjs tests/portal-legal-crosswalk.test.mjs
git add lib/catalog-option-signature.js lib/portal-legal-crosswalk.js tests/catalog-option-signature.test.mjs
git commit -m "refactor: classify raw legal catalog structurally"
```

---

### Task 3: Corrigir crosswalks e produzir `LegalDecision v3`

**Files:**
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/lib/portal-legal-crosswalk.js`
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/lib/legal-foundation.js`
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/lib/automation-preflight.js`
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/tests/portal-legal-crosswalk.test.mjs`
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/tests/automation-preflight.test.mjs`
- Modify: `work/tce-extractor/tests/fixtures/legal-foundations-professores-v2.json`

**Interfaces:**
- Produces: `decision_state` em `AUTO_SELECTED | REVIEW_REQUIRED | TRUE_TIE | NO_COMPATIBLE_CANDIDATE | CONTEXT_BLOCKED | DOCUMENT_CONFLICT | CATALOG_UNRECOGNIZED`.
- Produces: `isAutomaticLegalDecision()` exige `AUTO_SELECTED` e `legal-foundation-v3`.

- [ ] **Step 1: tornar teste de catálogo black-box**

```js
const portalOptions = fixture.catalog.map(({ label }, index) => ({
  value: `catalog-${index}`,
  label,
}));
```

Nenhum teste E2E principal deve injetar `class_id`, `scope` ou `rule_id`.

- [ ] **Step 2: adicionar regressão Maria-like**

```js
const mariaLike = classifyPortalLegalFoundation({
  operativeText: "RESOLVE conceder aposentadoria voluntária por tempo de contribuição, com proventos integrais, a servidor ocupante do cargo de PROFESSOR, com fundamento no art. 7º, incisos I a III, §§ 2º e 4º, inciso I, § 5º, inciso I, e § 11 do art. 6º da ECE nº 20/2020.",
  cargo: "PROFESSOR",
  options: portalOptions,
});
assert.notEqual(mariaLike.class_id, "EC20_ART8");
assert.equal(mariaLike.class_id, "EC41_TRANSITION_GENERAL");
```

- [ ] **Step 3: adicionar regressão Joana-like**

```js
const joanaLike = classifyPortalLegalFoundation({
  operativeText: "RESOLVE conceder aposentadoria voluntária por tempo de contribuição com proventos integrais, nos termos do art. 6º, incisos I a IV, e art. 7º da EC nº 41/2003, art. 87 da LCE nº 308/2005, asseguradas as regras anteriores pelo art. 2º da ECE nº 20/2020.",
  cargo: "PROFESSOR",
  options: portalOptions,
});
assert.notEqual(joanaLike.reason, "family-conflict");
assert.ok(joanaLike.ranking.length > 0);
```

- [ ] **Step 4: confirmar RED**

```powershell
node --test tests/portal-legal-crosswalk.test.mjs
```

- [ ] **Step 5: remover conflito global EC + ECE**

Remover a regra genérica baseada apenas em `referenceTypes.has("ec") && referenceTypes.has("ece")`. Preservar conflitos específicos CF×CE, art. 6×6-A e discriminadores incompatíveis. ECE20 art. 2º é referência de preservação; ECE20 art. 7º continua crosswalk de transição.

- [ ] **Step 6: produzir estado explícito**

```js
const tied = second !== null && best.confidence === second.confidence;
let decisionState;
if (tied) decisionState = "TRUE_TIE";
else if (status === "selected") decisionState = "AUTO_SELECTED";
else if (status === "review") decisionState = "REVIEW_REQUIRED";
else decisionState = "NO_COMPATIBLE_CANDIDATE";
```

`emptyDecision()` recebe estado explícito e `rules_version`.

- [ ] **Step 7: endurecer `isAutomaticLegalDecision()`**

```js
return decision?.status === "selected"
  && decision?.decision_state === "AUTO_SELECTED"
  && decision?.rules_version === "legal-foundation-v3"
  && decision?.method !== "none"
  && decision?.hard_conflict !== true
  && Number.isFinite(decision?.confidence)
  && decision.confidence >= 0.90
  && Number.isFinite(decision?.margin)
  && decision.margin >= 0.12;
```

Adicionar teste de `status:selected` com `decision_state:REVIEW_REQUIRED`; deve ser recusado.

- [ ] **Step 8: rodar focal e commit**

```powershell
node --test tests/catalog-option-signature.test.mjs tests/portal-legal-crosswalk.test.mjs tests/legal-foundation.test.mjs tests/automation-preflight.test.mjs
git add lib tests/portal-legal-crosswalk.test.mjs tests/automation-preflight.test.mjs ../../tests/fixtures/legal-foundations-professores-v2.json
git commit -m "fix: add legal decision v3 crosswalk states"
```

---

### Task 4: Fazer o bump coerente para `legal-foundation-v3`

**Files:**
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/lib/legal-foundation.js`
- Modify: `work/tce-extractor/portable/app/local_service.py`
- Modify: `work/tce-extractor/portable/app/qualification.py`
- Modify: testes JS/Python que fixam `legal-foundation-v2`.

**Interfaces:**
- Produces: runtime JS, serviço Python, capabilities e qualification concordam em `legal-foundation-v3`.
- Old qualification/caches v2 tornam-se incompatíveis sem apagar PDF/OCR.

- [ ] **Step 1: RED de deriva de versão**

Em Python:

```python
self.assertEqual(expected_qualification_versions()["rules"], "legal-foundation-v3")
```

Adicionar caso que rejeita qualification com `legal-foundation-v2`.

- [ ] **Step 2: confirmar RED**

```powershell
cd work/tce-extractor
python -m unittest test_automation_qualification test_qa_workflow -q
```

- [ ] **Step 3: atualizar fontes de verdade**

```js
export const LEGAL_FOUNDATION_RULES_VERSION = "legal-foundation-v3";
```

```python
RULES_VERSION = "legal-foundation-v3"
```

`LEGAL_CONTEXT_VERSION` permanece `legal-context-v4`.

- [ ] **Step 4: migrar fixtures operacionais, preservando docs históricas**

```powershell
rg -n 'legal-foundation-v2' work/tce-extractor -g '*.js' -g '*.mjs' -g '*.py' -g '*.json'
```

Código/runtime/fixtures atuais migram; handoffs históricos não são reescritos.

- [ ] **Step 5: rodar gates e commit**

```powershell
python -m unittest test_automation_qualification test_automation_api test_qa_workflow -q
cd portable/extensao-complementar-ato
node --test tests/automation-controller.test.mjs tests/automation-preflight.test.mjs tests/bridge-client.test.mjs tests/service-worker.test.mjs
git add ../../app .
git commit -m "chore: bump legal foundation rules to v3"
```

O teste novo do marcador selecionado deve continuar verde; esta tarefa não deve alterar seu comportamento.

---

### Task 5: Implementar reconstrução pontual de `LegalContext` no serviço Python

**Files:**
- Modify: `work/tce-extractor/portable/app/legal_context.py`
- Modify: `work/tce-extractor/portable/app/analysis_pipeline.py`
- Modify: `work/tce-extractor/portable/app/local_service.py`
- Modify: `work/tce-extractor/test_legal_context.py`
- Modify: `work/tce-extractor/test_analysis_pipeline.py`
- Modify: `work/tce-extractor/test_automation_api.py`

**Interfaces:**
- Produces: `build_legal_context_record(..., process_key, interested_normalized) -> dict | None`.
- Produces: `upsert_legal_context_record(path, record, dataset_sha256) -> None` atômico.
- Produces: `rebuild_legal_context_from_root(root, dataset_sha256, process_key, interested_normalized) -> dict`.
- HTTP: `POST /api/v1/legal-context/rebuild` com `{process_key, interested_normalized}`.

- [ ] **Step 1: RED para gerar somente uma identidade**

```python
record = build_legal_context_record(
    manifest,
    checkpoint_with_two_people,
    page_texts,
    HASH,
    "102173/2026",
    "maria lucia do nascimento",
)
self.assertIsNotNone(record)
self.assertEqual(record["process_key"], "102173/2026")
self.assertEqual(record["interested_normalized"], "maria lucia do nascimento")
```

- [ ] **Step 2: RED para upsert preservando outros registros**

Criar sidecar com dois records; substituir apenas um e afirmar que o outro permanece semanticamente idêntico e `dataset_sha256` não muda.

- [ ] **Step 3: extrair builder unitário da lógica atual**

Reutilizar `_manifest_sources`, `_checkpoint_blocks` e `_record`; não duplicar parser/OCR.

- [ ] **Step 4: implementar upsert atômico**

Exigir schema 1 e hash compatível; substituir chave `(process_key, interested_normalized)`; escrever pelo caminho já atômico de `write_legal_contexts()`.

- [ ] **Step 5: reconstruir a partir de evidências locais**

`rebuild_legal_context_from_root()` reutiliza manifesto, checkpoint, cache de texto/OCR, geometry cache e PDF já adquirido. Não chama coleta global nem batch runner.

- [ ] **Step 6: RED da rota HTTP**

Cobrir:

```text
sidecar ausente + evidência válida -> 200 complete
evidência ausente -> DOCUMENT_EVIDENCE_MISSING
identidade fora do dataset -> IDENTITY_NOT_IN_DATASET
GET depois do rebuild -> record reconstruído com revision/rules v3
```

- [ ] **Step 7: implementar rota autenticada**

`POST /api/v1/legal-context/rebuild` usa mesma autenticação loopback do GET, canonicaliza identidade, valida dataset atual e retorna envelope `{api_version:1, context}`.

- [ ] **Step 8: rodar focal e commit**

```powershell
python -m unittest test_legal_context test_analysis_pipeline test_automation_api -q
git add portable/app/legal_context.py portable/app/analysis_pipeline.py portable/app/local_service.py test_legal_context.py test_analysis_pipeline.py test_automation_api.py
git commit -m "feat: rebuild legal context per identity"
```

---

### Task 6: Centralizar `LegalContext` no Service Worker

**Files:**
- Create: `work/tce-extractor/portable/extensao-complementar-ato/background/legal-context-resolver.js`
- Create: `work/tce-extractor/portable/extensao-complementar-ato/tests/legal-context-resolver.test.mjs`
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/lib/bridge-client.js`
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/tests/bridge-client.test.mjs`
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/background/service-worker.js`
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/tests/service-worker.test.mjs`

**Interfaces:**
- `bridge.rebuildLegalContext(identity) -> Promise<{api_version:1, context}>`.
- `createLegalContextResolver({ bridge, rulesVersion })` produz `ensureLegalContext({ identity, datasetSha256 })`.
- Resultado: `{status:"ready"|"rebuilt"|"blocked", source:"cache"|"sidecar"|"rebuilt"|null, reason:string|null, context:object|null}`.

- [ ] **Step 1: RED do bridge**

Exigir `POST /legal-context/rebuild`, body snake_case e validação do envelope.

- [ ] **Step 2: implementar `rebuildLegalContext()` usando request autenticado existente**

Não criar fetch paralelo sem auth.

- [ ] **Step 3: RED do resolver**

Cobrir:

```text
cache válido -> segundo ensure não consulta bridge
sidecar válido -> ready/sidecar
GET NOT_FOUND -> rebuild -> rebuilt
hash divergente -> rebuild e revalidação
rules_version antiga -> rebuild
resolution_status != complete -> blocked
operative_text vazio -> blocked
identity divergente -> blocked
rebuild falha -> blocked com reason tipado
```

- [ ] **Step 4: implementar `legal-context-resolver.js`**

Cache indexado por `processKey|interestedNormalized|datasetSha256|rulesVersion|contextRevision`. Validação mínima: schema 1, hash, identidade, complete, operative text, revision inteira e rules version exata.

- [ ] **Step 5: integrar ao `GET_MATCH`**

O painel não precisa enviar contexto. O worker resolve contexto e anexa à decisão:

```js
context_status: resolution.status,
context_source: resolution.source,
context_reason: resolution.reason,
```

Blocked chama o fail-closed da Task 1, nunca o matcher genérico.

- [ ] **Step 6: unificar automático e manual**

Remover chamada direta paralela a `activeBridge.getLegalContext()` no caminho automático; ambos usam o mesmo resolver.

- [ ] **Step 7: rodar focal e commit**

```powershell
node --test tests/legal-context-resolver.test.mjs tests/bridge-client.test.mjs tests/service-worker.test.mjs tests/automation-controller.test.mjs
git add background lib/bridge-client.js tests/legal-context-resolver.test.mjs tests/bridge-client.test.mjs tests/service-worker.test.mjs
git commit -m "refactor: centralize legal context in service worker"
```

---

### Task 7: Remover ownership do contexto do painel e adicionar barreira final de escrita

**Files:**
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/sidepanel/panel.js`
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/tests/panel.test.mjs`

**Interfaces:**
- `panel.getMatch(snapshot)` não chama `bridgeClient.getLegalContext()`.
- `applyPayload()` omite `fundamento_legal` quando `isAutomaticLegalDecision()` é falso, mesmo com `proposedValue` presente.

- [ ] **Step 1: RED provando que painel não busca contexto**

Mockar `getLegalContext()` para lançar `Error("panel must not fetch legal context")`; refresh/getMatch deve continuar funcionando.

- [ ] **Step 2: remover `contextPayload` de `getMatch(snapshot)`**

Manter identidade/snapshot/opções; o worker resolve contexto.

- [ ] **Step 3: RED da barreira de escrita**

```js
{
  field: "fundamento_legal",
  proposedValue: "dangerous-option",
  match: {
    legalDecision: {
      status: "review",
      decision_state: "REVIEW_REQUIRED",
      rules_version: "legal-foundation-v3",
      confidence: 0.89,
      margin: 0.20,
      hard_conflict: false,
      method: "rule",
    },
  },
}
```

`APPLY_FIELDS.fields` não pode conter `fundamento_legal`; outro campo seguro deve continuar presente.

- [ ] **Step 4: implementar defense-in-depth**

```js
if (row.field === "fundamento_legal" && !isAutomaticLegalDecision(row.match?.legalDecision)) {
  continue;
}
```

- [ ] **Step 5: adicionar positivo AUTO**

`AUTO_SELECTED`, v3, `confidence:0.94`, `margin:0.18` e opção existente deve incluir exatamente o `option_value` autorizado.

- [ ] **Step 6: rodar focal e commit**

```powershell
node --test tests/panel.test.mjs tests/service-worker.test.mjs tests/automation-controller.test.mjs
git add sidepanel/panel.js tests/panel.test.mjs
git commit -m "fix: guard legal foundation writes in panel"
```

---

### Task 8: Separar contexto, decisão e autorização na UI

**Files:**
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/sidepanel/panel-view.js`
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/sidepanel/panel.js`
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/tests/panel-view.test.mjs`
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/tests/panel.test.mjs`

**Interfaces:**
- `buildLegalDiagnostics()` expõe `contextStatus`, `contextSource`, `contextReason`, `decisionState`, `writeAllowed`, `confidence`, `margin`, `method`, `candidateLabel`.
- TRUE_TIE é o único estado mostrado como empate.

- [ ] **Step 1: RED dos estados**

```text
AUTO_SELECTED     -> seleção automática / writeAllowed=true
REVIEW_REQUIRED   -> revisão necessária / false
TRUE_TIE          -> empate real / false
CONTEXT_BLOCKED   -> contexto jurídico bloqueado / false
DOCUMENT_CONFLICT -> conflito documental / false
```

`confidence:0` deve aparecer como `0%`; somente null/undefined é “indisponível”.

- [ ] **Step 2: ajustar `buildLegalDiagnostics()`**

Usar `decision_state` explicitamente. Em REVIEW, label é “Candidato principal”, não “Opção sugerida segura”. Sem candidato utilizável: `candidateLabel:null` e “Proposta segura: nenhuma”.

- [ ] **Step 3: remover mapeamento visual `non-AUTO => tie`**

TRUE_TIE é a única origem de copy/estilo de empate.

- [ ] **Step 4: exibir contexto e autorização separadamente**

```text
Contexto jurídico: disponível | reconstruído | bloqueado
Origem: cache | sidecar | evidências locais
Regras: legal-foundation-v3
Fundamento legal: será preenchido | não será preenchido automaticamente
```

- [ ] **Step 5: rodar focal e commit**

```powershell
node --test tests/panel-view.test.mjs tests/panel.test.mjs
git add sidepanel/panel-view.js sidepanel/panel.js tests/panel-view.test.mjs tests/panel.test.mjs
git commit -m "feat: show explicit legal decision diagnostics"
```

---

### Task 9: End-to-end jurídico sem regredir o piloto atual

**Files:**
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/tests/service-worker.test.mjs`
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/tests/panel.test.mjs`
- Modify: `work/tce-extractor/test_automation_api.py`
- Verify: `work/tce-extractor/portable/extensao-complementar-ato/tests/automation-controller.test.mjs`
- Verify: `work/tce-extractor/verify-project.ps1`

**Interfaces:**
- E2E: `snapshot -> GET_MATCH -> ensureLegalContext -> legal-foundation-v3 -> painel -> APPLY_FIELDS`.
- Casos bloqueados preservam demais campos e omitem fundamento.
- Casos AUTO escrevem exatamente `option_value` do catálogo atual.
- Fluxo do marcador selecionado no portal permanece intacto.

- [ ] **Step 1: teste integrado de contexto reconstruído**

Assertar:

```text
getLegalContext -> 1 tentativa
rebuildLegalContext -> 1 tentativa
decision_state -> AUTO_SELECTED
context_status -> rebuilt
APPLY_FIELDS -> contém fundamento_legal exato
```

- [ ] **Step 2: teste integrado de rebuild impossível**

`DOCUMENT_EVIDENCE_MISSING` deve omitir somente fundamento e deixar demais campos elegíveis.

- [ ] **Step 3: regressão integrada Maria-like**

Catálogo cru; nunca propor/escrever `EC20_ART8`; resultado esperado conforme regra atual: `EC41_TRANSITION_GENERAL` quando AUTO.

- [ ] **Step 4: regressão integrada Joana-like**

EC41 arts. 6/7 + LCE 308 + ECE20 art. 2; sem `family-conflict` global; confidence/margin numéricos; rules v3.

- [ ] **Step 5: proteger explicitamente a regressão do marcador do piloto**

```powershell
node --test tests/automation-controller.test.mjs
```

O caso `pilot without a typed marker locks the marker already selected in the portal` deve continuar PASS. Se falhar após mudanças jurídicas, tratar como regressão da implementação e corrigir antes de seguir.

- [ ] **Step 6: rodar suíte JS completa três vezes**

```powershell
npm test
npm test
npm test
```

Expected: três execuções verdes. Não codificar retries de produção para mascarar flake de teste.

- [ ] **Step 7: rodar Python amplo e verificador**

```powershell
cd work/tce-extractor
python -m unittest discover -s . -p 'test_*.py' -q
powershell -ExecutionPolicy Bypass -File .\verify-project.ps1
git diff --check
```

Expected: todos verdes.

- [ ] **Step 8: validar pacote portátil**

Usar o gate de empacotamento vigente no repositório e comparar os artefatos empacotados relevantes com as fontes validadas. Não versionar cópias privadas de `outputs/`.

- [ ] **Step 9: commit de integração**

```powershell
git add work/tce-extractor
git status --short
```

Antes de commit, confirmar que `.codex-live-pilot.py`, perfis, logs, HARs, traces e dados privados não estão staged.

```bash
git commit -m "test: cover legal foundation v3 end to end"
```

---

### Task 10: Smoke real supervisionado usando o marcador já selecionado no portal

**Files:**
- Create: `docs/notes/2026-09-17-fundamento-legal-v3-validation.md`
- Read only unless smoke revelar bug: `docs/notes/2026-09-17-portal-capture-launcher-fix-handoff.md`
- Local-only optional helper: `work/tce-extractor/.codex-live-pilot.py` se existir no ambiente do operador; nunca versionar.

**Interfaces:**
- Produces evidência sanitizada de que opção exibida e `option_value` escrito coincidem.
- Não escolhe marcador automaticamente; usa marcador já selecionado pelo operador.
- Não considera sucesso sem releitura do campo e evidência local consistente.

- [ ] **Step 1: pré-condições humanas**

No portal autenticado, o operador:

```text
faz login manual
seleciona manualmente o marcador vigente
deixa o campo opcional #automation-marker vazio
mantém lista autenticada visível
```

A automação deve capturar `snapshot.marker` e travar o valor selecionado. Não enviar `filter_marker` só para reproduzir o marcador.

- [ ] **Step 2: garantir ausência de execução pendente antes do smoke**

Consultar os mecanismos locais já usados pelo projeto e confirmar que não há run/comando/confirmação pendente. O handoff anterior registrou `runs=0`, `events=0`, `commands=0`, `confirmed_acts=0`; não presumir que isso ainda vale sem conferir.

- [ ] **Step 3: selecionar três atos representativos**

Cobrir:

```text
1. ECE/RN 20/2020 art. 7º, professor, transição
2. EC41 arts. 6/7 com ECE20 art. 2º como preservação
3. um caso não-AUTO: REVIEW, TRUE_TIE ou CONTEXT_BLOCKED
```

- [ ] **Step 4: registrar diagnóstico sanitizado antes de preencher**

Para cada ato registrar somente:

```text
rules_version
context_status
context_source
resolution_status
decision_state
method
confidence
margin
class_id
option_label sanitizado
writeAllowed
marker label sanitizado, sem tokens/ids privados
```

Não registrar CPF, matrícula, cookies, tokens ou HTML privado bruto.

- [ ] **Step 5: executar “Preencher campos disponíveis” sob supervisão**

Nos AUTO, reler `<select>` e exigir valor atual exatamente igual a `legalDecision.option_value`. No caso não-AUTO, fundamento não muda enquanto os demais campos elegíveis podem ser preenchidos.

- [ ] **Step 6: não confundir preenchimento com envio**

Este smoke valida preenchimento/seleção. Qualquer envio/finalização real continua sujeito às travas e autorizações existentes; não promover automaticamente o smoke para submissão do ato.

- [ ] **Step 7: documentar resultado**

Criar `docs/notes/2026-09-17-fundamento-legal-v3-validation.md` com comandos, contagens, resultados sanitizados e limitações ambientais.

- [ ] **Step 8: commit somente da evidência sanitizada**

```bash
git add docs/notes/2026-09-17-fundamento-legal-v3-validation.md
git commit -m "docs: validate legal foundation v3"
```

---

### Task 11: Gate final e handoff de conclusão

**Files:**
- Verify: todo o worktree de implementação
- Modify somente se necessário: `docs/notes/2026-09-17-fundamento-legal-v3-validation.md`

**Interfaces:**
- Produces: branch pronta para review/merge, com baseline e regressões atuais preservados.

- [ ] **Step 1: rodar gate final em checkout limpo**

```powershell
cd work/tce-extractor/portable/extensao-complementar-ato
npm test
cd ../../..
python -m unittest discover -s . -p 'test_*.py' -q
powershell -ExecutionPolicy Bypass -File .\verify-project.ps1
git diff --check
```

Expected: todos os comandos verdes.

- [ ] **Step 2: confirmar regressões críticas individualmente**

```powershell
cd portable/extensao-complementar-ato
node --test tests/matcher.test.mjs tests/catalog-option-signature.test.mjs tests/portal-legal-crosswalk.test.mjs tests/legal-context-resolver.test.mjs tests/service-worker.test.mjs tests/panel.test.mjs tests/panel-view.test.mjs tests/automation-controller.test.mjs
```

Expected: PASS incluindo o teste do marcador já selecionado no portal.

- [ ] **Step 3: procurar resíduos de versão antiga e fallback proibido**

```powershell
cd ../../..
rg -n 'legal-foundation-v2' work/tce-extractor -g '*.js' -g '*.mjs' -g '*.py' -g '*.json'
rg -n 'field\s*===?\s*["'']fundamento_legal["'']' work/tce-extractor/portable/extensao-complementar-ato
```

Ocorrências de v2 em docs/handoffs históricos são permitidas; runtime atual não. Revisar manualmente todos os call sites do fundamento para confirmar ausência de fallback genérico.

- [ ] **Step 4: confirmar higiene do Git**

```powershell
git status --short
git ls-files work/tce-extractor/.codex-live-pilot.py
```

Expected: segundo comando sem saída; nenhum artefato privado staged.

- [ ] **Step 5: revisão final antes de merge**

Usar `superpowers:requesting-code-review` e depois `superpowers:verification-before-completion`. Não declarar concluído com base em testes antigos ou parciais.

---

## Final Acceptance Checklist

- [ ] Worktree parte de `main` contendo `fa90605192d4ade824e0f71efbc45cfc4b34c588` ou sucessor.
- [ ] Baseline pré-v3 completou `verify-project.ps1`, inclusive PowerShell.
- [ ] Regressão do marcador selecionado no portal permanece verde.
- [ ] `fundamento_legal` sem contexto retorna `optionValue=null` e nunca executa matcher legado.
- [ ] Painel não chama `getLegalContext()`; Service Worker é owner da resolução.
- [ ] `ensureLegalContext()` cobre cache → sidecar → rebuild pontual.
- [ ] Rebuild inválido bloqueia apenas fundamento.
- [ ] Catálogo cru `{value,label}` funciona sem metadata sintética.
- [ ] `§ 5º` é reconhecido estruturalmente.
- [ ] ECE20/2020 não vira EC20/1998 por similaridade.
- [ ] EC41 + ECE20 art. 2º não gera `family-conflict` global.
- [ ] `decision_state` diferencia AUTO, REVIEW, TRUE_TIE, BLOCKED e conflitos.
- [ ] `isAutomaticLegalDecision()` exige v3 + thresholds + AUTO_SELECTED.
- [ ] `applyPayload()` possui guard independente.
- [ ] UI não chama todo non-AUTO de empate.
- [ ] Qualification/capabilities/runtime concordam em `legal-foundation-v3`.
- [ ] PDFs/OCR válidos são reaproveitados; decisões v2 são recalculadas.
- [ ] Maria-like e Joana-like passam no catálogo cru e no E2E.
- [ ] `npm test` passa repetidamente.
- [ ] descoberta Python passa.
- [ ] `verify-project.ps1` e `git diff --check` passam.
- [ ] pacote portátil contém artefatos validados.
- [ ] smoke usa marcador selecionado manualmente e campo de marcador vazio.
- [ ] smoke prova correspondência decisão ↔ valor selecionado e ausência de escrita em não-AUTO.
- [ ] `.codex-live-pilot.py` e dados privados permanecem fora do Git.
