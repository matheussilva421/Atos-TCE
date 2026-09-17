# Fundamentação Legal v3 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Before implementation, use `superpowers:using-git-worktrees` and work outside `main`.

**Goal:** tornar `fundamento_legal` fail-closed, obrigatoriamente dependente de `LegalContext` válido, classificado pelo catálogo real do TCE/RN e protegido por uma segunda barreira antes de qualquer `APPLY_FIELDS`.

**Architecture:** o Service Worker passa a ser o único proprietário da aquisição do contexto jurídico por meio de `ensureLegalContext()`, com resolução em três níveis: cache válido, sidecar atual e reconstrução pontual. A classificação jurídica migra para `legal-foundation-v3`, transforma opções cruas `{value,label}` em assinaturas estruturadas e separa compatibilidade jurídica, crosswalk, hard rejects e score. O painel apenas consome a decisão; não busca contexto e não pode escrever fundamento sem `LegalDecision v3` automática.

**Tech Stack:** JavaScript ES modules, Node `node:test`, Chrome Extension Manifest V3, Python 3.14 `unittest`, serviço HTTP loopback autenticado, JSON sidecars, PowerShell para gates/empacotamento.

**Spec:** `docs/superpowers/specs/2026-09-17-fundamento-legal-v3-design.md`

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
- Não alterar regras jurídicas fora das regressões cobertas; não fazer refactors não relacionados.
- Cada tarefa segue RED → GREEN → refactor mínimo → testes → commit.

---

### Task 1: Fechar definitivamente o fallback legado de `fundamento_legal`

**Files:**
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/lib/matcher.js` (`rankPortalOptions`)
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/tests/matcher.test.mjs`

**Interfaces:**
- Consumes: `resolveLegalFoundation({ context, options })` existente.
- Produces: `rankPortalOptions()` retorna um match bloqueado e `optionValue:null` sempre que `field === "fundamento_legal"` e não houver contexto.
- Produces: `legalDecision.decision_state === "CONTEXT_BLOCKED"` para ausência de contexto.

- [ ] **Step 1: escrever o teste RED que reproduz o bug atual**

Adicionar em `tests/matcher.test.mjs`:

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

- [ ] **Step 2: rodar o teste focal e confirmar RED**

Run:

```powershell
cd work/tce-extractor/portable/extensao-complementar-ato
node --test tests/matcher.test.mjs
```

Expected: o caso novo falha porque hoje `rankPortalOptions()` só entra em `resolveLegalFoundation()` quando `context` não é nulo e, na ausência dele, cai no ranking genérico.

- [ ] **Step 3: implementar o guard antes de qualquer lógica genérica**

Em `matcher.js`, estruturar o início de `rankPortalOptions()` assim:

```js
function missingLegalContextMatch() {
  return {
    kind: "pending",
    optionIndex: -1,
    optionValue: null,
    optionLabel: null,
    score: 0,
    reasons: ["LEGAL_CONTEXT_REQUIRED"],
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
      reason: "LEGAL_CONTEXT_REQUIRED",
      reasons: ["LEGAL_CONTEXT_REQUIRED"],
      warnings: [],
      ranking: [],
    },
  };
}

export function rankPortalOptions({ field, documentaryValue, hints = {}, options = [], context = null }) {
  if (field === "fundamento_legal") {
    if (context === null || context === undefined) return missingLegalContextMatch();
    const legalDecision = resolveLegalFoundation({ context, options });
    // preservar aqui o adaptador contextual já existente
  }

  // somente campos não jurídicos chegam ao matcher genérico
}
```

Não deixar um `if (field === "fundamento_legal" && context != null)` seguido de fallback; a condição deve englobar todo o campo.

- [ ] **Step 4: migrar testes que documentam comportamento morto**

No próprio `matcher.test.mjs`, localizar casos que chamam `field:"fundamento_legal"` sem contexto para testar pesos de `professor`, `diploma`, Dice ou sinais legados. Eles não devem ser “consertados” adicionando contexto falso. Remover esses asserts do contrato público de `rankPortalOptions` e cobrir os comportamentos jurídicos equivalentes nas Tasks 2–3, no classificador v3.

Run:

```powershell
rg -n 'field:\s*"fundamento_legal"' tests/matcher.test.mjs
```

Expected após a limpeza: os casos remanescentes sem contexto verificam exclusivamente o fail-closed; classificação jurídica fica nos testes de `portal-legal-crosswalk`/assinatura de catálogo.

- [ ] **Step 5: rodar a suíte focal**

```powershell
node --test tests/matcher.test.mjs
```

Expected: PASS.

- [ ] **Step 6: commit**

```bash
git add work/tce-extractor/portable/extensao-complementar-ato/lib/matcher.js work/tce-extractor/portable/extensao-complementar-ato/tests/matcher.test.mjs
git commit -m "fix: fail closed legal foundation without context"
```

