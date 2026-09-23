# Atos-TCE — Design: Preenchimento Best-Effort com Fundamento Legal v4

**Data:** 2026-09-23  
**Repositório:** `matheussilva421/Atos-TCE`  
**Branch alvo:** `codex/mesa-local-refactor`  
**Escopo:** fluxo M5 de preenchimento da Área Restrita pela Mesa + extensão, incluindo a política `legal-foundation-v4`.

## 1. Objetivo

O preenchimento automático deve economizar trabalho operacional, não exigir perfeição para começar.

A nova regra de produto é:

> Se a automação confirmou que está no processo e interessado corretos, ela deve preencher tudo o que conseguir com segurança operacional. Divergências, ausências, controles não graváveis e falhas isoladas viram avisos para revisão humana; não impedem os demais campos de serem preenchidos.

O clique final de **Complementar Ato** permanece manual.

Esta spec substitui a filosofia anterior de "preenchimento perfeito ou nada" por **best-effort + revisão humana**.

## 2. Problema atual

O fluxo M5 foi desenhado como fail-closed em várias camadas:

1. `app/area_restrita/preflight.py` bloqueia todo o plano por divergência de valor existente, controle obrigatório ausente/read-only, proposta ausente e opção literal inexistente.
2. `extension/content/fill-form.js` valida o plano inteiro antes da primeira escrita; um único campo recusado transforma campos válidos em `skipped`.
3. `app/area_restrita/fill_service.py` transforma essas situações em `BLOQUEADO`/`ERRO` e pode alterar o status analítico do processo.
4. `app/web/app.js` oferece **Preencher ato** apenas para processos `PRONTO`, de modo que uma falha de preenchimento pode retirar o processo do fluxo de nova tentativa.
5. `extension/content/detect-form.js` exige o conjunto completo de sentinelas para considerar o formulário disponível.
6. No `fundamento_legal`, o matcher literal genérico pode lançar `OPTION_NOT_AVAILABLE` antes de `resolve_legal_foundation()`, impedindo o motor jurídico de escolher a melhor opção.

O resultado prático é que uma divergência mínima em um campo impede a automação de preencher campos independentes e corretos.

## 3. Princípio de segurança

A política deve distinguir dois tipos de problema.

### 3.1. Problemas que podem causar escrita no ato errado

Esses continuam sendo **hard block**:

- processo/ano incompatível;
- interessado incompatível de forma inequívoca;
- ausência de identidade suficiente para vincular o formulário ao processo;
- mais de um formulário candidato sem critério seguro para escolher;
- troca de identidade entre leitura e escrita;
- stale generation que não possa ser recuperada por releitura/replanejamento;
- comando pertencente a requisição diferente/stale/foreign.

A automação nunca deve "chutar" qual processo preencher.

### 3.2. Problemas de conteúdo de campo

Esses **não bloqueiam o restante do preenchimento**:

- proposta ausente;
- controle ausente;
- controle `disabled` ou `readOnly`;
- valor existente divergente;
- opção específica não encontrada;
- falha ao escrever um campo;
- releitura divergente de um campo;
- baixa confiança/margem no fundamento legal;
- empate ou hard conflict no ranking jurídico.

Essas situações produzem resultado por campo + warning.

## 4. Contrato de preenchimento por campo

Cada campo termina em um estado independente.

Estados recomendados:

- `changed`: valor escrito e relido como esperado;
- `preserved`: havia valor existente que não foi sobrescrito;
- `missing_proposal`: não havia proposta documental;
- `not_found`: controle não existe no DOM atual;
- `disabled`: controle não pode ser escrito;
- `option_unavailable`: catálogo não contém valor gravável para aquele campo;
- `failed`: tentativa de escrita/releitura falhou;
- `warning`: metadado complementar, não substitui o estado principal.

Não deve existir mais a regra global "um campo inválido => todos os campos válidos ficam `skipped`".

A extensão deve escrever campo a campo, continuar após falhas isoladas e reler cada campo alterado.

## 5. Valores já existentes

