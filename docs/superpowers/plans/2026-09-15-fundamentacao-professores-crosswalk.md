# Fundamentação Legal de Professores — Crosswalk para o Catálogo da Área Restrita — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Before implementation, use `superpowers:using-git-worktrees` and work outside `main`.

**Goal:** substituir o matching jurídico excessivamente literal/fuzzy atual por um classificador especializado capaz de mapear a fundamentação documental de atos de aposentadoria de professores para a opção mais adequada do catálogo fechado da Área Restrita do TCE-RN, preservando similaridade quando a resolução usa normas diferentes das opções cadastradas no portal.

**Architecture:** separar o problema em quatro camadas: (1) extração estruturada das referências legais da resolução; (2) construção de um perfil previdenciário funcional do ato; (3) crosswalk semântico entre regras documentais modernas/estaduais e classes legadas do catálogo do portal; e (4) ranking com confiança, margem e explicações auditáveis. A resolução continua sendo a fonte documental; o resultado do portal é uma classificação cadastral e não uma reescrita do fundamento jurídico.

**Tech Stack:** JavaScript ES modules/Node test runner na extensão; Python no serviço local; Chrome extension; fixtures JSON; automação já existente do projeto.

## Global Constraints

- Repositório: `matheussilva421/Atos-TCE`.
- Trabalhar em worktree/branch dedicada, sugestão: `codex/fundamentacao-professores-crosswalk-v2`.
- Não alterar a semântica dos demais campos (`modalidade`, DOE, cargo, matrícula etc.) salvo quando necessário para fornecer sinais ao novo classificador.
- O universo prioritário é **aposentadoria de professores**, especialmente: voluntária por tempo de contribuição com proventos integrais; voluntária com proventos proporcionais; invalidez/incapacidade permanente.
- `cargo=Professor` é contexto, não fundamento decisório: não inferir `CF art. 40, §5º` apenas pelo cargo.
- **Similaridade é requisito funcional.** Não exigir igualdade literal entre resolução administrativa e opção do portal.
- O sistema deve permitir crosswalk entre diplomas diferentes quando juridicamente/cadastralmente previsto, por exemplo `ECE 20/2020 -> opção histórica EC 41/2003 + EC 47/2005`.
- Remover a regra global “ECE e EC são incompatíveis” do caminho de classificação cadastral; manter conflitos documentais reais detectáveis dentro da própria resolução.
- Distinguir `proventos integrais` de `integralidade`; distinguir `proventos proporcionais` de base de cálculo por média.
- Preservar separadamente `documentary_foundation` e `portal_classification`.
- O texto lexical nunca deve ser o principal sinal; Dice/fuzzy textual só pode desempatar candidatos semanticamente compatíveis.
- Opção civil nunca pode perder para opção militar em processos deste escopo; incompatibilidade civil/militar é hard reject.
- Empate, baixa confiança, margem pequena ou contradição devem bloquear preenchimento automático do fundamento e manter revisão manual.
- Nenhuma alteração pode reduzir as validações de identidade, hash, catálogo atual ou contexto documental já existentes.
- Não criar motor universal de Direito Previdenciário. Implementar somente o necessário para o catálogo real da Área Restrita e os tipos de atos de professor em análise.
- TDD obrigatório: cada comportamento novo nasce em teste RED, depois implementação mínima GREEN, depois refactor.
- Commits pequenos e temáticos.
- Antes de habilitar envio real com `legal-foundation-v2`, executar regressão completa JS + Python + smoke do pacote portátil.

---

# Functional Specification

## 1. Problema de negócio

A Área Restrita não recebe texto livre de fundamento legal. Ela expõe um `select` com uma taxonomia fechada e em parte histórica. A resolução administrativa do processo pode usar fundamento mais novo ou estadual e, ainda assim, precisar ser classificada em uma opção legada do catálogo.

Exemplo real que deve orientar a implementação:

```text
RESOLVE conceder aposentadoria voluntária por tempo de contribuição,
com proventos integrais, a PROFESSOR PERMANENTE (...),
com fundamento no art. 7º, incisos I a III, §§ 2º e 4º, inciso I,
§ 5º, inciso I, e § 11 do art. 6º da Emenda Constitucional Estadual nº 20/2020 (...)
```