---

### Task 2: Derivar a classe jurídica do catálogo cru do portal

**Files:**
- Create: `work/tce-extractor/portable/extensao-complementar-ato/lib/catalog-option-signature.js`
- Create: `work/tce-extractor/portable/extensao-complementar-ato/tests/catalog-option-signature.test.mjs`
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/lib/portal-legal-crosswalk.js`

**Interfaces:**
- Consumes: `parseLegalReferencesV2(text)` e `normalizeLegalText(text)`.
- Produces: `buildCatalogOptionSignature(option, index) -> {class_id, scope, modality, proportionality, teacher_rule, references, value, label, selectable}`.
- `portal-legal-crosswalk.js` deixa de possuir `inferClassId()` textual próprio e passa a consumir a assinatura.

- [ ] **Step 1: criar testes RED com opções reais no formato `{value,label}`**

Criar `tests/catalog-option-signature.test.mjs` com pelo menos:

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

test("detecta regra docente por CF art. 40 § 5º, não pela palavra paragrafo", () => {
  const result = buildCatalogOptionSignature({
    value: "teacher",
    label: "Civil - Artigo 6º, incisos I a IV e artigo 7º, ambos da Emenda Constitucional nº 41/2003 c/c o artigo 40, § 5º, Constituição Federal e artigo 2º da Emenda Constitucional nº 47/2005",
  }, 0);
  assert.equal(result.class_id, "EC41_TRANSITION_TEACHER");
  assert.equal(result.teacher_rule, true);
});
```

Adicionar casos para `EC47_ART3`, `EC41_ART6A_EC70`, `EC20_ART8`, CF art. 40 §1º III `a` e `b`, opção militar e placeholder não selecionável.

- [ ] **Step 2: confirmar RED**

```powershell
node --test tests/catalog-option-signature.test.mjs
```

Expected: FAIL porque o módulo ainda não existe.

- [ ] **Step 3: implementar assinatura estruturada**

Criar `lib/catalog-option-signature.js`. A implementação deve inferir classes por referências parseadas, não por `label.includes("paragrafo 5")`. Estrutura mínima:

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

function inferStructuredClassId(references) {
  const ec41Transition = referenceHas(references, "ec", "41", "6")
    && referenceHas(references, "ec", "41", "7");
  if (ec41Transition) {
    return cf40Paragraph5(references)
      ? "EC41_TRANSITION_TEACHER"
      : "EC41_TRANSITION_GENERAL";
  }
  if (referenceHas(references, "ec", "47", "3")) return "EC47_ART3";
  if (referenceHas(references, "ec", "41", "6", "a")) return "EC41_ART6A_EC70";
  if (referenceHas(references, "ec", "20", "8")) return "EC20_ART8";
  return null;
}

export function buildCatalogOptionSignature(option, index = 0) {
  const value = option?.value ?? option?.label ?? "";
  const label = option?.label ?? value;
  const normalized = normalizeLegalText(label);
  const references = parseLegalReferencesV2(label);
  const selectable = option?.selectable !== false
    && Boolean(value)
    && !/^selecion(?:e|ar)/iu.test(String(label).trim());
  const classId = option?.class_id ?? option?.rule_id ?? inferStructuredClassId(references)
    ?? `CATALOG_OPTION_${index}`;
  return {
    ...option,
    index,
    value,
    label,
    selectable,
    class_id: classId,
    scope: option?.scope ?? (/\bmilitar\b/u.test(normalized) ? "military" : "civil"),
    teacher_rule: classId === "EC41_TRANSITION_TEACHER" || cf40Paragraph5(references),
    references,
  };
}
```

Completar no mesmo módulo a modalidade/proporcionalidade usando a lógica estrutural já existente em `candidateSignature`; não duplicar duas implementações.

- [ ] **Step 4: substituir `optionParts`/`inferClassId`/`candidateSignature` duplicados**

Em `portal-legal-crosswalk.js`, importar `buildCatalogOptionSignature` e fazer o ranking trabalhar com a assinatura retornada. Remover a decisão baseada em `label.includes("paragrafo 5")`.

- [ ] **Step 5: rodar testes**

```powershell
node --test tests/catalog-option-signature.test.mjs tests/legal-reference-parser-v2.test.mjs tests/portal-legal-crosswalk.test.mjs
```

Expected: PASS sem exigir `class_id` para os novos casos.

- [ ] **Step 6: commit**

```bash
git add work/tce-extractor/portable/extensao-complementar-ato/lib/catalog-option-signature.js work/tce-extractor/portable/extensao-complementar-ato/lib/portal-legal-crosswalk.js work/tce-extractor/portable/extensao-complementar-ato/tests/catalog-option-signature.test.mjs
git commit -m "refactor: classify raw legal catalog structurally"
```

---

### Task 3: Corrigir crosswalks e introduzir `LegalDecision v3`

**Files:**
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/lib/portal-legal-crosswalk.js`
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/lib/legal-foundation.js`
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/lib/automation-preflight.js`
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/tests/portal-legal-crosswalk.test.mjs`
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/tests/automation-preflight.test.mjs`
- Modify: `work/tce-extractor/tests/fixtures/legal-foundations-professores-v2.json`

