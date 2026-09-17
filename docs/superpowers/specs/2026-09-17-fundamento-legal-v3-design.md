# Design — Correção da Fundamentação Legal v3

Data: 2026-09-17

## 1. Objetivo

Corrigir a cadeia de decisão e preenchimento do campo `fundamento_legal` no fluxo de complementação de atos do TCE/RN, eliminando o fallback legado quando o `LegalContext` não estiver disponível e tornando a classificação jurídica dependente de contexto documental validado, catálogo real do portal e regras estruturais auditáveis.

A solução deve preservar o preenchimento dos demais campos quando a fundamentação não puder ser decidida com segurança.

## 2. Problema observado

O fluxo atual possui caminhos diferentes para obtenção do `LegalContext` no modo manual e no automático. Em determinadas situações, o painel envia `GET_MATCH` sem `context`; nesse caso, `rankPortalOptions()` pode sair do caminho especializado de fundamentação e cair no matcher genérico. Isso permite que `fundamento_legal` receba uma proposta aproximada por similaridade mesmo quando o pipeline jurídico especializado não foi executado.

O defeito é agravado por três fatores:

1. `applyPayload()` considera `proposedValue` suficiente para incluir um campo no payload de escrita;
2. a UI converte diferentes estados não automáticos em uma apresentação semelhante a “empate”, ocultando se houve revisão, bloqueio, falta de contexto ou empate real;
3. os testes principais do catálogo injetam metadados como `class_id` e `scope`, enquanto o portal real fornece essencialmente `value + label`.

## 3. Decisões aprovadas

### 3.1 LegalContext obrigatório para fundamentação

Nenhuma classificação de `fundamento_legal` pode ocorrer sem `LegalContext` válido.

Se o contexto estiver ausente ou inválido, o sistema deve tentar recuperá-lo/reconstruí-lo. Se a recuperação falhar, somente `fundamento_legal` fica bloqueado; modalidade, DOE, cargo, matrícula, data de nascimento, gênero e demais campos seguros continuam disponíveis.

### 3.2 Service Worker como proprietário do contexto

A obtenção e validação do `LegalContext` devem ser centralizadas no Service Worker. O painel deixa de ser a fonte de verdade para buscar e anexar contexto ao `GET_MATCH`.

Manual e automático passam a usar a mesma função conceitual:

```text
ensureLegalContext(identity)
```

### 3.3 Recuperação em três níveis

A resolução do contexto deve seguir esta ordem:

1. cache validado;
2. sidecar atual via serviço local;
3. reconstrução pontual do contexto do processo/interessado.

A reconstrução deve reaproveitar, na ordem:

1. texto nativo já persistido;
2. cache OCR existente;
3. documento local já adquirido;
4. aquisição/reprocessamento específico somente quando necessário.

Não deve haver reprocessamento global de lote por falha de um único ato.

### 3.4 Bloqueio seguro

Falhas não recuperáveis — documento ausente, ambiguidade de identidade, PDF corrompido, resolução conflitante, texto insuficiente ou evidência inconsistente — devem produzir um resultado explícito de bloqueio para `fundamento_legal`.

Os demais campos continuam normalmente.

## 4. Arquitetura alvo

```text
EVIDÊNCIAS DOCUMENTAIS
        ↓
LegalContext v4
        ↓
ensureLegalContext()
  ↙      ↓       ↘
cache  sidecar  rebuild
        ↓
validação forte
        ↓
legal-foundation-v3
        ↓
RetirementLegalProfile
        +
catálogo cru do portal
        ↓
CatalogOptionSignature[]
        ↓
hard rejects
        ↓
crosswalk
        ↓
ranking
        ↓
LegalDecision v3
   ↙             ↘
AUTO           REVIEW/BLOCK
 ↓                 ↓
write guard      fundamento omitido
 ↓
APPLY_FIELDS
```

## 5. Contrato de `ensureLegalContext()`

A função não deve retornar apenas `context | null`. O resultado precisa carregar estado, origem e motivo para permitir diagnóstico auditável.

Estrutura conceitual:

```text
status:
  ready
  rebuilt
  blocked

context:
  LegalContext | null

source:
  cache
  sidecar
  rebuilt

reason:
  null
  LEGAL_CONTEXT_NOT_FOUND
  CONTEXT_INCOMPLETE
  CONTEXT_CONFLICT
  DATASET_MISMATCH
  RULES_VERSION_MISMATCH
  DOCUMENT_EVIDENCE_MISSING
  IDENTITY_MISMATCH
  ...
```