Essa resolução não possui necessariamente uma opção textual idêntica no portal. O classificador deve entender o **perfil funcional** do ato e encontrar a classe cadastral mais próxima, sem fingir que o fundamento documental é outro.

## 2. Famílias prioritárias

### `PROF_VOLUNTARIA_TC_INTEGRAL`

Sinais principais:

```text
aposentadoria voluntária
+ tempo de contribuição
+ proventos integrais
```

Sinais auxiliares possíveis: regra de transição, integralidade, paridade, EC 41/2003, EC 47/2005, ECE 20/2020, CF art. 40 §5º explicitamente citado.

### `PROF_VOLUNTARIA_TC_PROPORCIONAL`

Sinais principais:

```text
aposentadoria voluntária
+ tempo de contribuição
+ proventos proporcionais
```

Não inferir automaticamente artigo/alínea específica apenas pela palavra `proporcionais`; usar referências documentais + crosswalk.

### `PROF_INVALIDEZ_INCAPACIDADE`

Equivalência terminológica de família, preservando a época/regime:

```text
aposentadoria por invalidez
~ aposentadoria por incapacidade permanente
```

Subcaracterísticas independentes:

```text
proventos: integrais | proporcionais | desconhecido
base: remuneração | média | desconhecida
paridade: sim | não | desconhecida
```

A palavra `professor` não pode redirecionar uma aposentadoria por invalidez/incapacidade para uma regra de aposentadoria voluntária docente.

## 3. Catálogo civil observado na Área Restrita

O código deve continuar lendo `option.value` e `option.label` diretamente do portal. Os textos abaixo são assinaturas de referência/fixtures, nunca IDs persistentes hardcoded.

```text
Civil - Artigo 29, inciso I, alínea "b", da Constituição Estadual.
Civil - Artigo 29, inciso III, alínea "a", da Constituição Estadual.
Civil - Artigo 29, inciso III, alínea "b", da Constituição Estadual.
Civil - Artigo 29, inciso III, alínea "c", da Constituição Estadual.
Civil - Artigo 29, inciso III, alínea "d", da Constituição Estadual.
Civil - Artigo 40, § 1º, inciso I, da Constituição Federal
Civil - Artigo 40, § 1º, inciso II, da Constituição Federal
Civil - Artigo 40, § 1º, inciso III, alínea "a", da Constituição Federal
Civil - Artigo 40, § 1º, inciso III, alínea "b", da Constituição Federal
Civil - Artigo 6º, incisos I a IV e artigo 7º, ambos da Emenda Constitucional nº 41/2003 c/c o artigo 2º da Emenda Constitucional nº 47/2005
Civil - Artigo 6º, incisos I a IV e artigo 7º, ambos da Emenda Constitucional nº 41/2003 c/c o artigo 40, § 5º, Constituição Federal e artigo 2º da Emenda Constitucional nº 47/2005
Civil - Artigo 3º, incisos I a III e parágrafo único, da Emenda Constitucional nº 47/2005
Civil - Artigo 6º-A, parágrafo único, da Emenda Constitucional nº 41/2003, com redação dada pela Emenda Constitucional nº 70/2012
Civil - Artigo 40, §1º, inciso III, alínea "a", combinado com o §5º, da Constituição Federal
Civil - Art. 40, §1º combinado com o §4º, II da Constituição Federal e o art. 1º, II, da Lei Complementar nº 51/1985
Civil - Artigo 2º da Emenda Constitucional nº 41/2003
Civil - Artigo 8º, incisos I e II, §1º, alíneas "a" e "b", da Emenda Constitucional nº 20/1998
Civil - Art. 1º, inciso I, da Lei Complementar Nacional nº 51/85
```

O catálogo também contém opções militares. Neste projeto, elas devem ser reconhecidas apenas para exclusão (`scope=military`) e nunca escolhidas para registros civis de professor.

## 4. Modelo funcional obrigatório

Criar uma representação interna estável:

```js
/**
 * @typedef {Object} RetirementLegalProfile
 * @property {'civil'|'military'|'unknown'} scope
 * @property {'voluntary_contribution'|'invalidity_permanent_disability'|'other'|'unknown'} modality
 * @property {'integral'|'proportional'|'unknown'} proportionality
 * @property {'remuneration'|'average'|'unknown'} calculation_basis
 * @property {'yes'|'no'|'unknown'} parity
 * @property {boolean} professor_context
 * @property {boolean} professor_rule_explicit
 * @property {boolean|'unknown'} transition_rule
 * @property {LegalReferenceV2[]} references
 * @property {string[]} evidence
 */
```

`professor_context=true` pode vir de cargo/documento; `professor_rule_explicit=true` somente quando o fundamento/documento contiver sinal jurídico específico de regra docente.

## 5. Referência legal estruturada v2

Adotar estrutura capaz de representar múltiplos parágrafos/incisos/alíneas:

```js
/**
 * @typedef {Object} LegalReferenceV2
 * @property {'cf'|'ce'|'ec'|'ece'|'lc'|'lce'|'lei'|'unknown'} diploma_type
 * @property {string|null} diploma_number
 * @property {string|null} diploma_year
 * @property {string|null} article
 * @property {string|null} article_suffix
 * @property {Array<{number:string,incisos:string[],alineas:string[],items:string[]}>} paragraphs
 * @property {string[]} incisos
 * @property {string[]} alineas
 * @property {string[]} items
 * @property {string} raw
 */
```

O parser deve representar corretamente, no mínimo:

```text
art. 7º, incisos I a III, §§ 2º e 4º, inciso I, § 5º, inciso I,
e § 11 do art. 6º da ECE nº 20/2020
```

sem reduzir tudo ao primeiro parágrafo encontrado.

## 6. Separação documental x cadastral

A decisão deve manter dois conceitos independentes:

```js
{
  documentary_foundation: {
    operative_text,
    references,
    profile,
    citations
  },
  portal_classification: {
    option_value,
    option_label,
    class_id,
    method,
    confidence,
    margin,
    status,
    reasons,
    alternatives
  }
}
```

A resolução continua sendo a fonte documental. A opção do portal é classificação cadastral.

## 7. Política de similaridade jurídica

A `similarity` deve continuar existindo, mas deixar de ser principalmente lexical.

### Ordem de decisão

1. Hard rejects: civil x militar; modalidade incompatível; discriminador jurídico incompatível quando explicitamente presente.
2. Match de classe/crosswalk declarado.
3. Compatibilidade funcional: modalidade, proporcionalidade, base de cálculo, paridade, regime transitório.
4. Referências normativas estruturadas.
5. Contexto de professor como sinal auxiliar.
6. Similaridade lexical apenas como desempate residual.

### Regras fundamentais

- `cargo=Professor` sozinho **não** adiciona CF art. 40 §5º.
- `proventos integrais` **não** significa automaticamente integralidade.
- `proventos proporcionais` **não** significa automaticamente cálculo por média.
- `invalidez/incapacidade` não deve competir com regra voluntária apenas porque o servidor é professor.
- ECE 20/2020 pode mapear para classe histórica EC41/EC47 se houver crosswalk semântico declarado.
- EC x ECE não é conflito cadastral por si só; conflito documental real dentro da resolução continua bloqueando.
- Mesmo diploma + artigo diferente sem crosswalk não deve ganhar AUTO por Dice lexical.
- Alínea `a` e `b`, quando distinguem opções do catálogo, são discriminadores fortes.

## 8. Confidence e margin

Além do score, calcular:

```text
confidence = qualidade absoluta do melhor candidato
margin = confidence(top1) - confidence(top2)
```

Política inicial sugerida (calibrar com corpus real):

```text
AUTO:   confidence >= 0.90 e margin >= 0.12, sem hard reject/contradição
REVIEW: confidence >= 0.70, ou margin insuficiente
PENDING: sem candidato semanticamente compatível / conflito / dados insuficientes
```

Não congelar thresholds sem validação do corpus real. O critério de segurança é **falsos AUTO = 0** no corpus de piloto.

---

# File Structure

## Criar

