# Task 3 — Relatório de escopo e cardinalidade da análise

## Resultado

Implementada a propagação dos dois escopos autoritativos (`sector_finalistic` e
`my_processes`) e a cardinalidade por identidade `(process_key, interested_key)`.
O envio permanece fail-closed e não houve login, rede, envio, tramitação ou
alteração no pacote de referência `Versions/...`.

## Causa raiz

- `panel.js` fixava `sector_finalistic` em `startAnalysis()`; o schema de
  mensagens também rejeitava `my_processes` quando `analysisOnly` era verdadeiro.
- O receptor Python e a página HTML aceitavam somente o escopo do setor.
- O materializador indexava a fotografia apenas por `process_key`, descartando
  a possibilidade de interessados distintos no mesmo processo; sua contagem de
  manifesto também era implicitamente comparada à quantidade expandida.
- `automation-controller.js` agrupava observações por processo e convertia
  múltiplas identidades em uma única linha `AMBIGUO`. Observações conflitantes da
  mesma identidade podiam ser deduplicadas silenciosamente.

## TDD — RED

Testes escritos antes das respectivas correções de produção:

- Painel: expectativa `my_processes` falhou porque o payload recebeu
  `sector_finalistic`; o caso de escopo desconhecido também permitia prosseguir.
- Schema Node: `my_processes` falhou com `AUTO_ANALYZE analysis sourceScope is invalid`.
- Receptor: `my_processes` falhou na validação Python e a página não continha o
  escopo.
- Materializador: duas identidades no mesmo processo falharam com escopo fixo;
  após liberar o escopo, a cardinalidade falhou na validação de `unique_count`.
- Controlador: duas identidades no mesmo processo retornaram uma linha com
  `interested_key: null`; o teste de conflito também selecionava a primeira
  observação em vez de bloquear.

## Implementação GREEN

- `panel.js` lê `automation-source-scope` e bloqueia valores fora do conjunto
  fechado de dois escopos.
- `messages.js`, receptor Python e HTML validam os dois escopos e rejeitam os
  demais.
- `materialize_area_analysis.py` indexa por processo e preserva cada identidade
  distinta, rejeita duplicidade da tupla `(process_key, interested_key)` e
  mantém processos ausentes como identidade nula/bloqueada.
- `automation-controller.js` emite uma linha por observação identitária e
  transforma divergência da mesma identidade em linha `AMBIGUO` sem identidade.
- Os testes cobrem os dois escopos, dois interessados no mesmo processo,
  ausência e conflito; não houve relaxamento de `auto_submit`.

## Testes executados

### Regressão focada da Task 3

```text
python -m unittest test_area_restrita_analysis test_materialize_area_analysis test_area_snapshot_receiver -v
13 testes executados; 13 passaram; 0 falharam.
Status: verde.
```

### Suítes focadas Node

```text
npm test -- tests/panel.test.mjs
49 testes executados; 49 passaram; 0 falharam.

npm test -- tests/schema.test.mjs
12 testes executados; 12 passaram; 0 falharam.

npm test -- tests/automation-controller.test.mjs
67 testes executados; 67 passaram; 0 falharam.
```

### Regressão completa da extensão

```text
npm test
386 testes executados; 385 passaram; 1 falhou.
```

A única falha foi `automatic submission requires capability and an action-time
confirmation`, em `tests/panel.test.mjs:932`, com confirmação vazia. Ela foi
reproduzida isoladamente com `--test-name-pattern`, não toca o código da Task 3
nem foi mascarada. Nesta execução ela é determinística, portanto fica registrada
como falha independente da base, não como flakiness confirmada.

## Diff, Git e limitações

- `git diff --check`: passou antes do commit final; a checagem staged também deve permanecer sem erros.
- Alterações destinadas ao commit: somente os arquivos da Task 3, incluindo este
  relatório e o novo teste do receptor.
- `Versions/...` permanece inalterado.
- Não houve push; o SHA será registrado após o commit.
- Limitação: a regressão completa Node não ficou totalmente verde por causa da
  falha independente descrita acima.