**Interfaces:**
- Produces: `LegalDecision.decision_state` em `AUTO_SELECTED | REVIEW_REQUIRED | TRUE_TIE | NO_COMPATIBLE_CANDIDATE | CONTEXT_BLOCKED | DOCUMENT_CONFLICT | CATALOG_UNRECOGNIZED`.
- Produces: `isAutomaticLegalDecision()` exige também `decision_state === "AUTO_SELECTED"` e `rules_version === "legal-foundation-v3"`.
- Preserva `status: selected|review|pending` como compatibilidade temporária.

- [ ] **Step 1: tornar o teste do catálogo black-box**

No `portal-legal-crosswalk.test.mjs`, trocar a criação atual que injeta `class_id` e `scope` por:

```js
const portalOptions = fixture.catalog.map(({ label }, index) => ({
  value: `catalog-${index}`,
  label,
}));
```

O teste deve falhar se a produção depender de metadata sintética.

- [ ] **Step 2: adicionar regressão sanitizada ECE20/2020 (caso Maria)**

Adicionar caso com `operativeText` equivalente à resolução real, sem CPF/matrícula:

```js
const mariaLike = classifyPortalLegalFoundation({
  operativeText: "RESOLVE conceder aposentadoria voluntária por tempo de contribuição, com proventos integrais, a servidor ocupante do cargo de PROFESSOR, com fundamento no art. 7º, incisos I a III, §§ 2º e 4º, inciso I, § 5º, inciso I, e § 11 do art. 6º da ECE nº 20/2020.",
  cargo: "PROFESSOR",
  options: portalOptions,
});
assert.notEqual(mariaLike.class_id, "EC20_ART8");
assert.equal(mariaLike.class_id, "EC41_TRANSITION_GENERAL");
```

- [ ] **Step 3: adicionar regressão EC41 + ECE20 art. 2º (caso Joana)**

```js
const joanaLike = classifyPortalLegalFoundation({
  operativeText: "RESOLVE conceder aposentadoria voluntária por tempo de contribuição com proventos integrais, nos termos do art. 6º, incisos I a IV, e art. 7º da EC nº 41/2003, art. 87 da LCE nº 308/2005, asseguradas as regras anteriores pelo art. 2º da ECE nº 20/2020.",
  cargo: "PROFESSOR",
  options: portalOptions,
});
assert.notEqual(joanaLike.reason, "family-conflict");
assert.ok(joanaLike.ranking.length > 0);
```

- [ ] **Step 4: confirmar RED dos dois bugs**

```powershell
node --test tests/portal-legal-crosswalk.test.mjs
```

Expected: ao menos o caso EC41 + ECE20 art. 2º falha no guard global atual; o catálogo cru expõe qualquer dependência remanescente de `class_id`.

- [ ] **Step 5: remover o conflito global EC + ECE e manter conflitos reais**

Em `classifyPortalLegalFoundation()`, remover a condição genérica:

```js
referenceTypes.has("ec") && referenceTypes.has("ece")
```

Manter hard conflicts específicos, por exemplo CF × CE realmente incompatível e EC41 art. 6 × art. 6-A. ECE20 art. 2º deve ser tratado como referência de preservação; ECE20 art. 7º continua elegível ao crosswalk `ECE20_ART7_VOLUNTARY_TRANSITION`.

- [ ] **Step 6: produzir `decision_state` determinístico**

No retorno do classificador:

```js
const tied = second !== null && best.confidence === second.confidence;
let decisionState;
if (tied) decisionState = "TRUE_TIE";
else if (status === "selected") decisionState = "AUTO_SELECTED";
else if (status === "review") decisionState = "REVIEW_REQUIRED";
else decisionState = "NO_COMPATIBLE_CANDIDATE";
```

`emptyDecision()` deve aceitar o estado explícito em vez de deixar a UI inferir pelo score.

- [ ] **Step 7: endurecer o preflight**

Atualizar `isAutomaticLegalDecision(decision)` para exigir simultaneamente:

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

Adicionar RED/GREEN em `automation-preflight.test.mjs` para uma decisão `selected` porém `REVIEW_REQUIRED`: ela deve ser recusada.

- [ ] **Step 8: rodar focal**