```text
work/tce-extractor/portable/extensao-complementar-ato/lib/legal-reference-parser-v2.js
work/tce-extractor/portable/extensao-complementar-ato/lib/retirement-legal-profile.js
work/tce-extractor/portable/extensao-complementar-ato/lib/portal-legal-crosswalk.js
work/tce-extractor/portable/extensao-complementar-ato/tests/legal-reference-parser-v2.test.mjs
work/tce-extractor/portable/extensao-complementar-ato/tests/retirement-legal-profile.test.mjs
work/tce-extractor/portable/extensao-complementar-ato/tests/portal-legal-crosswalk.test.mjs
work/tce-extractor/tests/fixtures/legal-foundations-professores-v2.json
docs/notes/2026-09-15-fundamentacao-professores-v2-validation.md
docs/notes/2026-09-15-fundamentacao-professores-v2-handoff.md
```

## Modificar

```text
work/tce-extractor/portable/extensao-complementar-ato/lib/legal-foundation.js
work/tce-extractor/portable/extensao-complementar-ato/lib/normalizer.js
work/tce-extractor/portable/extensao-complementar-ato/lib/matcher.js
work/tce-extractor/portable/extensao-complementar-ato/lib/automation-preflight.js
work/tce-extractor/portable/extensao-complementar-ato/background/service-worker.js
work/tce-extractor/portable/extensao-complementar-ato/sidepanel/panel.js
work/tce-extractor/portable/extensao-complementar-ato/sidepanel/panel-view.js
work/tce-extractor/portable/app/local_service.py
work/tce-extractor/portable/app/qualification.py
work/tce-extractor/empacotar-extensao-complementar-ato.ps1
work/tce-extractor/empacotar-coletor-portatil.ps1
work/tce-extractor/package_complete_archive.py
work/tce-extractor/package_qa_release.ps1
work/tce-extractor/portable/app/package_audit.py
work/tce-extractor/verify_qa_release.py
```

---

# Implementation Tasks

## Task 0 — Baseline, worktree e regressões RED

1. Atualizar `main`, registrar HEAD/status e criar worktree/branch dedicada.
2. Rodar suites JS/Python atuais e registrar baseline.
3. Escrever testes RED para os bugs/limitações obrigatórios:
   - ECE20 professor não pode virar `family-conflict` só porque portal usa EC41/EC47;
   - cargo Professor não inventa §5º;
   - integral não implica integralidade;
   - invalidez/incapacidade não deve ser classificada como voluntária docente;
   - CF art. 40 §1º III `a` não pode casar com `b`;
   - `EC20/98` deve normalizar para 1998, não 2098;
   - mesmo diploma + artigo diferente sem crosswalk não pode virar AUTO apenas por similaridade lexical.
4. Rodar os testes e confirmar RED comportamental real.
5. Commit: `test: reproduce teacher legal crosswalk failures`.

## Task 1 — Parser jurídico v2

**Objetivo:** extrair referências legais estruturadas sem perder múltiplos parágrafos/incisos/alíneas.

Implementar `parseLegalReferencesV2(text)` em `legal-reference-parser-v2.js`.

Cobertura mínima:

```text
EC/ECE/CF/CE
LC/LCE/Lei
artigo + sufixo
caput
§ / §§ / parágrafo único
inciso(s), inclusive romano e intervalos
alínea(s)
item(ns)
"ambos"
"c/c" / "combinado com"
referência invertida: "ECE 20/2020, art. 7º"
```

Corrigir normalização de ano de dois dígitos com regra temporal segura para o domínio:

```text
00-49 => 2000-2049
50-99 => 1950-1999
```

Testar `EC20/98 -> 1998`, `EC41/03 -> 2003`, `EC47/05 -> 2005`.

O parser deve transformar corretamente o caso ECE20 complexo com art. 7º e §11 do art. 6º.

Commit: `feat: add structured legal reference parser v2`.

## Task 2 — Perfil previdenciário funcional

Criar `buildRetirementLegalProfile({ operativeText, documentaryValue, cargo, references })`.

Extrair independentemente:

```text
scope
modality
proportionality
calculation_basis
parity
professor_context
professor_rule_explicit
transition_rule
```

