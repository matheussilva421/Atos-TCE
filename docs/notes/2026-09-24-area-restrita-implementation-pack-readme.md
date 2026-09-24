# Atos-TCE — Pacote de Implementação da Área Restrita

**Data de revisão:** 2026-09-24  
**Repositório:** `matheussilva421/Atos-TCE`  
**Branch canônica para retomada:** `codex/atos-tce-unified`  
**HEAD verificado no GitHub:** `dcb9086fe5fdffe89022bfc14c07a85e728232df`  
**Relação com `main` no momento da revisão:** 44 commits à frente, 0 atrás.

## Objetivo deste pacote

Este ZIP contém somente os documentos necessários para retomar e concluir:

1. preenchimento Best-Effort + `legal-foundation-v4`;
2. validação real supervisionada do filler;
3. descoberta real da Área Restrita;
4. infraestrutura de Portal Lab com Chrome DevTools MCP + Playwright CLI;
5. ação **Próximo processo**;
6. endurecimento do runtime sem criar dependência de IA/MCP/Playwright no produto final.

## Ordem obrigatória de leitura

1. `01-ESTADO-ATUAL.md`
2. `02-OVERRIDES-E-REGRAS.md`
3. `orchestration/2026-09-24-atos-tce-area-restrita-consolidated-resumption-plan.md`
4. `canonical/2026-09-23-best-effort-form-filling-design.md`
5. `canonical/2026-09-23-best-effort-form-filling-implementation.md`
6. `canonical/2026-09-23-next-process-navigation-implementation.md`
7. `lab/2026-09-24-area-restrita-lab-design.md`
8. `lab/2026-09-24-area-restrita-reverse-engineering-plan.md`

`03-GOAL-CODEX.md` pode ser anexado como Goal junto com os documentos acima.

## Regra principal

**Não reimplementar trabalho já concluído.**

O Best-Effort Tasks 1–9 já está implementado na branch unificada. O primeiro objetivo funcional é fechar a validação real da Task 10 e a Phase 0 do plano de Próximo Processo.

O Portal Lab é infraestrutura de desenvolvimento. Ele não substitui a extensão e não entra no ZIP final do Atos-TCE.

## Resultado final esperado

```text
DESENVOLVIMENTO
Codex + Chrome DevTools MCP + Playwright CLI
                 |
                 v
observação -> fixture -> teste -> runtime

PRODUÇÃO
START.cmd -> Mesa -> extensão MV3 -> Área Restrita
```

O computador final não deve precisar de Codex, ChatGPT, MCP, Playwright CLI, Node ou API de LLM para usar o Atos-TCE.