```powershell
node --test tests/catalog-option-signature.test.mjs tests/portal-legal-crosswalk.test.mjs tests/legal-foundation.test.mjs tests/automation-preflight.test.mjs
```

Expected: PASS.

- [ ] **Step 9: commit**

```bash
git add work/tce-extractor/portable/extensao-complementar-ato/lib work/tce-extractor/portable/extensao-complementar-ato/tests/portal-legal-crosswalk.test.mjs work/tce-extractor/portable/extensao-complementar-ato/tests/automation-preflight.test.mjs work/tce-extractor/tests/fixtures/legal-foundations-professores-v2.json
git commit -m "fix: add legal decision v3 crosswalk states"
```

---

### Task 4: Fazer o bump coerente para `legal-foundation-v3`

**Files:**
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/lib/legal-foundation.js`
- Modify: `work/tce-extractor/portable/app/local_service.py`
- Modify: `work/tce-extractor/portable/app/qualification.py`
- Modify: testes JS/Python que fixam `legal-foundation-v2`, incluindo `tests/automation-controller.test.mjs`, `tests/automation-preflight.test.mjs`, `tests/bridge-client.test.mjs`, `tests/panel.test.mjs`, `tests/service-worker.test.mjs`, `test_automation_api.py`, `test_automation_qualification.py`, `portable/test_automation_recovery.py`, `portable/test_automation_integration.py` e `test_qa_workflow.py` quando aplicável.

**Interfaces:**
- Produces: runtime JS, serviço Python, capabilities e qualification concordam em `legal-foundation-v3`.
- Old qualification/caches v2 tornam-se incompatíveis por versão, sem apagar PDFs/OCR.

- [ ] **Step 1: criar/ajustar RED de deriva de versão**

Garantir que o teste de qualificação afirme:

```python
self.assertEqual(expected_qualification_versions()["rules"], "legal-foundation-v3")
```

E que um registro qualificado com `legal-foundation-v2` seja rejeitado como versão incompatível.

- [ ] **Step 2: confirmar RED**

```powershell
cd work/tce-extractor
python -m unittest test_automation_qualification test_qa_workflow -q
```

- [ ] **Step 3: atualizar as fontes de verdade**

Definir exatamente:

```js
export const LEGAL_FOUNDATION_RULES_VERSION = "legal-foundation-v3";
```

```python
RULES_VERSION = "legal-foundation-v3"
```

```python
"rules": "legal-foundation-v3"
```

Não incrementar `LEGAL_CONTEXT_VERSION`; ele permanece `legal-context-v4`.

- [ ] **Step 4: substituir fixtures operacionais v2 por v3**

Run:

```powershell
rg -n 'legal-foundation-v2' work/tce-extractor -g '*.js' -g '*.mjs' -g '*.py' -g '*.json'
```

Classificar cada ocorrência: código/runtime e fixtures atuais migram para v3; documentos/handoffs históricos não são reescritos.

- [ ] **Step 5: rodar gates de versão**

```powershell
python -m unittest test_automation_qualification test_automation_api test_qa_workflow -q
cd portable/extensao-complementar-ato
node --test tests/automation-controller.test.mjs tests/automation-preflight.test.mjs tests/bridge-client.test.mjs tests/service-worker.test.mjs
```

Expected: PASS.

- [ ] **Step 6: commit**

```bash
git add work/tce-extractor/portable/app work/tce-extractor/portable/extensao-complementar-ato work/tce-extractor/test_automation_api.py work/tce-extractor/test_automation_qualification.py work/tce-extractor/test_qa_workflow.py work/tce-extractor/portable/test_automation_recovery.py work/tce-extractor/portable/test_automation_integration.py
git commit -m "chore: bump legal foundation rules to v3"
```

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
- Produces: `build_legal_context_record(manifest, checkpoint, page_texts, dataset_sha256, process_key, interested_normalized) -> dict | None`.
- Produces: `upsert_legal_context_record(path, record, dataset_sha256) -> None` atômico.
- Produces: `rebuild_legal_context_from_root(root, dataset_sha256, process_key, interested_normalized) -> dict`.
- HTTP: `POST /api/v1/legal-context/rebuild` com JSON `{process_key, interested_normalized}`; resposta `{api_version:1, context:{...}}` igual ao GET.

- [ ] **Step 1: RED para geração de somente uma identidade**

Em `test_legal_context.py`, criar dois blocos e pedir apenas um:

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

- [ ] **Step 2: RED para upsert sem destruir outros registros**

Criar sidecar com dois records, substituir um, reler e afirmar que o outro é byte/semanticamente preservado e que `dataset_sha256` permanece o esperado.

- [ ] **Step 3: extrair o builder unitário da lógica já existente**

Em `legal_context.py`, reutilizar `_manifest_sources`, `_checkpoint_blocks` e `_record`; não duplicar parser/OCR. Implementar `build_legal_context_record()` filtrando por `process_key` e `interested_normalized` e retornando somente um record compatível.

- [ ] **Step 4: implementar upsert atômico**

`upsert_legal_context_record()` deve ler `fundamentos-contexto.v1.json` quando existir, exigir `schema_version == 1` e `dataset_sha256` igual, substituir apenas a chave `(process_key, interested_normalized)`, e gravar usando `write_legal_contexts()` para manter tempfile + `fsync` + `os.replace`.

- [ ] **Step 5: expor reconstrução a partir dos caches locais**

Em `analysis_pipeline.py`, criar `rebuild_legal_context_from_root()` reutilizando os mesmos arquivos/fontes já usados na publicação normal: manifesto, checkpoint, `_cached_page_texts(cache_path, geometry_cache_path, classified=classified)` e sidecar. Não iniciar batch runner nem coleta global.

Se as evidências locais forem insuficientes, levantar erro tipado que `local_service.py` converte em `DOCUMENT_EVIDENCE_MISSING`/`CONTEXT_INCOMPLETE`; não marcar o contexto como complete artificialmente.

- [ ] **Step 6: RED da rota HTTP**

Em `test_automation_api.py`, cobrir:

1. sidecar ausente + evidência local válida → POST rebuild retorna 200 e contexto complete;
2. evidência ausente → erro tipado e sidecar não é fabricado;
3. identidade fora do dataset → `IDENTITY_NOT_IN_DATASET`;
4. GET após rebuild devolve o record reconstruído com `context_revision` e `rules_version=legal-foundation-v3`.

Payload exato:

```json
{"process_key":"102173/2026","interested_normalized":"maria lucia do nascimento"}
```

- [ ] **Step 7: implementar `POST /api/v1/legal-context/rebuild`**

A rota deve usar a mesma autenticação loopback do serviço, canonicalizar processo/interessado, validar que a identidade pertence ao dataset atual, chamar `rebuild_legal_context_from_root`, injetar `context_revision` e `RULES_VERSION` no retorno e responder no mesmo envelope do GET.

- [ ] **Step 8: rodar Python focal**

```powershell
cd work/tce-extractor
python -m unittest test_legal_context test_analysis_pipeline test_automation_api -q
```

Expected: PASS.

- [ ] **Step 9: commit**

```bash
git add work/tce-extractor/portable/app/legal_context.py work/tce-extractor/portable/app/analysis_pipeline.py work/tce-extractor/portable/app/local_service.py work/tce-extractor/test_legal_context.py work/tce-extractor/test_analysis_pipeline.py work/tce-extractor/test_automation_api.py
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

