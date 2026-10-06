# Handoff — Modo Diagnóstico sempre ativo

Data: 2026-10-06  
Status: aguardando revisão do desenho; nenhuma implementação iniciada.

## Objetivo

Implementar o Modo Diagnóstico leve, sempre ON por padrão, descrito no arquivo
de objetivo anexado `goal-objective.md`. Deve observar o fluxo existente da Mesa
à extensão/portal e ao resultado, registrar duração e eventos SLOW, oferecer
estado/pausa/limpeza/exportação na Mesa, limitar retenção e excluir credenciais.
O diagnóstico não pode alterar identidade, qualification, capability gates,
fill, AR-1/AR-2/AR-3 ou o envio manual.

## Estado inicial verificado

- Branch: `codex/area-restrita-reliability-reset`.
- HEAD: `46d7538cf0c21e0c5adb3c3d9242fd8bcab5e166`, igual a
  `origin/codex/area-restrita-reliability-reset` no início desta etapa.
- Working tree limpa; nenhuma alteração de produto ou documentação feita antes
  deste handoff.
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

## Desenho proposto — ainda não aprovado

Manter o ledger de reliability como está e adicionar um recorder de diagnóstico
local e limitado sob `data-root`, ligado aos boundaries que já existem no
servidor e na extensão. Um identificador da sessão da Mesa correlacionaria os
eventos enviados pela extensão; falha ao registrar diagnóstico não deve alterar
o fluxo funcional. A Mesa exibiria estado agregado e ações de pausa, retomada,
limpeza e exportação. A exportação seria montada sob demanda com timeline,
ambiente, resumo, logs derivados por componente e última sessão.

O padrão de startup será ON; pausa é temporária e um reinício inicia ON. O
recorder conservará no máximo cinco sessões e um limite de tamanho por sessão.
O schema permitirá os campos de processo/formulário pedidos, mas filtrará nomes
de chaves e valores que representem senha, cookie, Authorization, Bearer,
extension token ou segredo equivalente. URL perderá query/fragment. A proposta
é marcar `SLOW` a partir de 2.000 ms.

## Testes, validação e GitHub

- Testes ainda não executados; nenhuma mudança de código foi feita.
- Nenhum smoke sintético, build de ZIP ou CI foi executado nesta etapa.
- Commit/push deste handoff: pendente.

## Retomada

1. Aguardar a revisão do desenho proposto nesta conversa.
2. Se aprovado, escrever e revisar a especificação arquitetural em
   `docs/superpowers/specs/`, submeter para revisão e só então criar o plano de
   implementação.
3. Implementar na árvore raiz com RED→GREEN por requisito, preservar o fluxo
   atual e atualizar este handoff a cada bloco significativo.
4. Executar os gates da raiz, o smoke sintético especificado e os gates de
   pacote/CI; gerar um ZIP novo a partir do SHA final commitado, verificar seus
   arquivos/hash e registrar o estado final.
