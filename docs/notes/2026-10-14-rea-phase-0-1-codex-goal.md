# GOAL 01 — Atos-TCE + REA: Fases 0–1 (Laboratório Sintético e Evidence Gateway)

**Status:** AUTORIZADO PARA EXECUÇÃO PELO CODEX; NÃO INICIADO NESTA PUBLICAÇÃO.  
**Aprovação humana:** 2026-10-14.  
**Método obrigatório:** Superpowers `subagent-driven-development`, com `using-git-worktrees`, TDD RED→GREEN, revisão independente de cada tarefa e revisão de segurança/qualidade ao final.  
**Escopo restrito:** Tasks 0–8 do primeiro plano; exclusivamente laboratório sintético.

## Objetivo

Implemente integralmente o plano aprovado de Fases 0–1: reconcilie a fonte de verdade e o baseline e entregue laboratório de investigação REA com execução controlada, Evidence Gateway pré-egresso, coordenação exclusiva de navegador, cenários sintéticos e testes de isolamento. Preserve as decisões arquiteturais D1–D10. **Não acesse nem automatize o portal real do TCE/RN, mesmo em modo de observação.**

## Fontes de verdade, em ordem obrigatória

1. `AGENTS.md` — árvore de produção, fontes reais, limites de segurança.
2. `docs/superpowers/specs/2026-10-14-atos-tce-rea-reliability-architecture-design.md` — especificação aprovada, decisões D1–D10.
3. `docs/superpowers/plans/2026-10-14-rea-atos-tce-phase-0-1-laboratory-plan.md` — plano de implementação **aprovado**, Tasks 0–8, interfaces, testes e passos verificáveis.
4. `docs/superpowers/specs/2026-09-30-area-restrita-reliability-reset-design.md` — Reliability Reset e qualificação.
5. `docs/superpowers/specs/2026-10-06-modo-diagnostico-design.md` — telemetria, limites e retenção.
6. `docs/notes/2026-09-30-area-restrita-runtime-source.md` — fonte canônica e baseline histórico; valide o estado atual antes de depender dele.

**Branch documental de referência:** `codex/2026-10-14-rea-superpowers-architecture-spec`.  
**PR documental:** https://github.com/matheussilva421/Atos-TCE/pull/7  
**Branch de implementação sugerida:** `codex/rea-lab-phase-0-1` em worktree isolada, derivada da revisão documental aprovada. Verifique existência e SHA antes de criar; não sobrescreva branches, worktrees ou alterações locais. Não faça merge em `main`.

A especificação prevalece sobre ambiguidades do plano, e as restrições de segurança do projeto prevalecem sobre ambas. Divergências materiais devem ser registradas como ruling com justificativa e efeito; nunca ampliar o escopo por conta própria.

## Estratégia de execução (sem pausas desnecessárias)

Use explicitamente `superpowers:subagent-driven-development` para executar, em ordem, as Tasks 0, 1, 2, 3, 4, 5, 6, 7 e 8, respeitando seus respectivos critérios de conclusão.

- Prepare worktree isolada via `superpowers:using-git-worktrees`; registre a base, estado Git e o workspace/ledger SDD específico deste plano antes de alterar arquivos.
- Para cada tarefa: despache implementador com contexto mínimo e requisitos exatos do task brief; execute teste RED demonstrando falha pertinente; implemente correção mínima; execute GREEN; obtenha commit e relatório do implementador.
- Depois de cada tarefa: gere pacote de revisão do diff **da base anterior da tarefa até o HEAD**, submeta a revisor independente para conformidade com spec e qualidade; resolva achados e reavalie antes da próxima tarefa.
- Use modelos e reasoning effort explicitamente conforme a skill e os recursos efetivamente disponíveis. Subagentes não podem despachar outros subagentes nem manipular o navegador em paralelo.
- Atualize o ledger e o handoff com SHA, testes, dificuldades, decisões e limitações. Não execute duas tarefas de escrita paralelamente sobre a mesma árvore.
- Ao fim da Task 8, solicite revisão **de todo o diff da fase** por revisor independente, incluindo ameaça de exfiltração, concorrência/fencing, regressões e limites de runtime. Corrija findings de segurança antes de considerar a fase aceita.
- Pode avançar entre tarefas previstas no plano sem me consultar individualmente; **pare após o handoff final** e submeta a fase inteira para minha revisão. Não comece a Fase 2 nem invoque automaticamente um novo writing-plans.

## Entregas técnicas esperadas