Adicionar teste que exige:

```js
await bridge.rebuildLegalContext({
  processKey: "102173/2026",
  interestedNormalized: "maria lucia do nascimento",
});
```

E verifica `POST /legal-context/rebuild`, JSON snake_case e validação do envelope.

- [ ] **Step 2: implementar `rebuildLegalContext()`**

Usar o helper autenticado de request já existente no `bridge-client.js`; não criar fetch paralelo sem auth.

- [ ] **Step 3: escrever testes RED do resolver**

Cobrir:

```js
// 1. cache válido: getLegalContext chamado uma vez, segundo ensure usa cache
// 2. sidecar válido: status ready/source sidecar
// 3. GET LEGAL_CONTEXT_NOT_FOUND -> rebuild -> status rebuilt
// 4. dataset_sha256 divergente -> tentar rebuild e validar novamente
// 5. rules_version antiga -> tentar rebuild
// 6. resolution_status !== complete -> blocked
// 7. operative_text vazio -> blocked
// 8. identity divergente -> blocked
// 9. rebuild falha -> blocked com reason tipado
```

- [ ] **Step 4: implementar `legal-context-resolver.js`**

O cache deve ser indexado por:

```text
processKey | interestedNormalized | datasetSha256 | rulesVersion | contextRevision
```

A validação mínima exige `schema_version===1`, hash do dataset, identidade, `resolution_status==="complete"`, `operative_text.trim()`, `context_revision` inteiro e `rules_version` exata. Contexto inválido nunca é retornado como `ready`.

- [ ] **Step 5: RED no Service Worker**

Em `service-worker.test.mjs`, `GET_MATCH` sem `context` fornecido pelo painel deve chamar o resolver e entregar contexto ao ranker. Se o resolver devolver blocked, modalidade e demais campos continuam ranqueados, enquanto fundamento recebe `optionValue:null` e `decision_state=CONTEXT_BLOCKED`.

- [ ] **Step 6: integrar `ensureLegalContext()` em `getMatch`**

Remover o pressuposto de que `validated.context`/cache opcional vindo do painel é suficiente. O Service Worker resolve contexto para `fundamento_legal`, passa o `context` somente quando `ready/rebuilt` e anexa ao `legalDecision`:

