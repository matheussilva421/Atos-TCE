# Relatório — Fase 3: diário de execução e relatórios duráveis

Data: 2026-09-08
Branch: `codex/fundamentacao-automatico`
Brief seguido: `task-3-brief.md`

## Status

Fase 3 implementada dentro do ownership autorizado. O serviço, a API, a
extensão, o worker, o painel, `prepare_transfer.py` e `package_audit.py` não
foram alterados nem executados para envio. O checkout não possui remoto
configurado; nenhum push foi realizado.

## Implementação

- Criado `work/tce-extractor/portable/app/automation_store.py`.
  - Persiste em `automacao/execucoes.sqlite3` com `journal_mode=DELETE`,
    `synchronous=FULL`, `foreign_keys=ON` e `busy_timeout=5000`.
  - Abre conexão nova e `BEGIN IMMEDIATE` por operação; falhas fazem rollback.
  - Implementa `create_run`, `freeze_queue`, `append_event`, `snapshot`,
    `get_events` (com fence opcional `through`) e `close`.
  - Mantém runs, especificações, revisões, timestamps, itens ordenados,
    eventos globais com sequência por run, comandos extensíveis e atos
    confirmados.
  - Projeta evento e estado na mesma transação; `event_id` repetido com o
    mesmo payload é idempotente e payload divergente é conflito.
  - Rejeita revisão obsoleta, transições inválidas e uma segunda execução ativa
    para a mesma raiz, inclusive entre instâncias concorrentes.
  - Ao reabrir, pausa `discovering`/`running` e converte `send_intent` sem ato
    confirmado em `unconfirmed`, sem ler ou migrar `progresso.json`.

- Criado `work/tce-extractor/portable/app/automation_report.py`.
  - Implementa `render_run_reports(store, run_id, output_root)` nos caminhos
    `relatorios/complementacao/<run_id>/relatorio.html` e `relatorio.csv`.
  - Registra antes/depois, campos, método/origem, releituras, decisão jurídica,
    citações documentais, timestamps, erros, último confirmado e item
    interrompido.
  - Usa allowlist estrutural de payloads e citações (`document_id`, `page_id`,
    `page` e `label`), redaction recursiva de tokens, cookies, CPF textual ou
    numérico, URLs com/sem esquema e caminhos relativos/absolutos, em HTML e
    CSV; neutraliza células CSV que começam com `=`, `+`, `-`, `@`, tab ou
    quebra de linha.
  - Publica uma geração versionada em `.generations/` e troca um manifesto
    atômico junto com os arquivos de compatibilidade `relatorio.html` e
    `relatorio.csv`. Falha em qualquer replace restaura o par anterior; os
    hashes no manifesto impedem aceitar gerações divergentes. Renderizar não
    altera o banco e chamadas repetidas são idempotentes.

- Criados `work/tce-extractor/test_automation_store.py` e
  `work/tce-extractor/test_automation_report.py` com contratos de concorrência,
  recovery fail-closed, idempotência, conflito, rollback, não migração do
  legado, sanitização e atomicidade.

## TDD — RED/GREEN

RED observado antes das correções desta rodada:

```text
python -m unittest test_automation_store test_automation_report -q
Resultado: 22 casos; 1 falha e 16 erros nos contratos novos de redaction,
fence de revisão, manifesto/publicação e replay legado.
```

Após a implementação mínima e a correção do import necessário do renderer:

```text
python -m unittest test_automation_store test_automation_report -q
Resultado: 28 testes executados, 28 passaram, 0 falharam.
```

## Testes e validações

Focais Python existentes relevantes:

```text
python -m unittest test_local_service test_prepare_transfer test_package_audit -q
Resultado: 69 testes executados, 69 passaram, 0 falharam, 3 skips ambientais.
Warnings: ResourceWarning HTTP já emitidos pela suíte; nenhum erro novo.
```

Validações adicionais:

```text
python -m py_compile portable/app/automation_store.py portable/app/automation_report.py test_automation_store.py test_automation_report.py
Resultado: OK.

git diff --check
Resultado: sem diagnóstico.
```

## Rodada de correção pós-revisão independente

Data: 2026-09-09

Foram corrigidos os quatro achados da revisão independente, preservando os
fixes anteriores dos commits `f0e1dc8` e `924cfef`:

- projeção estrutural segura de `last_confirmed` e `interrupted_item`, sem
  payload livre, com redaction endurecida para tokens/cookies, API keys, CPF
  numérico com zero inicial, URLs com/sem esquema e caminhos;
