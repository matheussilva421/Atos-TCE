# Relatório — Fase 2: resolvedor específico de fundamento

## Estado

- Branch: `codex/fundamentacao-automatico`
- Brief seguido: `.superpowers/sdd/2026-09-08-fundamentacao-automatico-plano-fases/task-2-brief.md`
- Commit: `fix: resolve legal foundations from documentary references` (`697f60a`)
- Escopo: Fase 2 somente; nenhum worker, painel, API, persistência, navegação, envio, redesign ou dataset v1 foi alterado.

## Implementação

- Criado `work/tce-extractor/portable/extensao-complementar-ato/lib/legal-foundation.js`.
  - `parseLegalReferences(text)` separa EC/ECE/CF, preserva ano e sufixo A,
    expande romanos e intervalos de incisos, entende `arts.`, `ambos`,
    parágrafo único, `c/c`/`combinado com` e referências invertidas.
  - `resolveLegalFoundation({ context, options })` consome somente
    `LegalContext` completo (`resolution_status=complete`), usa o trecho
    operativo final, associa citações de páginas e retorna `LegalDecision` com
    status, método, regra, opção, score, razões, ranking completo, referências,
    citações e `rules_version`.
  - Implementa EC41 sem/com §5, EC47 art. 3º, CF art. 40 §1º II e art. 6º-A
    sem confusão com art. 6º; ano ausente, contradição, conflito de família,
    empate e score zero ficam `pending` sem seleção.
  - Filtra placeholder/opções sem valor e não usa cargo para acrescentar §5.
- Alterado `lib/normalizer.js` somente para os sinais jurídicos necessários.
- Alterado `lib/matcher.js` para manter modalidade legada, retornar
  `pending/null` para score zero e carregar `legalDecision` apenas quando um
  contexto for explicitamente fornecido.
- Criados/atualizados os testes focais correspondentes.

## TDD — RED/GREEN

1. Parser inicial: RED por módulo ausente; GREEN após o primeiro contrato EC/ECE.
2. Normalização: RED em CF/sufixo e `c/c`; GREEN após normalização mínima.
3. Parser estrutural: RED em `ambos`, c/c, CF e referências invertidas; GREEN
   após associação por referência.
4. Resolvedor: RED pelo stub não implementado; GREEN em EC47 com ranking e
   citações.
5. Regras obrigatórias: GREEN para EC41 sem/com §5, art. 7 isolado vinculado,
   art. 6-A, CF §1º II, placeholder, empate, contexto incompleto, ano ausente,
   ano divergente e família conflitante.
6. Matcher: RED legado (3 falhas no ciclo, incluindo a RED existente); GREEN
   após `pending/null` e transporte opcional de `legalDecision`.
7. Parser plural: RED em `Arts. 6º e 7º`; GREEN após expansão.
8. Histórico: RED ao misturar menção histórica e `RESOLVE`; GREEN após limitar
   o consumo ao último marcador operativo.

## Testes e validações

Comando focal obrigatório:

```text
node --test tests/legal-foundation.test.mjs tests/matcher.test.mjs tests/normalizer.test.mjs
```

Resultado focal final: 52 testes executados, 52 passaram, 0 falharam.

Comando full:

```text
npm test
```

Resultado full final: 144 testes executados, 144 passaram, 0 falharam.

Também foi executado `git diff --check` sem diagnóstico.

## Self-review

- Padrões: alterações pequenas e localizadas; funções públicas são testadas
  por comportamento, sem mocks de colaboradores internos.
- Especificação: o resolvedor é fail-closed em contexto incompleto, ano
  ausente, contradição, família conflitante, empate e score zero; não usa a
  ordem do catálogo como desempate de decisão.
- Compatibilidade: o caminho legado do matcher permanece para chamadas sem
  `context`; modalidade e schema v1 não foram redesenhados.
- Limite conhecido: a allowlist do empacotador ainda não inclui o
  `legal_context.py` da Fase 1; isso permanece concern posterior de pacote,
  fora desta fase.

## GitHub e retomada

- O checkout não possui remoto configurado; nenhum push foi realizado nem
  será criado remoto arbitrário.
- Após o commit, conferir `git status --short --branch` e usar este relatório
  como ponto de retomada.
- Próximas fases podem consumir `legalDecision`; não integrar worker/painel
  nesta fase.

## Rodada de correção — achados da revisão independente

- Estado: os quatro achados foram corrigidos no resolvedor e cobertos por sete
  testes RED/GREEN adicionais.
- Famílias: EC, ECE, CF e CE agora exigem identidade de diploma compatível;
  EC/ECE e CF/CE incompatíveis ficam `pending`, e `OTHER` não resolve por
  similaridade lexical sem diploma compartilhado.
- Contradição: anos divergentes do mesmo diploma/tipo/número ficam
  `pending` mesmo quando aparecem em artigos diferentes.