A política padrão é **não sobrescrever silenciosamente valores não vazios divergentes**.

Para qualquer campo:

- atual vazio + proposta gravável -> escrever;
- atual equivalente à proposta -> `preserved`;
- atual não vazio e divergente -> `preserved` + warning `existing_value_divergence`;
- continuar processando os demais campos.

Isso elimina o bloqueio global sem destruir informação que o portal já possuía.

Uma futura ação explícita de override pode ser desenhada separadamente; não faz parte desta spec.

## 6. Fundamento legal v4 — best available obrigatório

O plano `2026-09-21-fundamento-legal-v4-best-available-plan.md` é incorporado como subsistema de decisão do fundamento, com as adaptações globais desta spec.

### 6.1. Regra principal

Se:

- existe proposta/texto documental de `fundamento_legal`; e
- o catálogo atual do `<select>` possui pelo menos uma opção realmente selecionável;

então o backend deve escolher **exatamente uma** opção do catálogo.

O texto documental serve para **ranquear** as opções do portal; não precisa coincidir literalmente com `option.value` ou `option.label`.

### 6.2. Não podem impedir uma escolha

Quando há ao menos uma opção real:

- `confidence < 0.90`;
- `margin < 0.12`;
- empate;
- classe desconhecida;
- `hard_conflict`;
- referência incompleta;
- ausência de referência estruturada, mas texto utilizável;
- contradição;
- todas as candidatas previamente marcadas como rejeitadas.

Esses fatores permanecem no diagnóstico e em warnings, mas não autorizam deixar o campo no placeholder.

### 6.3. Catálogo selecionável

Deve existir uma única função canônica para filtrar opções reais do DOM.

Requisitos:

- preservar o `value` bruto;
- `value` vazio não é selecionável;
- `label` vazio não é selecionável;
- placeholders "Selecionar/Selecione..." não são selecionáveis;
- não converter `value=""` no próprio label;
- preservar `option_index` para desempate determinístico.

Se não restar nenhuma opção real, o fundamento não é inventado: resultado `LEGAL_OPTIONS_EMPTY` + warning, e os demais campos continuam.

### 6.4. Ordem correta do preflight

`fundamento_legal` sai do matcher literal genérico.

Fluxo:

```text
proposta documental
  -> catálogo atual
  -> filtro de opções selecionáveis
  -> resolve_legal_foundation()
  -> ranking v4
  -> option_value vencedor
  -> validar membership no catálogo atual
  -> incluir no plano de escrita
```

Nunca enviar o texto documental diretamente como `value` de um `<select>`.

### 6.5. Ranking e fallback

Preservar score bruto/compatibilidade mesmo quando houver hard conflict.

Ordem:

1. preferir candidatas sem hard conflict, quando existirem;
2. caso contrário, escolher a melhor dentre todas;
3. ordenar por score de compatibilidade;
4. usar componentes estruturais/crosswalk/discriminadores/lexical como tie-breaks;
5. `option_index` como último desempate determinístico.

`TRUE_TIE` deixa de ser estado impeditivo. Um empate real deve produzir warning e escolha determinística.

### 6.6. Thresholds viram telemetria

`confidence` e `margin` continuam calculados e expostos, mas não são condição de autorização.

`is_automatic_legal_decision()` passa a validar integridade:

- `status == selected`;
- `decision_state == AUTO_SELECTED`;
- `rules_version == legal-foundation-v4`;
- `option_value` não vazio;
- `method != none`.

Não exigir threshold mínimo ou `hard_conflict == false`.

A membership do `option_value` no catálogo atual é validada no backend e novamente pela extensão.

## 7. Preflight backend

`build_fill_plan()` deixa de ser um gate all-or-nothing de conteúdo.

Ele continua responsável por:

- confirmar identidade;
- confirmar generation;
- construir plano dos campos;
- produzir warnings;
- resolver fundamento legal v4;
- nunca autorizar campo/valor fora da allowlist.

Para campos comuns, falhas de conteúdo são acumuladas em warnings/resultados e não levantam `FillBlocked`.

