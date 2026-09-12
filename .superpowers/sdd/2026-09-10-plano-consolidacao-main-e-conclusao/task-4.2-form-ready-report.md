# Task 4.2 — relatório da correção de registro tardio

Data: 2026-09-12
Brief de autoridade: `.superpowers/sdd/2026-09-10-plano-consolidacao-main-e-conclusao/task-4.2-form-ready-brief.md`

## Status

GREEN para a correção offline do bloqueio técnico de `FORM_READY`. O content
script agora registra um formulário que surge depois da injeção, sem alterar o
fluxo de portal, o pacote live ou as operações de preenchimento/envio.

## Escopo e arquivos

Arquivos de ownership alterados:

- `work/tce-extractor/portable/extensao-complementar-ato/content/form-detector.js`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/form-detector.test.mjs`

Relatório criado neste arquivo.

Nenhum arquivo de portal-navigation, background, panel, manifest, bridge,
dados ou saída live foi alterado. As alterações concorrentes já existentes em
`.superpowers/sdd/2026-09-10-plano-consolidacao-main-e-conclusao/progress.md`,
`docs/notes/2026-09-10-plano-consolidacao-main-e-conclusao.md` e
`docs/notes/2026-09-11-fase42-reconciliacao-handoff.md` permaneceram fora do
índice e não foram revertidas.

## Implementação

- Mantido o envio imediato de `FORM_READY` quando o conjunto completo já existe
  na injeção.
- Para um documento inicialmente incompleto, instalado `MutationObserver`
  usando a janela do documento ou o fallback global, observando alterações de
  filhos, subárvore e atributos.
- O callback somente envia depois de confirmar sentinelas completas e
  formulário visível; lê `locationRef.href` no momento do registro e gera um
  novo request id.
- `readySent` e `disconnect()` impedem mensagens duplicadas e encerram a
  observação após o registro.
- O observador também é encerrado quando o documento deixa de ser utilizável;
  instalação em documentos não-browser ou sem observer falha fechada e não
  cria timer de polling.
- O roteamento de mensagens, os guards de visibilidade do snapshot e os guards
  de escrita permaneceram inalterados.

## Evidência TDD

RED antes da implementação:

```text
node --test --test-name-pattern="registers a late complete form exactly once" tests/form-detector.test.mjs
1 teste executado; 0 passou; 1 falhou.
Falha esperada: observers.length era 0, mas o teste exigia 1 (0 !== 1).
```

GREEN focal após a implementação:

```text
node --test --test-name-pattern="registers a late complete form exactly once" tests/form-detector.test.mjs
1 teste executado; 1 passou; 0 falhou.
```

## Gates finais

```text
node --test tests/form-detector.test.mjs
28 testes executados; 28 passaram; 0 falharam.

npm test
340 testes executados; 340 passaram; 0 falharam.

git diff --check
exit code 0; nenhuma ocorrência.

git show --check --stat --oneline HEAD
exit code 0; commit sem erro de whitespace.
```

## Git e continuidade

Commit local da implementação e do teste:

```text
4cb0ebc7e9b5aca9335275a635abead70d152ea3
```

O commit contém somente os dois arquivos de ownership. A branch local `main`
está 1 commit à frente de `origin/main`; não foi feito push. O relatório é
documentação obrigatória deste bloco e deve ser commitado separadamente sem
incluir as três alterações concorrentes.

## Validação manual, pendências e preocupações

- Foi feita revisão do diff e dos nomes staged; não houve navegação no portal.
- Não foram executados `APPLY_FIELDS`, preenchimento, envio, finalização ou
  qualquer alteração no pacote live.
- A validação autenticada real e os três preflights de Task 4.2 continuam
  pendentes por estarem fora do escopo autorizado nesta execução; portanto este
  GREEN não qualifica o fluxo live.
- Em ambientes sem `MutationObserver`, o comportamento tardio não é
  simulado por polling e permanece não registrado, conforme o requisito de não
  introduzir timer ilimitado.

Para retomada: preservar as três mudanças concorrentes, revisar/commitá-las
separadamente conforme o owner correspondente e, somente com autorização
específica, executar a validação real no Chrome de trabalho isolado.
