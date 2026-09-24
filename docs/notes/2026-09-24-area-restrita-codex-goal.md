# Goal — Concluir automação da Área Restrita com Portal Lab

Retome o repositório `matheussilva421/Atos-TCE` a partir da branch canônica `codex/atos-tce-unified`. Leia primeiro `00-LEIA-ME.md`, `01-ESTADO-ATUAL.md`, `02-OVERRIDES-E-REGRAS.md` e o plano consolidado.

Objetivo: concluir o preenchimento Best-Effort já implementado, finalizar a descoberta real da Área Restrita e somente depois implementar “Próximo processo”, usando Chrome DevTools MCP/Playwright exclusivamente como laboratório de desenvolvimento.

Regras:
- NÃO reimplementar Best-Effort Tasks 1–9; elas já estão na branch.
- Primeiro reexecutar baseline completa.
- Criar/validar Portal Lab isolado do runtime.
- Fechar Best-Effort Task 10 com casos reais supervisionados.
- Fechar integralmente Next Process Phase 0 antes de qualquer código de navegação.
- Usar evidência real -> fixture sanitizada -> teste RED -> correção -> GREEN.
- A Mesa escolhe o próximo alvo; a extensão nunca escolhe row por posição.
- Identidade/generation permanecem fail-closed.
- Não resolver navegação apenas aumentando timeout/retry.
- Não automatizar submit/finalização/`Complementar Ato`.
- DevTools MCP/Playwright não podem virar dependência do produto.
- O ZIP final deve funcionar em outro PC sem IA, MCP, Playwright ou Node.

Após fechar Phase 0, execute as Tasks 1–8 do plano de Próximo Processo, faça revisão adversarial, rode Python + extensão + web + `work/tce-extractor/verify-project.ps1` + packaging/smoke, e registre handoff final.