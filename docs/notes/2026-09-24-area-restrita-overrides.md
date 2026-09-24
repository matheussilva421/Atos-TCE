# Overrides e regras de retomada

Este arquivo resolve instruções históricas que ficaram desatualizadas depois da reconciliação Git de 24/09.

## 1. Branch

Instruções antigas que dizem:

```text
promover codex/mesa-local-refactor para main
criar branch de implementação a partir do main promovido
```

já foram superadas pelo histórico posterior.

**Agora use `codex/atos-tce-unified` como base canônica de desenvolvimento.**

Antes de trabalhar:

```powershell
git fetch origin --prune
git switch codex/atos-tce-unified
git pull --ff-only origin codex/atos-tce-unified
git status --short
git rev-parse HEAD
```

Não mergear em `main` antes dos gates reais finais.

## 2. Best-Effort

Os passos de implementação das Tasks 1–9 do plano de 23/09 são referência e contrato histórico, não uma fila para repetir.

Use-os para:

- conferir invariantes;
- entender interfaces;
- localizar testes;
- revisar regressões.

O trabalho novo começa pela Task 10 real.

## 3. Próximo Processo

A Phase 0 continua sendo hard gate.

O Portal Lab novo deve ser usado para completar a Phase 0. Ele **não** autoriza pular discovery.

## 4. Portal Lab

Chrome DevTools MCP e Playwright CLI:

- são ferramentas de investigação/QA;
- podem se conectar ao Chrome dedicado autenticado via CDP;
- não substituem a extensão;
- não entram em `app/`, `extension/` como dependência;
- não entram no pacote portátil.

## 5. Regra de TDD para portal real

Toda divergência descoberta no portal segue:

```text
observação real
 -> sanitização
 -> fixture
 -> teste RED
 -> correção mínima
 -> teste GREEN
```

Não editar runtime por intuição.

## 6. Timeouts

Não corrigir problema de frame/navegação apenas aumentando `delay`, `retry` ou `timeout`.

Primeiro identificar o predicado estrutural que representa o estado esperado. Timeout é limite superior, não detector principal de estado.

## 7. Próximo alvo

A Mesa escolhe a identidade do próximo processo.

A extensão recebe o alvo explícito e apenas navega até ele.

Proibido:

- selecionar “a próxima row”;
- usar vizinho visual como fallback;
- escolher primeiro frame em caso de ambiguidade;
- wrap automático no fim da fila.

## 8. Clique final

Nenhum documento deste pacote autoriza automatizar:

- `Complementar Ato` final;
- submit;
- send;
- finalize;
- assinatura;
- tramitação.

Quando um gate exigir observar o resultado final, o operador executa manualmente e a automação apenas observa o estado posterior.

## 9. Privacidade

Não versionar:

- HAR/trace bruto;
- perfil Chrome;
- cookies;
- tokens;
- CPF;
- nomes/processos reais em fixtures;
- capturas raw.

Fixtures versionadas devem ser sanitizadas.

## 10. Portabilidade

O ZIP final deve funcionar sem:

- Codex;
- ChatGPT;
- MCP;
- Playwright CLI;
- Node.js;
- chave/API de LLM.

O Portal Lab fica fora do artefato de distribuição.