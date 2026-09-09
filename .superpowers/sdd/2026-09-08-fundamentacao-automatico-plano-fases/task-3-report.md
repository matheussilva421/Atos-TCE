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
    `get_events` e `close`.
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
  - Escapa HTML, restringe citações a ID de documento/página, redige tokens,
    cookies, CPF, URLs de sessão e caminhos, e neutraliza células CSV que
    começam com `=`, `+`, `-`, `@`, tab ou quebra de linha.
  - Usa temporários com `flush`/`fsync` e `os.replace`, limpando temporários e
    restaurando o relatório anterior em falha de substituição. Renderizar não
    altera o banco e chamadas repetidas são idempotentes.

- Criados `work/tce-extractor/test_automation_store.py` e
  `work/tce-extractor/test_automation_report.py` com contratos de concorrência,
  recovery fail-closed, idempotência, conflito, rollback, não migração do
  legado, sanitização e atomicidade.

## TDD — RED/GREEN

RED observado antes dos módulos de produção:

```text
python -m unittest test_automation_store test_automation_report -q
Resultado: 11 falhas, 0 aprovados; falha esperada por ausência dos módulos
automation_store.py e automation_report.py.
```

Após a implementação mínima e a correção do import necessário do renderer:

```text
python -m unittest test_automation_store test_automation_report -q
Resultado: 11 testes executados, 11 passaram, 0 falharam.
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
4. Commit funcional: `d3035da`
   (`feat: persist automation events and incremental reports`).

Próxima retomada: revisar este relatório e consumir `AutomationStore` somente
na fase de API, preservando o gate de envio real e executando novamente os
testes de integração após a integração autorizada.