`FillBlocked` fica reservado a risco de alvo errado ou impossibilidade de estabelecer sessão/formulário seguro.

O plano precisa carregar informação suficiente para a extensão devolver resultado por campo.

## 8. Extensão

`extension/content/fill-form.js` permanece sem capacidade de submit.

A mudança de comportamento é:

1. validar identidade e generation antes da escrita;
2. processar cada campo independentemente;
3. não abortar todos os campos porque um falhou;
4. nunca escrever controle inexistente/desabilitado;
5. nunca escrever opção de `<select>` inexistente;
6. reler cada campo alterado;
7. retornar `field_results` completo.

Identidade/generation continuam sendo invariantes globais: se falharem, zero writes.

Falha de um campo após o início da escrita não desfaz os outros campos já corretamente preenchidos; é registrada como warning/result.

## 9. Leitura do formulário

`detect-form.js` deve distinguir:

- sentinelas necessárias para provar que a página é o formulário correto;
- campos individuais que podem estar ausentes/alterados.

A existência do formulário não deve depender necessariamente de todos os controles de conteúdo estarem presentes, especialmente campos opcionais.

A lista exata de sentinelas de identidade/navegação deve ser definida na implementação após leitura dos testes e do DOM já modelado no projeto.

## 10. Máquina de estados e status do processo

O estado analítico do processo (`PRONTO`, `REVISAR`, etc.) não deve ser corrompido por uma tentativa operacional de preenchimento.

Uma falha de transporte/DOM/filler pertence à **fill request**, não necessariamente à qualificação documental do processo.

### 10.1. Resultado terminal recomendado

`PREENCHIDO` significa que a tentativa executou e produziu relatório, mesmo que existam campos preservados ou warnings.

Exemplo:

```json
{
  "state": "PREENCHIDO",
  "changed": ["cargo", "matricula", "fundamento_legal"],
  "preserved": ["modalidade"],
  "warnings": [
    {"field": "data_publicacao_doe", "code": "CONTROL_NOT_FOUND"}
  ]
}
```

`BLOQUEADO` fica reservado aos hard blocks de identidade/alvo.

`ERRO` representa falha técnica da requisição de preenchimento, sem transformar automaticamente um processo documentalmente `PRONTO` em `ERRO`.

### 10.2. Retry

Depois de warning ou erro técnico, o usuário deve poder tentar preencher novamente sem precisar reparar manualmente o status do processo.

A Mesa deve oferecer a ação enquanto o processo continuar elegível documentalmente.

## 11. Mesa/UI

A UI deve comunicar progresso útil, não apenas sucesso/fracasso binário.

Resultado esperado:

> Ato preenchido — 4 alterados, 1 preservado, 1 para revisar. Confira e conclua manualmente no portal.

Warnings precisam ser visíveis no detalhe da tentativa/processo.

A Mesa não deve ocultar o botão apenas porque uma tentativa anterior terminou com warning/erro operacional.

## 12. Observabilidade

O relatório deve permitir descobrir por que um campo não foi escrito sem transformar isso em bloqueio global.

Para `fundamento_legal`, manter:

- `rules_version`;
- `status`;
- `automatic`;
- `option_value`;
- `option_label`;
- `method`;
- `confidence`;
- `margin`;
- `hard_conflict`;
- `fallback_used`;
- `tie_break_used`;
- `reasons`;
- `warnings`;
- ranking/top candidates quando disponível.

Para cada campo, registrar `before`, `proposed`, `after`, `status` e erro/warning quando houver.

## 13. Compatibilidade com o oracle v3

Os oracles v3 permanecem históricos para parsers/perfis/comportamentos que não mudaram.

A policy final de decisão v4 diverge intencionalmente do v3 fail-closed.

Não alterar silenciosamente um oracle chamado v3 para fazê-lo agir como v4.

Testes v4 tornam-se a fonte de verdade da nova política de seleção.

## 14. Invariantes

### Segurança