### 5.1 Contexto considerado válido

Antes de liberar a classificação jurídica, devem ser validados pelo menos:

- `process_key` correto;
- interessado compatível com a identidade do item;
- `dataset_sha256` correspondente ao dataset carregado;
- `resolution_status === "complete"`;
- `operative_text` não vazio;
- evidências/páginas válidas;
- schema/context version suportados;
- `rules_version === "legal-foundation-v3"`;
- revisão/versão do contexto compatível;
- ausência de inconsistência de identidade documental.

A reconstrução nunca pode “afrouxar” essas validações. Ela deve gerar um novo contexto e validá-lo do zero antes de liberar a fundamentação.

## 6. Remoção do fallback legado

`fundamento_legal` passa a ser campo especial no matcher.

Regra obrigatória:

```text
field === "fundamento_legal"
        ↓
LegalContext válido?
  ├─ sim → resolveLegalFoundation / legal-foundation-v3
  └─ não → pending/blocked, optionValue=null
```

É proibido chamar o matcher genérico para `fundamento_legal`, ainda que a similaridade lexical seja alta.

Os demais campos continuam usando o matcher existente.

## 7. Catálogo real do portal como fonte de verdade

### 7.1 Formato de entrada

A classificação principal deve funcionar com o formato real capturado no portal:

```js
{
  value: "...",
  label: "Civil - Artigo ..."
}
```

Os testes de integração não devem depender de:

```text
class_id
scope
rule_id
```

### 7.2 `CatalogOptionSignature`

Cada opção do portal deve ser transformada em uma assinatura jurídica estruturada a partir de `parseLegalReferencesV2(label)`.

Campos conceituais:

```text
value
label original
scope
references[]
modality
teacher_rule
transition_family
class_id derivado estruturalmente
```

A identificação de classes não deve depender de substrings frágeis como `label.includes("paragrafo 5")`. O reconhecimento da regra docente deve resultar da estrutura jurídica, por exemplo CF art. 40 § 5º.

## 8. Compatibilidade jurídica antes de score

O ranking deve obedecer à ordem:

```text
perfil documental
      +
assinaturas do catálogo
      ↓
compatibilidade estrutural
      ↓
crosswalk
      ↓
hard rejects
      ↓
ranking
      ↓
lexical apenas como evidência auxiliar
```

Similaridade lexical nunca cria compatibilidade jurídica.

### 8.1 Hard rejects mínimos

Devem ser rejeitados antes do score:

- civil × militar;
- CF × CE quando juridicamente incompatíveis;
- art. 6º × art. 6º-A;
- inciso discriminador incompatível;
- alínea incompatível;
- modalidade incompatível;
- regra docente incompatível quando expressamente exigida;
- opção não selecionável.

## 9. Crosswalks e conflitos

### 9.1 ECE/RN 20/2020

O crosswalk ECE20 deve continuar traduzindo a fundamentação documental para a taxonomia fechada do portal quando juridicamente cabível.

No caso de aposentadoria voluntária por tempo de contribuição com base no art. 7º da ECE/RN 20/2020, a classificação deve seguir a família histórica correspondente do catálogo e nunca escolher EC 20/1998 apenas por similaridade lexical.

### 9.2 EC + ECE não é conflito global

A regra global “EC e ECE coexistindo => family-conflict” deve ser removida do caminho cadastral.

Referências como ECE/RN 20/2020 art. 2º podem funcionar como cláusula de preservação/transição junto com EC 41/2003, sem constituir conflito jurídico por si só.

Conflitos reais devem ser detectados a partir do papel e conteúdo das referências, e não apenas pela coexistência dos tipos de diploma.

## 10. `LegalDecision v3`

O contrato deve separar estado operacional de estado jurídico.

Estados jurídicos explícitos:

```text
AUTO_SELECTED
REVIEW_REQUIRED
TRUE_TIE
NO_COMPATIBLE_CANDIDATE
CONTEXT_BLOCKED
DOCUMENT_CONFLICT
CATALOG_UNRECOGNIZED
```

Durante a migração, `status` pode continuar aceitando:

```text
selected
review
pending
```

mas a UI e as barreiras de escrita devem usar `decision_state` para distinguir os casos.

## 11. Thresholds

Os thresholds atuais permanecem inicialmente:

```text
AUTO:
confidence >= 0.90
margin >= 0.12

REVIEW:
confidence >= 0.75
```

