# Fase 4.2 — preflight real bloqueado por divergências

Data: 2026-09-11
Status: **NÃO PASSA / bloqueado**
Escopo: documentação e retomada; nenhum preenchimento, envio ou finalização.

## Estado observado

Após login manual do usuário, em Chromium 151 isolado via CDP
`127.0.0.1:19231`, três representantes foram localizados no `ProcessonoSetor`
por consulta exata: `100120/2026`, `100273/2025` e `100065/2026`.

Para cada representante:

- houve uma única ação semanticamente identificada como `Complementar Ato`;
- a identidade processo/ano conferiu;
- a tela apresentou um único rádio de interessado;
- a seleção do rádio foi reversível e deixou visíveis os sete controles
  esperados;
- a conferência foi interrompida quando o preview não bateu com o portal.

O catálogo atual observado continha 13 opções de modalidade, 35 de fundamento
legal e 3 de gênero. Depois de reload da sidepanel, a extensão exibiu
`preview ready` com 7 cards, revisão `120` e prefixo de dataset
`23cce5807c01`; `send` e `pilot` estavam desabilitados.

## Divergências sanitizadas

| Processo/ano | Campos divergentes |
| --- | --- |
| `100120/2026` | `fundamento_legal`, `data_publicacao_doe` |
| `100273/2025` | `modalidade`, `data_publicacao_doe`, `matricula` |
| `100065/2026` | `data_publicacao_doe` |

Este documento registra somente identificadores de processo/ano, contagens,
flags e nomes de campos. Não contém nomes, CPF, tokens, cookies, valores de
campos ou DOM bruto.

## Bloqueio e limites

- O preflight não passou porque os três representantes apresentaram ao menos
  uma divergência de campo.
- Não houve `APPLY_FIELDS`, envio, finalização ou persistência de mutação.
- As abas `Complementar Ato` abertas pelo agente foram fechadas ao final da
  observação; nenhuma alteração foi feita no portal.
- Os checkboxes de 4.2 e de Fase 5+ permanecem desmarcados.
- `real_send_enabled=false` e `pilot_enabled=false` permanecem a fronteira
  de segurança.

## Retomada segura

1. Reconciliar a origem das divergências de `fundamento_legal`,
   `data_publicacao_doe`, `modalidade` e `matricula` sem publicar valores
   privados.
2. Em nova sessão controlada, repetir consulta exata, ação, identidade, rádio,
   catálogo e os sete controles.
3. Regerar/reler o preview e exigir igualdade completa antes de considerar
   qualquer etapa de preenchimento reversível.
4. Permanecer em STOP diante de nova divergência, identidade ambígua, opção
   ausente, frame incorreto ou evidência insuficiente.
5. Não iniciar Fase 5: qualquer envio futuro exige autorização humana imediata,
   ato a ato, depois de um preflight aprovado.

## Validação e GitHub

Esta entrega é somente documental. Não requer teste de código; a validação é
`git diff --check`, revisão do diff nominal e busca de conteúdo sensível. O
commit e o push desta atualização devem ser feitos somente com os três
documentos listados no fechamento da sessão, em `main` e sem force push.

## Reconciliacao de origem da Area Restrita (2026-09-11)

A imagem da sessao confirma que `Proc./ Doc. Eletronicos` e `Meus Processos
Eletronicos` sao origens distintas. O codigo passou a preservar essa separacao:
`ProcessonoSetor.asp` e `sector_finalistic`; `MeusProcessos.asp` e
`my_processes`; `ComplementarAto.asp` permanece um frame derivado da lista e
nao precisa declarar `source_scope`.

Foram adicionados guards para nao escolher frame de lista oculto ou persistido
de outra origem. A sidepanel tambem rotula explicitamente as duas escolhas.
Testes: 36/36 controlador, 27/27 navegacao, 43/43 sidepanel e 313/313 suite
completa. Nenhum `APPLY_FIELDS`, envio ou finalizacao ocorreu; a Tarefa 4.2
continua bloqueada pelos preflights reais ainda divergentes.
