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
- Precedência: referências estruturalmente equivalentes recebem
  `method: "equivalence"`, antes de `rule`/`similarity`; a compatibilidade
  legada do matcher permanece inalterada.
- TDD: RED confirmado em 7 testes novos (52 anteriores verdes); GREEN final
  em 59/59 testes focais.
- Validação completa: `npm test` passou em 151/151 testes; `git diff --check`
  passou.
- Escopo preservado: nenhum worker, painel, API, persistência ou envio real foi
  alterado ou executado.
- Commit: `fix: close phase 2 review findings`.