Testes obrigatórios:

1. `aposentadoria voluntária por tempo de contribuição, com proventos integrais` => modality voluntary_contribution + proportionality integral.
2. `proventos integrais calculados pela média` => integral + average; parity não deve virar yes.
3. `aposentadoria por invalidez com proventos proporcionais` => invalidity_permanent_disability + proportional.
4. `incapacidade permanente` => mesma família funcional de invalidez, preservando texto/evidência.
5. cargo Professor sem dispositivo docente => professor_context true e professor_rule_explicit false.
6. referência expressa CF art. 40 §5º em aposentadoria voluntária docente => professor_rule_explicit true.

Commit: `feat: derive retirement legal profile`.

## Task 3 — Catálogo e classes canônicas do portal

Criar `portal-legal-crosswalk.js`.

Responsabilidades:

- Parsear todas as opções atuais do portal em `PortalLegalClass`.
- Identificar `scope: civil|military`.
- Associar labels conhecidas a classes canônicas sem hardcode de `option.value`.
- Detectar opção desconhecida/nova e marcá-la como `UNKNOWN_PORTAL_OPTION` para REVIEW, não adivinhar.

Classes iniciais civis devem cobrir todas as opções observadas do catálogo acima.

Para opções militares: classificar `scope=military`; nenhuma precisa de semântica aprofundada nesta rodada.

Commit: `feat: model portal legal foundation catalog`.

## Task 4 — Crosswalk jurídico ECE20 -> catálogo legado

Implementar crosswalk explícito e auditável, sem fingir identidade normativa.

Exemplo principal:

```text
SOURCE: ECE 20/2020 art. 7º + aposentadoria voluntária por tempo de contribuição + integrais
TARGET CANDIDATES: classes históricas EC41/EC47 do portal
```

O classificador deve permitir que a classe histórica vença por equivalência cadastral/funcional, apesar de diploma diferente.

Regras:

- ECE x EC deixa de ser veto global no crosswalk.
- conflito real entre duas referências contraditórias da própria resolução continua bloqueando.
- ausência de CF art. 40 §5º na fonte não pode ser inventada só pelo cargo.
- se duas classes irmãs (EC41 geral x EC41 professor) ficarem próximas por falta de discriminador explícito, resultado deve ser REVIEW conforme margin.

Commit: `feat: crosswalk modern state retirement rules to portal catalog`.

## Task 5 — Scoring semântico, confidence e margin

Substituir o papel dominante do score lexical por score jurídico.

Ordem recomendada de pesos:

```text
scope/modalidade incompatível => hard reject
proportionality => muito alto
calculation_basis/parity => alto quando conhecido
diploma/regra/crosswalk => alto
artigo/parágrafo/inciso/alínea discriminante => alto
transition_rule => médio/alto
professor_rule_explicit => alto
professor_context => baixo
lexical Dice => residual, máximo 5% do total
```

Produzir ranking com `reasons` legíveis e `alternatives`.

Implementar status `auto|review|pending` internamente; manter compatibilidade externa necessária com contratos existentes.

Testes:

- mesmo diploma/artigo errado sem crosswalk: nunca AUTO;
- alínea errada: hard reject quando discrimina opções;
- opção militar: hard reject;
- ECE20 -> EC41/EC47: similarity jurídica permitida;
- top1 alto mas margin baixo: REVIEW;
- confidence alto + margin adequado: AUTO.

Commit: `feat: rank portal foundations with legal confidence`.

## Task 6 — Integrar ao resolvedor/matcher sem quebrar demais campos

Modificar `legal-foundation.js` e `matcher.js` para usar pipeline v2 apenas em `fundamento_legal` com contexto.

Preservar comportamento de `modalidade` e demais campos.

A decisão deve expor:

```text
rules_version=legal-foundation-v2
method=exact|rule|similarity|none
status=selected|pending
confidence
margin
reasons
ranking
documentary_foundation
portal_classification
```

Quando v2 indicar REVIEW, não produzir `matchedValues.fundamento_legal` apto a envio automático.

Commit: `refactor: route legal foundation matching through crosswalk v2`.