| Task | Entrega |
|---|---|
| 0 | Worktree, baseline, source-of-truth, gates e recibo documental |
| 1 | Política estrita para cenários REA apenas em localhost sintético |
| 2 | `Evidence Gateway` com projeções tipadas, allowlist e falha segura |
| 3 | Coordenador com lease exclusivo, fencing e bloqueio de resultado incerto |
| 4 | Runner REA com versão fixa, subprocesso isolado e nenhum stdout/stderr bruto entregue ao agente |
| 5 | Fixtures de frames/FORM/LOGIN_REQUIRED/ACCESS_DENIED e smoke sintético com confinamento de rede |
| 6 | Atestação do isolamento real entre captura e agente; sem alegações falsas de proteção |
| 7 | Gates para impedir entrada de ferramentas e capturas do laboratório no ZIP portátil |
| 8 | Handoff, matriz de testes, revisão de segurança, SHA e decisão de avanço/bloqueio |

O plano define os arquivos e assinaturas exatos. **Não substitua suas Tasks por uma implementação genérica.**

## Restrições absolutas

1. **Portal real proibido nesta fase**: não abrir a Área Restrita/e-Contas; não conectar CDP a sessão real; não usar perfil autenticado; não coletar processos, interessados, CPF, matrícula, PDFs, HTML privado, HAR, cookies ou tokens; não executar comandos sobre atos reais.
2. **Autonomia investigativa D2 permanece**, porém limitada aqui a fixtures sintéticas. O REA deve ser fixado/verificado em `rea-agents@6.5.0`; não usar `@latest` silenciosamente. Node compatível com o `engines` publicado; sem instalação global não autorizada e sem registro irrestrito de REA como MCP do agente que lida com evidência real.
3. Evidência bruta só pode existir em spool restrito e ignorado pelo Git; todo resultado apresentado a Codex deve atravessar o Gateway. Se o agente e o processo de captura tiverem o mesmo principal com leitura irrestrita ou acesso direto a shell/CDP/MCP, **não declarar isolamento comprovado**.
4. `real_capture_enabled=false` durante TODA esta fase, inclusive após testes sintéticos verdes. Falta de isolamento externo, confinamento ou dependência pinada é `BLOCKED`, não `PASS`; registre o bloqueio e preserve o restante do trabalho seguro.
5. Chrome QA com owner único, fencing verificável e nenhuma repetição cega de comandos após `accepted_unconfirmed`. Não fechar navegador externo, apagar locks ou provocar mudança de perfil. Nesta fase, somente Chrome de fixture não autenticado.
6. Não alterar mecanismos de `DiagnosticRecorder`, `ReliabilityRecorder`, motor jurídico, automação MV3 produtiva, `START.cmd`, banco SQLite ou código legado para atender a este GOAL. Ajuste de guardas de packaging só se necessário e com RED prévio.
7. Não incorporar REA, Codex, MCP ou IA ao runtime portátil. Sem automação de login, credenciais, envio, assinatura, finalização ou clique **Complementar Ato**. Preserve fallback manual e comportamento fail-closed.
8. Os gates de **20/20 real-dev + 20/20 portátil** continuam obrigatórios *por capacidade*, mas **não são executados nem satisfeitos nesta fase**. Testes offline jamais promovem `QUALIFIED` ou `PRODUCTION`.
9. Dados privados nunca devem ser publicados; não incluir artefatos brutos em commit, CI, issues ou PR. `main` permanece inalterada; nenhum merge/force push/limpeza destrutiva.

## Gates finais para o handoff

Entregue: branch e worktree, commits, `git diff --stat` e SHA; relatório de RED→GREEN por tarefa; totais de testes Python/Node/web/packaging conforme ambiente; smoke REA sintético `PASS` ou `BLOCKED` justificado; auditoria explícita de rede, spools, credenciais, egressos e bypass; verificação do ZIP/runtime; relatório de revisor independente; achados pendentes com severidade e próximos requisitos.

A fase só é considerada **completa** se os critérios de aceitação forem demonstrados; caso o REA real sintético ou o isolamento não possam ser comprovados, registre a entrega como **PARCIAL/BLOCKED**, não mascare o bloqueio. A autorização de testes reais exigirá outro gate, autorização expressa e revisão da fronteira de segurança.

**Critério de encerramento:** publicar a branch de implementação separada, apresentar um handoff auditável para minha revisão e **PARAR**. Não efetuar merge; não iniciar Fase 2; não abrir o portal real.
