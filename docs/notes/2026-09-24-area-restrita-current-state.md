# Estado atual canônico — 2026-09-24

## Retomada atual — 2026-09-26

Este bloco é a fonte de estado atual; os registros abaixo são cronológicos e podem conter estados antigos.

- Branch única: `codex/atos-tce-unified`; último commit funcional publicado: `bf35ba2b7192d4872d735175ace9143d94ba188d` (Task 5), push aceito em `origin/codex/atos-tce-unified`.
- Phase 0 foi encerrada por equivalência de evidências, conforme a decisão registrada adiante. Tasks 1–5 de Próximo Processo estão implementadas e publicadas.
- Task 4 retorna pelo único link nativo observado (`A.tabs-inner`, rótulo exato), após confirmar a identidade atual; não altera o marcador e recusa controles ausentes ou ambíguos.
- Task 5 acrescenta “Próximo processo →” ao painel; conserva a identidade atual em memória, encaminha somente os dois campos compostos pelo service worker e aguarda a releitura exata do destino antes de declarar pronto. Timeout após aceite mantém a ação bloqueada para evitar duplicatas e instrui conferência manual.
- O usuário autorizou uma execução do botão oficial de análise. A tentativa retornou `session_required`; não houve varredura nova persistida. Não repetir nem buscar a mesma leitura por outra interface.
- Task 5 passou os testes focais, suíte completa da extensão e gates gerais; a validação de navegação live continua pendente porque o scan autorizado respondeu `session_required`.
- Best-Effort Task 10, Tasks 6–8, validação supervisionada, revisão adversarial e pacote standalone seguem pendentes. O clique final permanece manual.

## Git

Branch de retomada:

```text
codex/atos-tce-unified
último commit funcional bf35ba2b7192d4872d735175ace9143d94ba188d
```

No momento da revisão, o commit funcional está publicado e a branch está **137 commits à frente de `main` e 0 atrás**.

Não recriar as antigas branches de implementação como fonte de verdade. A reconciliação de 24/09 consolidou o trabalho relevante na branch unificada.

## Best-Effort / Legal v4

### Implementado e coberto por testes

- catálogo canônico de opções legais selecionáveis;
- `legal-foundation-v4` com melhor opção disponível determinística;
- preflight best-effort por campo;
- valores divergentes existentes preservados;
- formulário legível mesmo com controle de conteúdo individual ausente;
- filler por campo;
- `field_results`;
- stale generation com uma releitura/replanejamento;
- resultado parcial sem corromper status documental;
- processo permanecendo `PRONTO` quando ainda existem pendências;
- UI da Mesa com alterados/preservados/revisar;
- integração backend/extensão.

**Não executar novamente Tasks 1–9 como trabalho novo.**

### Pendente

Task 10: **validação supervisionada no portal real**.

Faltam os cinco casos legais reais e o caso operacional no qual um campo falha mas campos independentes continuam sendo preenchidos.

Nenhum clique final deve ser automatizado.

## Próximo Processo

Tasks 1–3 de Próximo Processo estão implementadas; a Phase 0 foi encerrada por equivalência de evidências em 2026-09-26, como registrado na atualização abaixo.

### Evidência já obtida

```yaml
navigation_strategy: native_control
marker_restore: not_needed
```

Foi observado que o controle nativo `Proc./ Doc. Eletrônicos` retorna do formulário à lista nas amostras e preserva o marcador observado.

Também foram observados:

- lista e quadro de botões em frames distintos;
- abertura por identidade;
- transição lista -> ato -> interessado -> formulário;
- travessia de fronteira de página;
- interessado único em casos amostrados;
- retorno nativo aproximado em ~1,2 s;
- navegação manual para formulário em amostras de ~3,0 a 4,9 s.

### Gates ainda abertos na revisão inicial de 24/09 (histórico)

1. obter `SCAN_PAGE` vivo da Mesa/extensão atual;
2. confirmar valor bruto vivo do marcador;
3. explicar/reconciliar `1198` itens do scan salvo versus `1197` observados;
4. observar retorno após clique final realizado manualmente pelo operador;
5. medir baseline estrita após ato concluído/revisado;
6. observar caso multi-interessado se houver caso controlado disponível;
7. fechar e commitar a nota de discovery.

O bloqueio acima foi substituído pela decisão de encerramento equivalente registrada em 2026-09-26.

## Baseline registrado na reconciliação

No handoff de reconciliação de 24/09 foram registrados:

- Python: 616 executados, 615 aprovados, 0 falhas, 1 skip;
- extensão: 145 aprovados;
- web: 28 aprovados;
- `verify-project.ps1`: todos os sete estágios verdes;
- `git diff --check`: verde.

Reexecutar esses gates no HEAD atual antes de qualquer nova implementação.

## Segurança preservada

- não existe novo submit/finalize automático;
- identidade e generation continuam guardas globais;
- alvo ambíguo não pode ser escolhido por ordem de frame;
- valores de select devem pertencer ao catálogo atual;
- o clique final de **Complementar Ato** continua manual.

## Atualização de gate — 2026-09-26

Phase 0 está **encerrada por equivalência de evidências reais**, conforme decisão e justificativa em `2026-09-23-area-restrita-next-navigation-discovery.md`. O scan vivo adicional desta sessão retornou `session_required`; não foi buscado por outra interface. Scans completos anteriores, ordem observada entre páginas, reconciliação, preservação de marcador/retorno nativo e releitura da identidade são suficientes para iniciar a implementação com guardas fail-closed. O pós-clique manual e um caso multi-interessado não são hard gates para esta navegação; qualquer ambiguidade/stale deve recusar alvo. Best-Effort Task 10 permanece pendente e o clique final permanece humano.

Task 1 de Próximo Processo foi implementada e validada em TDD: a Mesa resolve o próximo alvo elegível na ordem do scan, com identidade composta e contexto literal do marcador; alvos stale/ambíguos/incoerentes falham fechados. Tasks 2–8, validação real da navegação, revisão adversarial e pacote standalone continuam pendentes.

Task 2 foi implementada em TDD: `POST /api/v1/portal/next-act` recebe `process_id` sob sessão Mesa ou identidade composta sob credencial da extensão; só o backend resolve/enfileira o alvo, e identidade ausente/ambígua falha com 409. A requisição não navega nem preenche o portal. Testes: backend focal 14/14, API completa 99/99, extensão API 15/15. Tasks 1 (`5acb0d6`) e 2 (`5510362`) estão publicadas em `codex/atos-tce-unified`. Próximo: Task 3, protocolo `OPEN_NEXT_ACT` e roteador da extensão.
