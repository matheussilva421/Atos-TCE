# Atos-TCE — Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Executar a spec aprovada de 20/10/2026 por fases independentes e testáveis, sem automatizar a conclusão de atos.

**Architecture:** Mesa/SQLite é fonte oficial; JSON v2 é a fonte primária e imutável de dados na extensão MV3; API autenticada serve somente observações, eventos e consultas excepcionais. REA e ferramentas do Portal Lab são exclusivamente de desenvolvimento.

**Tech Stack:** Python 3/unittest, SQLite, JavaScript ES modules/Node node:test, Chrome/Edge MV3, web UI nativa, Windows/PowerShell, CDP/Playwright/REA no QA.

**Spec:** `docs/superpowers/specs/2026-10-20-atos-tce-mesa-extensao-json-portal-lab-design.md` (aprovada formalmente; commit inicial `18131a1`).

## Global Constraints

- **Não implementar durante o writing-plans.** Nenhum merge, lançamento ou ativação de capability sem gates e autorização posterior.
- Ler `AGENTS.md`. O runtime é a árvore raiz (`app/`, `extension/`, `tests/`, `packaging/`, `scripts/`); `work/tce-extractor/` não é a fonte da aplicação distribuída.
- **Allowlist exata de escrita:** `modalidade`, `data_publicacao_doe`, `cargo`, `matricula`, `data_nascimento`. `tipo_processo` somente metadado; `fundamento_legal` e `genero` sem escrita ou preflight obrigatório.
- Operador autentica e conclui no portal; nenhuma ferramenta ou extensão clica envio final, assina, tramita ou lê/reutiliza credenciais.
- JSON v2 contém inventário integral do lote escolhido, interessados vinculados, checksum canônico validado e importação atômica de um lote ativo; reexportação/reimportação manuais.
- JSON exato e parcial **não consulta Mesa**; só processo ou interessado ausente autoriza lookup excepcional; offline permite preencher via JSON.
- Fail-closed para identity, frame, tab, nonce, generation, select, divergência e sessão; sem fill por detecção automática.
- Dados sensíveis, snapshots brutos, tokens, cookies, HAR e traces reais jamais entram no Git ou no ZIP. DevTools MCP/Playwright/REA/mitmproxy não são dependências do runtime.
- Reliability Reset obrigatório: **20/20 tentativas reais consecutivas na mesma build** para QUALIFIED e **20/20 no artefato portátil/Chrome normal** para PRODUCTION, por capability afetada. Testes offline não equivalem a esse gate.
- Toda task de código exige RED explícito, GREEN mínimo, regressão, commit próprio, fresh reviewer independente e correção/re-review de P0/P1 antes da próxima task.

## Review Focus

1. Service worker reinicia entre escrita e troca de lote JSON: lote staged não assume ACTIVE sem reconciliação (F1).
2. Duas abas/formulários com identidades distintas: alternar para Mesa não altera o destino, resposta antiga não preenche outro interessado (F2).
3. Portal ainda exige fundamentação legal manual: campo não é escrito nem tratado como êxito do preenchimento dos cinco (F0/F1/F4).
4. Fila de conclusão após Mesa offline e chave de proteção indisponível: não fabricará prova nem apagará pendência (F4).
5. Rascunho entra em conflito entre comparação e Salvar: CAS recusa sem descartar edição (F3).

## Sequenciamento e arquivos

| Fase | Plano detalhado | Resultado e dependência |
| --- | --- | --- |
| F0 | `2026-10-20-atos-tce-f0-contrato-json.md` | Cinco campos, exportador/sha JSON v2, adaptação sem perda histórica |
| F1 | `2026-10-20-atos-tce-f1-extensao.md` | Extensão JSON-first, lote atômico, preenchimento seguro; requer F0 |
| F2 | `2026-10-20-atos-tce-f2-acompanhamento.md` | Acompanhamento último formulário, eventos, lookup; requer F0/F1 |
| F3 | `2026-10-20-atos-tce-f3-mesa.md` | Mesa de duas colunas, PDF, drafts e merge; requer F0/F2 |
| F4 | `2026-10-20-atos-tce-f4-conclusoes.md` | Conclusão comprovada, fila durável e fechamento humano; requer F2/F3 |
| F5 | `2026-10-20-atos-tce-f5-portal-lab.md` | REA/Portal Lab, investigação, qualification, packaging; L0 antecede testes reais de todas as fases |

F5-L0 é uma **pré-condição transversal**, não autorização de varredura real. F0–F4 podem ser implementadas offline com fixtures fictícias. L1/L2 exigem aprovação própria e L3 é sempre proibido para ferramentas.

## Fronteiras entre planos

- F0 define o esquema v2 e hashes golden Python/JS; F1 valida e importa exatamente esse esquema.
- F1 retorna `EXACT_JSON`, `NEEDS_MESA` ou `BLOCKED`; F2 implementa lookup para NEEDS_MESA. F1 não mistura fontes.
- F2 usa `app/area_restrita/current_selection.py` e `extension/background/router.js`, conservando o canal autenticado e seus controles de origem; eventos de fill são descartáveis.
- F3 só projeta a seleção e mantém drafts fora do workspace portátil, sem disponibilizá-los ao fallback.
- F4 só persiste conclusão inequívoca reconhecida após ação final **humana**; o encerramento do processo é outro ato, manual, na Mesa.
- F5 eleva evidência observada a fixture sanitizada -> teste RED -> correção mínima -> GREEN -> benchmark real -> reviewer e gates.

## Gate de entrada futuro (somente depois do aceite deste plano)

- [ ] Criar worktree isolado na branch de execução aprovada; ler spec, `AGENTS.md` e todos os planos.
- [ ] Verificar `START.cmd`, builder e root source; não alterar árvore legada por engano.
- [ ] Registrar baseline: `python -m unittest discover -s tests -p "test_*.py" -q`; `(cd extension && node --test)`; `node --test app/web/tests/*.test.mjs`; `packaging/verify-package.ps1` quando artefato existir.
- [ ] Conferir bloqueios RELIABILITY e ausência de qualquer comando `SUBMIT`, `SEND` ou `FINALIZE`.
- [ ] Se baseline vermelho ou source divergir, documentar blocker e reconciliar antes do primeiro RED.

## Gate final por fase

- [ ] Testes RED/GREEN e regressões demonstrados em logs sanitizados; review independente concluído, P0/P1 resolvidos.
- [ ] Commit por task e handoff datado em `docs/notes/` com SHA, testes e estado real/não observado.
- [ ] `git diff --check`, testes raiz/extension/web e contrato ZIP; nada confidencial no diff.
- [ ] Capability permanece UNQUALIFIED/EXPERIMENTAL até cumprir 20/20+20/20 no portal sob supervisão.
- [ ] Nenhum merge, push para main, instalação em produção ou release automática.

## Aceite e método

Este master e os seis planos são **documentação**, não aprovação de execução. Apresentar ao usuário para revisão e escolher método Superpowers: preferir **subagent-driven-development**, com um implementador e um reviewer novos por task e revisão de branch completa. A execução futura exige aceite explícito.