```js
context_status: resolution.status,
context_source: resolution.source,
context_reason: resolution.reason,
```

Para `blocked`, chamar o caminho fail-closed da Task 1 e enriquecer o motivo, sem retornar ao matcher antigo.

- [ ] **Step 7: garantir que automação e manual usam a mesma resolução**

O fluxo automático que hoje chama `activeBridge.getLegalContext()` diretamente deve ser redirecionado ao mesmo resolver. Não manter duas políticas de validação.

- [ ] **Step 8: rodar focal**

```powershell
cd work/tce-extractor/portable/extensao-complementar-ato
node --test tests/legal-context-resolver.test.mjs tests/bridge-client.test.mjs tests/service-worker.test.mjs
```

Expected: PASS.

- [ ] **Step 9: commit**

```bash
git add work/tce-extractor/portable/extensao-complementar-ato/background work/tce-extractor/portable/extensao-complementar-ato/lib/bridge-client.js work/tce-extractor/portable/extensao-complementar-ato/tests/legal-context-resolver.test.mjs work/tce-extractor/portable/extensao-complementar-ato/tests/bridge-client.test.mjs work/tce-extractor/portable/extensao-complementar-ato/tests/service-worker.test.mjs
git commit -m "refactor: centralize legal context in service worker"
```

---

### Task 7: Remover ownership do contexto do painel e adicionar a barreira final de escrita

**Files:**
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/sidepanel/panel.js`
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/tests/panel.test.mjs`

**Interfaces:**
- `panel.getMatch(snapshot)` envia identidade/snapshot/opções, mas não chama `bridgeClient.getLegalContext()`.
- `applyPayload()` omite `fundamento_legal` quando `isAutomaticLegalDecision()` for falso, mesmo se `proposedValue` estiver preenchido.

- [ ] **Step 1: RED provando que o painel não busca contexto**

No mock de `bridgeClient`, fazer `getLegalContext()` lançar `AssertionError`/`Error("panel must not fetch legal context")`. Chamar refresh/getMatch e exigir sucesso: a busca deve ocorrer no Service Worker, não no painel.

- [ ] **Step 2: remover `contextPayload` de `getMatch(snapshot)`**

Eliminar o bloco que chama `state.bridgeClient?.getLegalContext(identity)`. O `GET_MATCH` continua levando a identidade; o worker é responsável por resolver contexto.

- [ ] **Step 3: RED da barreira de escrita**

Criar row de fundamento deliberadamente inconsistente:

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

Chamar “Preencher campos disponíveis” e afirmar que o payload `APPLY_FIELDS.fields` não contém `fundamento_legal`, enquanto outro campo seguro continua presente.

- [ ] **Step 4: implementar defense-in-depth em `applyPayload()`**

No loop de `state.rows`, antes de copiar `proposedValue`:

```js
if (row.field === "fundamento_legal" && !isAutomaticLegalDecision(row.match?.legalDecision)) {
  continue;
}
```

Não usar somente `row.kind`, `proposedValue`, `tie` ou presença de label como autorização jurídica.

- [ ] **Step 5: teste positivo**

Adicionar decisão `AUTO_SELECTED`, confidence `0.94`, margin `0.18`, v3 e opção existente; neste caso `fundamento_legal` deve entrar no payload exatamente com `option_value` autorizado.

- [ ] **Step 6: rodar focal**

```powershell
node --test tests/panel.test.mjs tests/service-worker.test.mjs
```

Expected: PASS.

- [ ] **Step 7: commit**

