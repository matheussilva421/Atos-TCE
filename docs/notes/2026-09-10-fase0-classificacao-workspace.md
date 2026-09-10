# Fase 0 — classificação do workspace e proposta de quarentena

Data: 2026-09-10
Manifesto: `tmp/fase0/workspace-manifest-r2.json`
Estado: aguardando aprovação humana antes da Tarefa 0.8

## Evidência medida

- Escopo físico observado: 109.050 arquivos e aproximadamente 45,3 GB.
- Manifesto seguro: 29.559 entradas; schema fechado de 10 campos validado em
  todas as entradas; `git_state_source=queried`.
- Enumeração parcial intencional: 4 diretórios não puderam ser enumerados e
  ficam automaticamente em `proibido remover` até investigação individual.
- Privacidade: zero CPF, Bearer, token/cookie/API key atribuídos no JSON; as
  referências registram somente caminho e linha e não apontam para diretórios
  privados.
- Classes: 20.120 duplicatas byte a byte, 5.950 desconhecidos, 2.826 caches ou
  stagings, 259 dados privados, 195 documentos, 145 fontes, 38 perfis/sessões e
  26 entregas candidatas/autorizadas.
- Os 20.120 arquivos duplicados não são aprovação para remoção individual:
  somente diretórios completos explicitamente relacionados abaixo poderão ser
  movidos pela futura simulação.

## Decisão proposta

| Decisão | Alvos | Tamanho estimado | Regra |
|---|---|---:|---|
| reter | `.git`, fontes e docs versionadas, `.gitignore`, `.gitattributes` | necessário | nunca mover |
| reter | `tmp/fase0-recovery`, `tmp/fase0` e evidência live do lote 1 | necessário | preservar até o encerramento |
| reter | `outputs/TCE-Acervo-Atualizado-227-2026-09-05.zip` | 1.737.402.229 B | cópia canônica do acervo de 05/09 |
| reter | pacote `fase11k`, extração atual e evidência `live-real-fase11h-sector-lot50` | necessário | entrega/runtime/evidência canônicos |
| reter | pacote completo `v6` e extensão `v5` em `artifacts` | 1.739.071.285 B | últimas entregas de cada série |
| reter | `.codex-remote-attachments` e anexos originais ainda referenciados | necessário | evidência original |
| quarentenar | `work/tce-extractor/.package-staging-*` | 10.298.032.216 B | montagens reproduzíveis |
| quarentenar | `work/tce-extractor/staging*` | 2.530.773.380 B | staging reproduzível |
| quarentenar | `work/tce-extractor/qa-extracted-*` | 1.440.437.100 B | extrações de QA reproduzíveis |
| quarentenar | `work/tce-extractor/tmp` | 267.507.466 B | temporários reproduzíveis |
| quarentenar | `work/chrome-qa-*`, `work/chrome-html-qa*` | 33.033.390 B | perfis/saídas de QA não ativos, após checagem de processo |
| quarentenar | `tmp/verify-release-integrated` | 262.377.072 B | extração de verificação reproduzível |
| quarentenar | `.worktrees` | 0 B | nenhum worktree registrado; prune dry-run vazio |
| duplicata | ZIP de 05/09 na raiz | 1.737.402.229 B | idêntico à cópia canônica, SHA-256 `a621791800a24ab6292b755d473aef6b3f407e167a4bf4beb8272acb68ff1720` |
| quarentenar | pacotes completos históricos `v2`–`v5` e extensões `v2`–`v4` em `artifacts` | 6.955.572.934 B | versões anteriores; últimas versões retidas |
| investigar | `portable/`, `work/tce-downloads`, saídas antigas e demais itens desconhecidos | 527.696.588 B no manifesto | não mover nesta rodada |
| proibido remover | dados privados, `.chrome-work*`, perfis, locks e 4 diretórios não enumerados | necessário | preservar sem exceção automática |

Total máximo desta proposta: 23.525.135.787 bytes (21,91 GiB), sempre por
movimento recuperável para quarentena. Não há autorização para purge.

## Gate humano

A aprovação desta tabela autoriza apenas implementar o limpador, expandir os
padrões acima para caminhos existentes exatos e executar o `WhatIf`. O `Apply`
continuará bloqueado até a revisão das contagens e bytes do `WhatIf`, conforme o
plano. Itens em `investigar`, `reter` ou `proibido remover` não entram no recibo.