Eles não serão recalibrados nesta correção. Primeiro devem ser corrigidos contexto, catálogo, regras estruturais e regressões reais. Qualquer futura recalibração deverá ser baseada em corpus validado.

## 12. Barreiras de escrita

A decisão jurídica e a escrita no portal devem ser protegidas por duas barreiras independentes.

### 12.1 Barreira de decisão

`fundamento_legal` só é elegível para escrita quando:

```text
status = selected
decision_state = AUTO_SELECTED
context_status = ready | rebuilt
hard_conflict = false
confidence >= 0.90
margin >= 0.12
option_value existe no catálogo atual
rules_version = legal-foundation-v3
```

### 12.2 Barreira em `APPLY_FIELDS`

Antes de montar/enviar o payload de escrita:

```text
fundamento_legal possui LegalDecision v3 autorizada?
  ├─ sim → incluir
  └─ não → remover do payload
```

Essa barreira deve existir mesmo que `proposedValue` esteja preenchido por erro em outra camada.

O modo manual também respeita a mesma regra: “Preencher campos disponíveis” jamais escreve uma fundamentação em estado REVIEW, TRUE_TIE, BLOCKED ou PENDING.

## 13. UI e diagnóstico

A UI deve mostrar separadamente:

### 13.1 Contexto documental

Exemplos:

```text
Contexto jurídico: disponível
Origem: sidecar
Versão: legal-context-v4
Regras: legal-foundation-v3
```

ou:

```text
Contexto jurídico: reconstruído
Origem: evidências locais
```

ou:

```text
Contexto jurídico: bloqueado
Motivo: resolução documental conflitante
```

### 13.2 Decisão jurídica

Exemplos:

```text
Estado: seleção automática
Método: crosswalk estrutural
Confiança: 94%
Margem: 18 p.p.
```

ou:

```text
Estado: revisão necessária
Método: regra estrutural
Confiança: 87%
Margem: 9 p.p.
```

### 13.3 Preenchimento

A UI deve informar explicitamente:

```text
Fundamento legal: será preenchido
```

ou:

```text
Fundamento legal: não será preenchido automaticamente
Motivo: margem abaixo do limite
```

Não deve exibir “empate” para qualquer decisão não automática.

Quando não houver candidato utilizável:

```text
Proposta segura: nenhuma
```

Quando houver candidato apenas para revisão:

```text
Candidato principal: <label>
Estado: REVIEW_REQUIRED
Não será preenchido automaticamente.
```

## 14. Versionamento

`legal-foundation-v2` será incrementado para:

```text
legal-foundation-v3
```

O bump invalida:

- qualification antiga;
- caches jurídicos incompatíveis;
- decisões persistidas com v2;
- execução automática criada sob versão de regras diferente.

Não invalida PDFs, OCR ou evidências documentais válidas. Evidências podem ser reaproveitadas; a decisão jurídica deve ser recalculada.

## 15. Arquivos/áreas afetadas

A implementação deverá revisar, no mínimo:

- `portable/extensao-complementar-ato/background/service-worker.js`;
- `portable/extensao-complementar-ato/sidepanel/panel.js`;
- `portable/extensao-complementar-ato/sidepanel/panel-view.js`;
- `portable/extensao-complementar-ato/lib/matcher.js`;
- `portable/extensao-complementar-ato/lib/legal-foundation.js`;
- `portable/extensao-complementar-ato/lib/portal-legal-crosswalk.js`;
- `portable/extensao-complementar-ato/lib/legal-reference-parser-v2.js` quando necessário;
- `portable/extensao-complementar-ato/lib/retirement-legal-profile.js` quando necessário;
- `portable/extensao-complementar-ato/lib/bridge-client.js`;
- `portable/app/local_service.py`;
- `portable/app/legal_context.py`;
- `portable/app/analysis_pipeline.py` somente se necessário para reconstrução/publicação;
- testes JS da extensão;
- testes Python do serviço/pipeline.

Refactors fora desse fluxo não fazem parte do escopo.

## 16. Estratégia de testes

### 16.1 LegalContext

Cobrir:

- contexto existente;
- ausente;
- versão antiga;
- hash divergente;
- revisão divergente;
- `resolution_status=incomplete`;
- conflito documental;
- interessado divergente;
- reconstrução bem-sucedida;
- reconstrução impossível.

Garantia: nenhum desses cenários permite fallback legado para `fundamento_legal`.