## Task 7 — Preflight, automação e painel

### Preflight

AUTO somente quando:

```text
portal_classification.status == auto
option_value existe no catálogo atual
confidence >= threshold
margin >= threshold
contexto/hash/identidade continuam válidos
sem hard reject/contradição
```

REVIEW/PENDING bloqueiam preenchimento automático do fundamento.

### Painel

Mostrar ao usuário:

```text
Fundamento documental
Perfil identificado
Opção do portal sugerida
Método
Confiança
Margem
Sinais que coincidiram
Complementos existentes somente no catálogo
Conflitos/ausências relevantes
2ª melhor opção
```

Exemplo de explicação:

```text
Fonte: ECE 20/2020, art. 7º — aposentadoria voluntária, tempo de contribuição, proventos integrais
Portal: EC 41/2003 + EC 47/2005
Método: crosswalk jurídico
Confiança: 0.94
Margem: 0.18
Observação: o portal usa classe histórica; o fundamento documental permanece ECE 20/2020.
```

Commit: `feat: gate and explain legal crosswalk decisions`.

## Task 8 — Versionamento, serviço local e empacotamento

Atualizar coerentemente:

```text
LEGAL_FOUNDATION_RULES_VERSION = legal-foundation-v2
RULES_VERSION no serviço local
qualification contract
capabilities
fixtures/testes que validam a versão
```

Atualizar allowlists/package scripts para incluir os módulos novos.

Não declarar release-ready sem smoke do ZIP/pacote portátil.

Commit: `build: package legal crosswalk v2 modules`.

## Task 9 — Matriz de regressão jurídica do lote de professores

Criar/expandir `legal-foundations-professores-v2.json` com pelo menos 12 casos:

```text
4 voluntária por tempo de contribuição + integrais
3 voluntária por tempo de contribuição + proporcionais
3 invalidez/incapacidade permanente
2 ambíguos/negativos que devem ficar REVIEW/PENDING
```

Pelo menos 6 casos devem vir de resoluções reais anonimizadas do lote antes do go-live.

Cada fixture deve declarar ground truth somente quando conhecido; caso incerto deve esperar REVIEW.

Métricas obrigatórias:

```text
accuracy top-1 nos casos com ground truth
AUTO corretos
REVIEW corretos
falsos AUTO = 0
militares rejeitados = 100%
modalidades incompatíveis nunca automatizadas
confusões entre classes irmãs
```

Critério de piloto:

```text
falsos AUTO = 0
100% militar rejeitado em escopo civil
100% modalidade incompatível não automatizada
>=90% top-1 nos casos reais com ground truth, ou divergentes em REVIEW
```

Commit: `test: validate teacher retirement legal crosswalk`.

## Task 10 — Verificação final e handoff

Rodar suite JS relevante, incluindo novos testes e regressões antigas.

Rodar Python relevante: `test_legal_context.py`, `test_local_service.py`, `test_automation_api.py`, recovery/integration.

Executar:

```bash
git grep -n "legal-foundation-v1"
git grep -n "hasIncompatibleDiplomaFamilies"
git grep -n "diceScore"
```

Esperado:

- v1 apenas em documentação histórica, se houver;
- nenhum veto global ECE x EC no caminho v2;
- Dice somente residual.

Smoke do pacote QA:

```text
extensão inicia
/health responde
rules_version=legal-foundation-v2
contexto legal carrega
REVIEW não é aplicado automaticamente
AUTO aplica somente option.value presente no catálogo atual
```

Criar `docs/notes/2026-09-15-fundamentacao-professores-v2-handoff.md` com branch, HEAD, commits, arquivos, comandos, contagens, métricas, casos em REVIEW e rollback.

Antes de declarar concluído, usar `superpowers:requesting-code-review` e `superpowers:verification-before-completion`.

---

# Mandatory Regression Cases

## A. Crosswalk ECE20 -> catálogo legado permitido

```text
SOURCE:
professor
aposentadoria voluntária por tempo de contribuição
proventos integrais
ECE 20/2020 art. 7º

EXPECTED:
não bloquear apenas porque portal usa EC41/EC47
produzir ranking civil semanticamente explicado
```