- EC47: `EC47_ART3` exige apenas art. 3º da EC47/2005; parágrafo único e
  incisos permanecem qualificadores opcionais.
- Precedência: referências estruturalmente equivalentes são avaliadas antes de
  `rule`/`similarity`; a interface pública não expõe `equivalence`: famílias
  conhecidas usam `method: "rule"` e equivalência sem família usa `exact`.
- TDD: RED confirmado em 7 testes novos (52 anteriores verdes); GREEN final
  em 59/59 testes focais.
- Validação completa: `npm test` passou em 151/151 testes; `git diff --check`
  passou.
- Escopo preservado: nenhum worker, painel, API, persistência ou envio real foi
  alterado ou executado.

## Rodada de correção — associação explícita em três referências

- Achado corrigido: `diplomaForArticle` ignorava diploma EC/ECE após um artigo
  quando havia outro artigo seguinte, fazendo o artigo herdar o diploma
  anterior e ocultando conflitos de família/ano.
- TDD RED: o novo teste `binds every explicit diploma in a three-reference
  conflict` falhou porque o art. 7º recebeu `EC 41/2003` em vez de `ECE
  41/2020`.
- Correção mínima: a associação agora usa o diploma pós-artigo quando a
  referência explícita termina em `da`, `do` ou `de`; a lógica de CF/CE com
  qualificadores foi preservada, assim como referências invertidas e `c/c`.
- GREEN focal: 61 testes executados, 61 passaram, 0 falharam.
- GREEN full (`npm test`): 153 testes executados, 153 passaram, 0 falharam.
- `git diff --check`: sem diagnóstico.
- Escopo: somente `lib/legal-foundation.js`,
  `tests/legal-foundation.test.mjs` e esta documentação foram alterados;
  nenhum worker, painel, API, persistência ou envio real foi alterado ou
  executado.
- Commit solicitado: `fix: bind each legal reference to its diploma`.
- Commit: `fix: close phase 2 review findings`.

## Rodada final — revisão independente do contrato público

- RED inicial confirmado no checkout: o focal executou 59 testes, com 58
  passando e 1 falhando por `ReferenceError: hasIncisos is not defined` no
  caminho CF art. 40 § 1º II (`lib/legal-foundation.js`).
- RED de contrato confirmado após os testes adicionais: 60 testes, 49
  passando e 11 falhando, cobrindo `resolved`/`equivalence` fora do contrato
  público.
- Correções mínimas: adicionada a verificação de incisos para `CF40_P1_II`;
  decisões selecionadas agora retornam `status: "selected"`; equivalência
  estrutural retorna `rule` para família conhecida ou `exact` sem família;
  `matcher.js` reconhece `selected` e preserva `kind: "probable"`.
- Testes de contrato cobrem exclusivamente status `selected|pending` e
  métodos `exact|rule|similarity|none`, além do caminho pending.
- Focal final: 60 testes executados, 60 passaram, 0 falharam.
- Full final (`npm test`): 152 testes executados, 152 passaram, 0 falharam.
- `git diff --check`: sem diagnóstico.
- Escopo preservado: nenhum worker, painel, API, persistência ou envio real foi
  alterado ou executado.

## Rodada de correção — combinado EC41/CF, CE e compatibilidade legada

- RED antes da implementação: o focal executou 64 testes, com 59 passando e 5
  falhando nos quatro cenários novos: EC41 com um único art. 6º + CF §5,
  abreviação CE, resultado legado sem `context` e fallback de mensagem pending.
- EC41/CF: `sourceFamilies` agora considera qualquer art. 6º ou 7º da EC41
  como vínculo suficiente para que CF art. 40 §5 forme `EC41_COM_P5`; art. 6º
  isolado sem CF §5 continua `EC41_SEM_P5`.
- CE: `normalizer.js` reconhece `CE` como `Constituição Estadual`; o resolvedor
  preserva a identidade `ce` e não casa com opções `cf`.
- Compatibilidade: o caminho legado sem `context` voltou a retornar `probable`,
  índice e opção mesmo em score zero; somente o caminho contextual de
  `fundamento_legal` retorna `pending/null` por decisão fail-closed.
- Mensagens: `createMessage` converte `pending`, `{kind: "pending"}` e status
  pending direto ou em `legalDecision` para `tie`, o fallback v1 cauteloso;
  valores desconhecidos continuam rejeitados.
- GREEN focal: 64 testes executados, 64 passaram, 0 falharam.
- GREEN full (`npm test`): 157 testes executados, 157 passaram, 0 falharam.
- `git diff --check`: sem diagnóstico.
- Escopo preservado: nenhum worker, painel, API, persistência, navegação ou
  envio real foi alterado ou executado.
- Commit final: `7ceb326c43adf9bb347712b6e3b20ed6125d4ab8`.
- Revisão independente final: aprovada sem achados funcionais; a correção
  posterior foi apenas documental, ajustando o focal para 64/64.
- Próxima fase: Fase 3, diário durável e relatórios.
