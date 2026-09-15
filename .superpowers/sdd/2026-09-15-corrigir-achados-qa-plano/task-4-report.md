# Task 4 — relatório de implementação

Data: 2026-09-15

## Causa raiz

O painel convertia `citation.document` em documento local e marcava OCR como
`ready`, mesmo quando não havia artefato local nem hash verificável. Isso fazia
um item apenas citado entrar em `eligible`. No backend, `batch_scope` aceitava a
mera presença de documentos e não exigia identidade, hash e evidência mínima
coerentes para `exact` + `ready`. O serviço local expunha apenas o estado
agregado do job; o painel não tinha um contrato seguro de estado por item/lote.

## TDD

### RED

Foram adicionados e executados primeiro os testes mínimos para:

1. citação sem hash/artefato não ser `ready` nem `eligible`;
2. evidência local válida poder ser `ready`;
3. aquisição por item/lote não ser concluída quando o processo do job falha.

O RED observado foi o esperado: a citação era marcada `ready`, o serviço não
possuía o estado `lot` esperado e o painel não preservava a confirmação de
prévia/tamanho. O controle de evidência válida passou antes da implementação.
Um erro de setup do teste usava `root` em vez de `_root`; foi corrigido sem
alterar o comportamento testado.

### GREEN

Implementação mínima aplicada:

- `batch_scope.py` agora exige identidade, hash e `relative_path` seguro ou
  estrutura de evidência produzida para considerar documentos locais coerentes.
  `ready` sem essa coerência é normalizado para `not_run`; aquisição pendente
  continua disponível.
- `panel.js` deixou de derivar evidência de `citation.document`. Só evidência
  local fornecida pelo item, com hash, snapshot e artefato relativo seguro,
  pode produzir `ready`/`eligible`; a exibição inclui estados por item/lote.
- `local_service.py` projeta estado seguro por item/lote usando identificadores
  ordinais, sem paths absolutos, tokens ou PII. Falha do processo mantém lote e
  itens em `failed`, nunca `completed`.
- A confirmação existente permanece imediatamente antes do download. O estado
  do painel registra confirmação, lote e quantidade prevista quando o seam
  seguro está disponível; não foi criado evento persistente novo.

## Verificações

- RED focado: falhou pelos motivos esperados antes da produção; controles
  válidos passaram.
- GREEN focado: Python 3/3 e Node 3/3.
- `node --test` na extensão: 388 testes, 388 passaram, 0 falharam.
- `python -m unittest test_area_restrita_analysis test_local_service -q`:
  34 casos descobertos, 33 passaram, 1 ignorado, 0 falharam.
- `python -m py_compile app/batch_scope.py app/local_service.py`: passou.
- `git diff --check`: passou.

## Limitações e decisões preservadas

- O estado por item é derivado do estado do job até existir persistência
  granular do coletor; não é prova de arquivo individual baixado.
- `batch_scope` valida a forma do caminho relativo, mas não testa existência
  física do arquivo nessa camada pura.
- O worker de análise atual normalmente não fornece evidência local `econtas`,
  então o estado permanece pendente até o pipeline de aquisição alimentar esse
  contrato.
- A confirmação fica em estado de UI; não há ledger/event seam seguro para
  persistência adicional.
- `auto_submit`, envio e o pacote `Versions` não foram alterados.
- Não foram executados gates reais do portal; continuam fora do escopo local da
  Task 4.

## Git e retomada

Alterações limitadas aos arquivos de propriedade da Task 4. Commit local será
criado após a verificação final; nenhum push será feito. Para continuar,
consultar este relatório, revisar `git status` e repetir apenas os gates
focados se o worktree mudar.