```bash
git add work/tce-extractor/portable/extensao-complementar-ato/sidepanel/panel.js work/tce-extractor/portable/extensao-complementar-ato/tests/panel.test.mjs
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
- `buildLegalDiagnostics(decision, documentaryValue)` expõe `contextStatus`, `contextSource`, `contextReason`, `decisionState`, `writeAllowed`, `confidence`, `margin`, `method`, `candidateLabel`.
- UI não converte toda decisão não automática em `tie`.

- [ ] **Step 1: RED para estados distintos**

Em `panel-view.test.mjs`, criar table test com:

```text
AUTO_SELECTED     -> "seleção automática" / writeAllowed=true
REVIEW_REQUIRED   -> "revisão necessária" / false
TRUE_TIE          -> "empate real" / false
CONTEXT_BLOCKED   -> "contexto jurídico bloqueado" / false
DOCUMENT_CONFLICT -> "conflito documental" / false
```

Também exigir que `confidence:0` apareça como `0%`, e apenas `undefined/null` apareçam como “indisponível”.

- [ ] **Step 2: ajustar `buildLegalDiagnostics()`**

A função deve ler `decision.decision_state` explicitamente. `classification.option_label` pode ser mostrado como “Candidato principal” em REVIEW, mas não como “Opção sugerida segura”. Quando não existir candidato utilizável, retornar `candidateLabel:null` e copy “Proposta segura: nenhuma”.

- [ ] **Step 3: remover a regra visual `non-AUTO => tie`**

Em `panel.js` e `panel-view.js`, substituir o mapeamento que força `kind="tie"` quando `!isAutomaticLegalDecision()`. TRUE_TIE deve ser o único estado jurídico que recebe apresentação de empate.

- [ ] **Step 4: adicionar diagnóstico do contexto**

Exibir a origem/estado vindos do resolver:

```text
Contexto jurídico: disponível | reconstruído | bloqueado
Origem: cache | sidecar | evidências locais
Regras: legal-foundation-v3
```

E, separadamente:

```text
Fundamento legal: será preenchido
```

ou

```text
Fundamento legal: não será preenchido automaticamente
Motivo: <context_reason ou razão da decisão>
```

- [ ] **Step 5: rodar UI focal**

```powershell
node --test tests/panel-view.test.mjs tests/panel.test.mjs
```

Expected: PASS.

- [ ] **Step 6: commit**

```bash
git add work/tce-extractor/portable/extensao-complementar-ato/sidepanel/panel-view.js work/tce-extractor/portable/extensao-complementar-ato/sidepanel/panel.js work/tce-extractor/portable/extensao-complementar-ato/tests/panel-view.test.mjs work/tce-extractor/portable/extensao-complementar-ato/tests/panel.test.mjs
git commit -m "feat: show explicit legal decision diagnostics"
```

---

### Task 9: End-to-end, regressões reais sanitizadas e gates do pacote

**Files:**
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/tests/service-worker.test.mjs`
- Modify: `work/tce-extractor/portable/extensao-complementar-ato/tests/panel.test.mjs`
- Modify: `work/tce-extractor/test_automation_api.py`
- Modify: `work/tce-extractor/test_real_portal_session.py` somente se necessário para validar o contrato sanitizado, sem armazenar PII.
- Modify: `work/tce-extractor/tests/fixtures/real-portal-observation-form.json` somente se uma nova observação sanitizada alterar o contrato estrutural permitido.
- Verify: `work/tce-extractor/verify-project.ps1`
- Verify: scripts de pacote/auditoria já existentes.

**Interfaces:**
- E2E simula `snapshot -> GET_MATCH -> ensureLegalContext -> legal-foundation-v3 -> painel -> APPLY_FIELDS`.
- Casos bloqueados preservam os demais campos e omitem fundamento.
- Casos AUTO escrevem exatamente o `option_value` do catálogo corrente.

- [ ] **Step 1: criar teste integrado de contexto reconstruído**

Simular sidecar ausente, bridge rebuild bem-sucedido e decisão AUTO. Assertar:

```text
bridge.getLegalContext      -> 1 tentativa
bridge.rebuildLegalContext  -> 1 tentativa
fundamento legal decision   -> AUTO_SELECTED
context_status              -> rebuilt
APPLY_FIELDS                -> contém fundamento_legal
```

- [ ] **Step 2: criar teste integrado de reconstrução impossível**

Simular rebuild `DOCUMENT_EVIDENCE_MISSING`. Assertar:

```text
modalidade/data/cargo/etc. -> continuam no payload quando disponíveis
fundamento_legal           -> ausente
legalDecision              -> CONTEXT_BLOCKED
```

- [ ] **Step 3: criar regressão integrada Maria-like**

Usar contexto ECE20/2020 e catálogo cru. Assertar que nenhuma camada propõe/escreve `EC20_ART8` e que a opção final, quando AUTO, corresponde à `EC41_TRANSITION_GENERAL` derivada do catálogo.

- [ ] **Step 4: criar regressão integrada Joana-like**

Usar EC41 arts. 6/7 + LCE 308 + ECE20 art. 2. Assertar ausência de `family-conflict`, `confidence`/`margin` numéricos, método diferente de `none` quando houver candidato e `rules_version=v3`.

- [ ] **Step 5: rodar suíte JS completa três vezes**

```powershell
cd work/tce-extractor/portable/extensao-complementar-ato
npm test
npm test
npm test
```

Expected: três execuções verdes. Se o flake histórico de confirmação automática reaparecer, não mascarar com retry no código de produção; isolar/corrigir o teste separadamente antes de aceitar o gate.

- [ ] **Step 6: rodar suíte Python ampla**

```powershell
cd work/tce-extractor
python -m unittest discover -s . -p 'test_*.py' -q
```

Expected: 0 failures; skips ambientais documentados são permitidos apenas se já previstos pela suíte.

- [ ] **Step 7: rodar verificador e auditoria de diff**

```powershell
powershell -ExecutionPolicy Bypass -File .\verify-project.ps1
git diff --check
git status --short
```

