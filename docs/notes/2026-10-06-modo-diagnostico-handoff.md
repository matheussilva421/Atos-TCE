# Handoff — Modo Diagnóstico sempre ativo

Data: 2026-10-06  
Status: especificação escrita e em revisão; nenhuma implementação iniciada.

## Objetivo

Implementar o Modo Diagnóstico leve, sempre ON por padrão, descrito no arquivo
de objetivo anexado `goal-objective.md`. Deve observar o fluxo existente da Mesa
à extensão/portal e ao resultado, registrar duração e eventos SLOW, oferecer
estado/pausa/limpeza/exportação na Mesa, limitar retenção e excluir credenciais.
O diagnóstico não pode alterar identidade, qualification, capability gates,
fill, AR-1/AR-2/AR-3 ou o envio manual.

## Estado inicial verificado

- Branch: `codex/area-restrita-reliability-reset`.
- Estado inicial desta etapa: HEAD `1a687e8bdb980257a8bb94ad263bb286d1099199`,
  igual ao upstream e working tree limpa.
- Handoff inicial desta tarefa foi commitado e enviado como `1a687e8`.
- Fonte do runtime portátil: `app/`, `extension/`, `tests/`, `packaging/` e
  `scripts/`. `work/tce-extractor/` é legado/verificador.
- A última referência de release encontrada no handoff existente é
  `AR1_BUILD=88eed8ce...`; qualquer pacote desta implementação precisa ser
  reconstruído com a árvore final commitada, sem reutilizar ZIP antigo.

## Descobertas relevantes

- `app/area_restrita/reliability.py` mantém o ledger de qualification com
  eventos e chaves estritamente validados. Ele remove por desenho dados como
  processo, interessado, cookies, tokens e corpo; adicionar a timeline rica
  nele pode contaminar o avaliador de qualification.
- `app/area_restrita/current_selection.py` mantém o snapshot transitório do
  formulário apenas em memória e documenta que ele não é persistido nem
  registrado. O novo diagnóstico precisa obter somente os dados explicitamente
  autorizados pelo objetivo, com redação de segredos, sem mudar a resolução ou
  a escrita do formulário.
- A Mesa serve `app/web/`; a API e integração com o ciclo de vida ficam em
  `app/api/server.py`; observação/heartbeat/comandos ficam em
  `extension/background/router.js` e `extension/lib/api.js`.
- O builder de `packaging/build-portable.ps1` copia automaticamente `app/` e
  `extension/` para o ZIP portátil.

## Decisão arquitetural registrada para especificação

Manter o ledger de reliability como está e adicionar um recorder local e
limitado sob `data-root`, ligado aos boundaries existentes no servidor,
`FillService`, roteador e filler da extensão. Eventos da extensão acompanham os
payloads existentes de observação/resultado; não haverá workflow de comandos
paralelo. Sessão gerada pelo servidor correlaciona as partes; erros do recorder
são fail-open. A Mesa mostra estado e ações de pausa, retomada, limpeza e
exportação.

Especificação criada em
`docs/superpowers/specs/2026-10-06-modo-diagnostico-design.md`. Define ON no
startup, pausa transitória, retenção de cinco sessões e limite de 8 MiB por
timeline ativa (trim para 6 MiB), eventos allowlisted, redação de segredos,
threshold SLOW de 2.000 ms, endpoints Mesa, UI, ZIP e gates.

## Testes, validação e GitHub

- Testes de produto ainda não executados; nenhuma mudança de código foi feita.
- Especificação revisada contra os campos, export, smoke e DoD do objetivo;
  `git diff --check` passou. A revisão humana da especificação ainda está
  pendente.
- Nenhum smoke sintético, build de ZIP ou CI foi executado nesta etapa.
- Commit/push da especificação e atualização deste handoff: pendentes.

## Retomada

1. Revisar `docs/superpowers/specs/2026-10-06-modo-diagnostico-design.md` e
   incorporar correções solicitadas antes de aprovar.
2. Depois da aprovação da especificação, criar e revisar o plano de
   implementação em `docs/superpowers/plans/`.
3. Implementar na árvore raiz com RED→GREEN por requisito, preservar o fluxo
   atual e atualizar este handoff a cada bloco significativo.
4. Executar os gates da raiz, o smoke sintético especificado e os gates de
   pacote/CI; gerar um ZIP novo a partir do SHA final commitado, verificar seus
   arquivos/hash e registrar o estado final.