1. Identidade incompatível nunca escreve.
2. Formulário ambíguo nunca escreve por ordem arbitrária.
3. Generation stale nunca é tratada como "boa o bastante".
4. Valor de select inexistente no catálogo atual nunca é escrito.
5. Nenhuma capacidade de submit/finalização automática é adicionada.

### Best-effort

6. Falha de um campo não impede campos independentes válidos.
7. Divergência existente preserva o valor e não bloqueia os outros.
8. Campo ausente/desabilitado vira warning.
9. Releitura divergente de um campo não apaga o resultado dos outros.
10. Erro operacional da tentativa não deve reclassificar automaticamente o processo documental.

### Fundamento v4

11. proposta documental + >= 1 opção real => exatamente 1 opção escolhida.
12. opção escolhida pertence ao catálogo atual.
13. placeholder nunca é vencedor.
14. baixa confiança não gera vazio.
15. baixa margem não gera vazio.
16. empate não gera vazio.
17. hard conflict não gera vazio.
18. mesma entrada + mesmo catálogo => mesma opção.

## 15. Estratégia de testes

A implementação deve ser TDD.

Cobertura mínima:

### Backend/preflight

- valor existente divergente preserva e permite outros campos;
- campo ausente/read-only permite outros campos;
- proposta ausente permite outros campos;
- fundamento não literal chama v4 e escolhe opção;
- `LEGAL_OPTIONS_EMPTY` não bloqueia outros campos;
- identidade divergente continua bloqueando;
- generation inválida continua bloqueando.

### Extensão

- dois campos válidos + um disabled: válidos são escritos;
- dois campos válidos + um select inválido: válidos são escritos;
- um write falha: os demais continuam;
- reread divergente marca apenas o campo afetado;
- identity/generation mismatch => zero writes;
- select membership continua obrigatório.

### Fill service

- warnings terminam com relatório utilizável;
- hard identity mismatch => `BLOQUEADO`;
- erro técnico da fill request não muda automaticamente `PRONTO` para `ERRO`;
- retry permanece disponível;
- `PREENCHIDO` registra changed/preserved/warnings.

### UI

- mostra contadores/resumo de preenchimento;
- mostra warnings;
- ação de preencher permanece disponível quando documentalmente elegível;
- não existe submit automático.

## 16. Fora de escopo

- clicar em **Complementar Ato**;
- sobrescrever automaticamente valor real divergente já existente;
- reclassificar upstream processos `REVISAR` como `PRONTO`;
- criar terceiro motor de ranking jurídico;
- remover telemetria/warnings jurídicos;
- fuzzy matching genérico que ignore o perfil jurídico atual;
- reformular aquisição e-Contas/Área Restrita fora do necessário para o filler.

## 17. Critérios de aceitação

A mudança só está pronta quando:

- divergência mínima em um campo não impede os demais;
- a extensão não usa mais precheck global para transformar campos válidos em `skipped`;
- conteúdo imperfeito gera warnings por campo;
- somente risco real de alvo errado mantém hard block;
- tentativa operacional não destrói a elegibilidade documental do processo;
- retry funciona;
- fundamento legal v4 escolhe exatamente uma opção quando existe proposta + opção real;
- o vencedor do fundamento pertence ao catálogo DOM atual;
- thresholds/hard conflict/empate são diagnósticos, não veto;
- placeholders são filtrados;
- v3 histórico não é mascarado como v4;
- nenhum submit automático é introduzido;
- testes focados e suíte completa ficam verdes;
- validação real supervisionada confirma preenchimento parcial/best-effort e releitura correta.

## 18. Regra de ouro para implementação

> Confirme rigorosamente **onde** está escrevendo; seja tolerante sobre **quanto** consegue preencher. Segurança de identidade é fail-closed. Conteúdo de campo é best-effort. O operador revisa e conclui manualmente.

Para `fundamento_legal`:

> O texto documental ranqueia o catálogo fechado do portal. Se existe proposta documental e ao menos uma opção real, escolha exatamente uma opção determinística do catálogo. Evidência fraca muda warnings e método, não autoriza deixar o campo vazio.
