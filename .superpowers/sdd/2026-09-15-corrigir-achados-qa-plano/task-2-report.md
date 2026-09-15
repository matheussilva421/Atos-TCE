# Relatório Task 2 — Identidade exata do processo

**Data:** 15/09/2026
**Escopo:** `work/tce-extractor/portable/TcePortal.Driver.js` e teste Node isolado do driver
**Restrições observadas:** pacote de referência preservado; sem rede, login ou envio no portal.

## Fix round do review

O review identificou que a correção anterior ainda comparava `anoProcesso` com `Number(...)`. Isso aceitava a representação textual divergente `"02026"` para a solicitação `2026`. O candidato já presente no worktree foi mantido e validado: a comparação agora usa `String(item.anoProcesso) === String(year)`, preservando `2026` numérico e `"2026"` textual, mas exigindo a representação exata para strings.

Também foi mantida a regressão explícita para resposta vazia, que confirma rejeição antes de qualquer chamada a `/eventos`.

## Causa raiz

`resolveProcess(number, year)` já procurava uma combinação exata de `numeroProcesso` e `anoProcesso`, mas usava `result[0]` quando não encontrava essa combinação. Assim, uma resposta divergente que contivesse `idProcesso` podia ser aceita e encaminhada por `buildManifest()` ao endpoint de eventos do processo errado.

## Correção

Removido somente o fallback `|| result[0]`. A resolução agora retorna exclusivamente o item com número/ano correspondentes aos argumentos; lista vazia, divergência ou item exato sem `idProcesso` continuam lançando o erro existente antes da consulta de eventos. `buildManifest()`, downloads, exclusão de capas e retries não foram alterados.

## Teste adicionado

Arquivo: `work/tce-extractor/portable/extensao-complementar-ato/tests/portal-driver.test.mjs`

O teste carrega o driver real em uma VM Node com `fetch` controlado e cobre:

- resposta contendo somente processo divergente: rejeita e não chama `/eventos`;
- resposta com combinação exata sem `idProcesso`: rejeita e não chama `/eventos`;
- resposta com item divergente seguido do item exato: gera o manifest usando apenas o ID exato e chama somente o endpoint de eventos correspondente;
- resposta com ano `"02026"`: rejeita a representação não exata e não chama `/eventos`;
- resposta vazia: rejeita e não chama `/eventos`;
- combinações cruzadas de ano numérico `2026` e string canônica `"2026"`: continuam aceitas.

## TDD

### RED

Com o driver original, após o teste final estar escrito:

```text
npm test -- tests/portal-driver.test.mjs
1 falhou, 2 passaram, 0 cancelados
```

A falha foi a asserção de que uma resposta sem correspondência exata deveria rejeitar; o fallback aceitou o processo divergente e prosseguiu para eventos. Os dois casos de item sem ID e de correspondência exata passaram, confirmando que o teste exercitava o comportamento real.

### GREEN

Após remover o fallback:

```text
npm test -- tests/portal-driver.test.mjs
6 testes executados
6 passaram
0 falharam
```

## Regressão

```text
npm test
382 testes executados
382 passaram
0 falharam
0 cancelados
```

Também executado:

```text
git diff --check
```

Status: verde, sem erro de whitespace.

## Pacote de referência e escopo Git

Não houve alteração em `Versions/TCE-Meus-Processos-165-e-Setor-156-Extensao-Reorganizada-2026-09-14`. Não foram executados comandos de rede, autenticação, navegação real ou envio.

## Preocupações

- A validação de ano usa igualdade textual após a conversão para string, o que aceita número `2026` e string `"2026"`, mas rejeita strings com padding, como `"02026"`.
- A aceitação final em portal real permanece fora do escopo e não foi declarada.
- O commit desta rodada deve conter somente este relatório, o teste isolado e a alteração mínima do driver; mudanças não relacionadas do worktree não devem ser incluídas.