- descarte fechado de citações que não sejam lista de objetos permitidos com
  `document_id`, `page_id`, `page` e `label` seguros;
- recovery preservando a origem da pausa: `discovering` retoma como
  `discovering` e `running` continua retomando como `running`, sem liberar o
  slot de execução ativa;
- leitura de eventos limitada à revisão do snapshot;
- geração versionada validada por SHA-256 e manifesto publicado validado antes
  de qualquer nova substituição; divergências falham fechadamente e deixam a
  geração não publicada;
- erro explícito `LegacyEventReplayError` para replay sem `result_json`.

Os fixes anteriores preservados incluem recovery de `send_intent` em runs
`paused`, terminalidade após `stopped`/`completed`, resultado original em
replay atual, conflito JSON `1` versus `true`, `expected_revision` obrigatório,
pragmas/transações SQLite, concorrência e redaction inicial.

TDD da rodada:

```text
RED por fatia: redaction (1 falha), citações (2 subcasos), recovery discovering
(1 falha) e integridade de geração/manifesto (2 falhas).
GREEN: 28 testes executados, 28 passaram, 0 falharam.
Focais Python: 69 testes executados, 69 passaram, 0 falharam, 3 skips ambientais.
py_compile: OK.
git diff --check: sem diagnóstico.
```

O escopo permaneceu restrito a `automation_store.py`,
`automation_report.py`, seus testes e este relatório. Nenhum serviço, API,
worker, painel, empacotamento, autenticação ou envio real foi alterado ou
executado. A nova coluna `events.result_json` é adicionada de forma compatível
ao abrir bancos existentes; a coluna `runs.paused_from_state` também é
adicionada de forma compatível. Eventos legados sem esse resultado armazenado
falham fechadamente com `LegacyEventReplayError`, sem devolver snapshot
posterior como resultado original.

## Rodada de correção final — revisão independente

Data: 2026-09-09

Foram corrigidos os três achados acionáveis da revisão final, preservando as
correções anteriores:

- sanitização contextual mantém `process_key`/identidades de ato permitidas,
  incluindo `103439/2023`, legíveis no HTML e CSV; caminhos reais continuam
  redigidos;
- citações são descartadas quando não são lista de objetos com `document_id`
  ou `page_id` seguro; `page`, `label` e demais campos só são aceitos como
  derivados de uma dessas identidades;
- `generation` é derivada por helper determinístico dos hashes SHA-256 do HTML
  e CSV e o manifesto falha fechadamente se o identificador divergir, mesmo
  com os arquivos individuais íntegros.

TDD desta rodada:

```text
RED: as três regressões falharam antes da implementação (após corrigir um
fixture que inicialmente não correspondia à identidade congelada).
GREEN: python -m unittest test_automation_store test_automation_report -q
Resultado: 31 testes executados, 31 passaram, 0 falharam.
```

Os testes novos cobrem identidades de ato versus caminhos reais, citações
somente com página/rótulo/string/objeto arbitrário e adulteração do ID de
geração com hashes e arquivos válidos. Nenhum serviço, API, worker, painel,
empacotamento, autenticação ou envio real foi alterado ou executado.

## Arquivos sob alteração

- Criado `work/tce-extractor/portable/app/automation_store.py`.
- Criado `work/tce-extractor/portable/app/automation_report.py`.
- Criado `work/tce-extractor/test_automation_store.py`.
- Criado `work/tce-extractor/test_automation_report.py`.
- Criado este relatório.
- A alteração pré-existente em `.superpowers/.../task-2-report.md` foi
  preservada e não faz parte desta Fase 3.

## Concerns e retomada

1. A integração do store e dos relatórios em `local_service.py`, API, worker,
   painel e empacotamento permanece deliberadamente para fases posteriores.
2. O modelo de `commands` está criado para consumo futuro; `consume_command` não
   foi implementado nesta fase.
3. Nenhum envio real, autenticação de portal ou navegação foi iniciado.
4. Commit funcional anterior: `d3035da`
   (`feat: persist automation events and incremental reports`).
5. Esta rodada será consolidada em `fix: finalize automation report identity and generation validation`.

Próxima retomada: revisar este relatório e consumir `AutomationStore` somente
na fase de API, preservando o gate de envio real e executando novamente os
testes de integração após a integração autorizada.