### 16.2 Catálogo cru

Testar sem `class_id`, `scope` ou `rule_id` injetados:

- EC 41 arts. 6º/7º;
- EC 41 + CF art. 40 § 5º;
- EC 47 art. 3º;
- EC 41 art. 6º-A + EC 70;
- CF art. 40 § 1º III a;
- CF art. 40 § 1º III b;
- EC 20 art. 8º;
- ECE/RN 20/2020;
- incapacidade;
- professor;
- civil × militar;
- CF × CE;
- alínea a × b;
- incisos discriminadores.

### 16.3 Regressões reais sanitizadas

#### Maria Lúcia

Entrada documental: ECE/RN 20/2020, art. 7º, art. 6º, aposentadoria voluntária por tempo de contribuição, proventos integrais, cargo de professor.

Assert mínimo:

```text
NUNCA selecionar EC20_ART8
```

Conforme a regra vigente do projeto, o resultado esperado é `EC41_TRANSITION_GENERAL`, salvo futura alteração jurídica deliberada e documentada.

#### Joana D'Arc

Entrada documental: EC 41/2003 arts. 6º/7º, LCE 308/2005 art. 87 e ECE/RN 20/2020 art. 2º como preservação/transição.

Assert mínimo:

```text
context_status != null
confidence != null
margin != null
method != none
rules_version == legal-foundation-v3
```

A coexistência EC + ECE art. 2º não pode produzir `family-conflict` automaticamente.

### 16.4 Teste explícito contra o bug atual

Cenário:

```text
field = fundamento_legal
documentaryValue = texto jurídico válido
context = null
```

Resultado obrigatório:

```text
optionValue = null
kind = pending
reason = LEGAL_CONTEXT_REQUIRED
```

Mesmo que uma opção tenha similaridade lexical de 100%.

### 16.5 Teste da barreira de escrita

Cenário:

```text
LegalDecision não automática
+
proposedValue presente por qualquer motivo
```

Assert:

```text
APPLY_FIELDS não contém fundamento_legal
```

### 16.6 End-to-end

Simular:

```text
snapshot portal
→ GET_MATCH
→ ensureLegalContext
→ legal-foundation-v3
→ painel
→ Preencher campos disponíveis
→ APPLY_FIELDS
```

Nos casos bloqueados, os demais campos continuam; `fundamento_legal` não é escrito.

Nos casos `AUTO_SELECTED`, o fundamento pode ser escrito e deve corresponder exatamente ao `option_value` validado no catálogo atual.

## 17. Critérios de aceite

A correção só é considerada concluída quando houver evidência de que:

1. nenhum caminho usa matcher legado para `fundamento_legal`;
2. obtenção do contexto está centralizada no Service Worker;
3. contexto ausente dispara recuperação/reconstrução;
4. falha de reconstrução bloqueia somente o fundamento;
5. catálogo cru funciona sem metadados artificiais;
6. `§ 5º` é reconhecido estruturalmente;
7. ECE20 não pode virar EC20/1998 por similaridade;
8. EC + ECE art. 2º não é tratado como conflito global;
9. REVIEW, TRUE_TIE e BLOCKED são estados distintos;
10. `APPLY_FIELDS` possui guarda independente;
11. regressões Maria Lúcia e Joana passam;
12. suíte JS completa passa;
13. suíte Python completa passa;
14. integração extensão ↔ serviço passa;
15. pacote portátil contém os mesmos artefatos validados;
16. smoke test real supervisionado comprova que o fundamento exibido no painel é o mesmo `option_value` efetivamente selecionado no portal.

## 18. Fora de escopo

- recalibrar thresholds antes de corrigir a arquitetura;
- alterar regras jurídicas sem fixture/evidência correspondente;
- refatorar módulos não relacionados;
- fazer reprocessamento global de acervo por falha pontual;
- permitir fallback lexical para fundamento jurídico;
- liberar escrita automática de candidato em estado de revisão.

## 19. Resultado esperado

Após a implementação, o sistema deve ser fail-closed especificamente para a fundamentação jurídica, sem prejudicar a produtividade dos demais campos. Todo fundamento escrito no portal deve ser rastreável a:

1. evidência documental válida;
2. `LegalContext` validado;
3. regras `legal-foundation-v3`;
4. catálogo real do portal;
5. `LegalDecision v3` autorizada;
6. barreira de escrita final.

Esse encadeamento passa a ser a invariante de segurança do campo `fundamento_legal`.