Expected: todos os stages do verificador verdes; `git diff --check` sem saída.

- [ ] **Step 8: validar pacote portátil**

Executar o gate de empacotamento já adotado pelo repositório e confirmar que o ZIP/pacote contém os arquivos modificados de extensão/serviço. Não validar apenas o checkout: comparar hashes/contents dos artefatos empacotados relevantes.

- [ ] **Step 9: commit de integração**

```bash
git add work/tce-extractor
git commit -m "test: cover legal foundation v3 end to end"
```

---

### Task 10: Smoke test real supervisionado e evidência de conclusão

**Files:**
- Create: `docs/notes/2026-09-17-fundamento-legal-v3-validation.md`
- No production code should be changed in this task unless the smoke exposes a reproducible defect, in which case return to RED/GREEN in the task responsável.

**Interfaces:**
- Produces: evidência sanitizada de que o fundamento exibido e o `option_value` escrito são o mesmo valor do catálogo real.
- Não produz envio/finalização automática sem autorização humana já exigida pelo fluxo existente.

- [ ] **Step 1: selecionar três atos representativos**

Usar sessão real supervisionada com login humano, cobrindo:

1. ECE/RN 20/2020 art. 7º, professor, transição;
2. EC 41/2003 arts. 6º/7º com cláusula ECE20 art. 2º;
3. caso não-AUTO (REVIEW/TRUE_TIE/CONTEXT_BLOCKED) para provar que fundamento fica intacto.

- [ ] **Step 2: antes de preencher, registrar somente evidência sanitizada**

Para cada ato registrar no relatório:

```text
rules_version
context_status/context_source
resolution_status
decision_state
method
confidence
margin
class_id
option_label sanitizado
writeAllowed
```

Não registrar CPF, matrícula, token, cookie ou HTML privado bruto.

- [ ] **Step 3: executar “Preencher campos disponíveis” sob supervisão**

Nos casos AUTO, verificar por releitura do `<select>` que o valor corrente é exatamente `legalDecision.option_value`. No caso não-AUTO, verificar que o valor do fundamento não mudou enquanto os outros campos elegíveis puderam ser preenchidos.

- [ ] **Step 4: documentar resultado**

Criar `docs/notes/2026-09-17-fundamento-legal-v3-validation.md` com comandos, contagens dos gates, três resultados sanitizados e qualquer limitação ambiental.

- [ ] **Step 5: gate final**

```powershell
cd work/tce-extractor/portable/extensao-complementar-ato
npm test
cd ../../..
python -m unittest discover -s . -p 'test_*.py' -q
git diff --check
```

Expected: verde antes de declarar a correção concluída.

- [ ] **Step 6: commit da evidência**

```bash
git add docs/notes/2026-09-17-fundamento-legal-v3-validation.md
git commit -m "docs: validate legal foundation v3"
```

---

## Final Acceptance Checklist

A implementação só pode ser marcada concluída quando todos os itens abaixo estiverem comprovados por testes ou smoke supervisionado:

- [ ] `fundamento_legal` sem contexto retorna `optionValue=null` e nunca executa matcher legado.
- [ ] O painel não chama `getLegalContext()`; o Service Worker é o owner exclusivo da resolução.
- [ ] `ensureLegalContext()` cobre cache → sidecar → rebuild pontual.
- [ ] Rebuild inválido bloqueia apenas fundamento.
- [ ] Catálogo cru `{value,label}` funciona sem `class_id`, `scope` ou `rule_id` sintéticos.
- [ ] `§ 5º` é reconhecido estruturalmente.
- [ ] ECE20/2020 não vira EC20/1998 por Dice/similaridade.
- [ ] EC41 + ECE20 art. 2º não gera `family-conflict` global.
- [ ] `decision_state` diferencia AUTO, REVIEW, TRUE_TIE, BLOCKED e conflitos.
- [ ] `isAutomaticLegalDecision()` exige v3 + thresholds + estado AUTO.
- [ ] `applyPayload()` possui guard independente para fundamento.
- [ ] UI não chama todo non-AUTO de “empate”.
- [ ] Qualification/capabilities/runtime concordam em `legal-foundation-v3`.
- [ ] PDFs/OCR válidos são reaproveitados; decisões v2 são recalculadas.
- [ ] regressões Maria-like e Joana-like passam no catálogo cru e no E2E.
- [ ] `npm test` passa repetidamente.
- [ ] `python -m unittest discover -s . -p 'test_*.py' -q` passa.
- [ ] `verify-project.ps1` e `git diff --check` passam.
- [ ] pacote portátil contém os artefatos validados.
- [ ] smoke real demonstra correspondência entre decisão exibida e valor realmente selecionado, e demonstra ausência de escrita em caso não-AUTO.