## B. Professor não inventa §5º

```text
SOURCE:
cargo professor
incapacidade permanente
sem referência docente expressa

EXPECTED:
não escolher regra de aposentadoria voluntária docente por cargo
```

## C. Integral não significa integralidade

```text
SOURCE:
proventos integrais calculados pela média

EXPECTED:
proportionality=integral
calculation_basis=average
parity != yes por inferência automática
```

## D. Alínea importa

```text
SOURCE: CF art40 §1 III a
CANDIDATES: III a / III b
EXPECTED: b rejeitada como discriminador incompatível
```

## E. Ano histórico correto

```text
EC20/98 => 1998
EC41/03 => 2003
```

## F. Similarity continua existindo

```text
norma documental moderna/estadual
+
opção cadastral histórica
+
crosswalk declarado
=> method=similarity permitido
```

## G. Similarity lexical solta não automatiza

```text
mesmo diploma, artigo diferente, nenhum crosswalk
=> não AUTO
```

## H. Militar nunca vence professor civil

Todas as opções militares ficam hard-rejected para `scope=civil`.

---

# Non-Goals

Não implementar nesta rodada:

- motor genérico para qualquer RPPS do Brasil;
- pesquisa automática de jurisprudência;
- validação autônoma de legalidade do ato concessório;
- reconstrução dos requisitos pessoais de aposentadoria a partir de tempo de contribuição;
- inferência de direito adquirido sem texto documental;
- substituição da decisão humana em casos REVIEW;
- alteração remota do catálogo da Área Restrita;
- hardcode de `option.value` do portal.

---

# Rollback

Se v2 apresentar regressão em ambiente real:

1. manter captura de contexto/análise, mas bloquear `fundamento_legal` em AUTO;
2. permitir apenas sugestão no painel;
3. não voltar silenciosamente ao fuzzy lexical legado para envio automático;
4. registrar `rules_version`, processo anonimizado/chave interna, ranking e motivo;
5. corrigir fixture + teste RED antes de reativar AUTO.

---

# Definition of Done

A feature só está concluída quando todos forem verdadeiros:

- parser v2 entende múltiplos parágrafos/incisos/alíneas do caso ECE20;
- `EC20/98` é 1998, não 2098;
- perfil diferencia modalidade, proporcionalidade, base de cálculo e paridade;
- cargo Professor não cria fundamento docente por si só;
- ECE20 pode fazer crosswalk para classe histórica EC41/EC47;
- EC x ECE não é mais veto global cadastral;
- conflitos documentais reais continuam bloqueados;
- Dice lexical vale no máximo 5% do score;
- opções militares são hard reject no escopo civil;
- confidence e margin controlam AUTO;
- caso ambíguo vira REVIEW/PENDING;
- painel explica documental x cadastral;
- `legal-foundation-v2` está consistente JS/Python/qualification;
- novos módulos entram no pacote portátil;
- falsos AUTO = 0 no corpus de validação;
- suites JS/Python relevantes com 0 FAIL;
- smoke do pacote QA aprovado;
- handoff final escrito com evidências.

---

# Instructions to Codex at Execution Time

1. Leia este plano integralmente antes de alterar qualquer arquivo.
2. Use `superpowers:using-git-worktrees` antes de implementar.
3. Execute Task 0 e confirme RED real antes de escrever produção.
4. Siga as tasks em ordem; não pule gates de teste.
5. Use `superpowers:subagent-driven-development` se disponível; uma task por subagente/revisão.
6. Após cada task, execute os testes indicados e registre resultados.
7. Não mude expected de fixture real apenas para fazer GREEN; se o ground truth for incerto, classifique como REVIEW.
8. Não use `cargo=Professor` como atalho para §5º da CF.
9. Não remova similarity; substitua similarity textual fraca por similarity jurídica/crosswalk auditável.
10. Não habilite envio real antes da Task 9 + Task 10.
11. Ao terminar, use `superpowers:requesting-code-review` e `superpowers:verification-before-completion`.
12. Entregue handoff final, ranking dos casos reais e lista dos casos que permaneceram para revisão manual.
