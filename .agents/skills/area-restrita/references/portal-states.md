# Estados documentais da Área Restrita

Este guia descreve o vocabulário do contrato versionado em
`devtools/area-restrita/portal-contract.json`. O contrato e suas fixtures são
documentação/oráculos de teste; não provam, sozinhos, o estado atual do portal.
Os sinais listados abaixo refletem o contrato e o scanner atuais até que uma
captura real sanitizada da Phase 0 confirme ou atualize cada um.

| Estado | Sinais documentados | Conduta segura |
|---|---|---|
| `list` | Rota documentada `ProcessonoSetor.asp`; `#tbproc01` e `#NumeroPagina`. | Em L0, observar a estrutura e a ordem real. Não inferir paginação, próximo alvo ou identidade a partir da posição visual. |
| `interested` | Rota documentada `ComplementarAto.asp`; `#PessoasAssocicadas`, `#PessoasAssociadas` e `input[name=escolha]`. | Confirmar pessoa e processo exatos. Seleção é L2 e requer gate, contexto inequívoco e operador presente. |
| `form` | `#complementarAtoForm`; sentinelas estruturais `#txtNumeroProcesso` e `#txtAnoProcesso`; campos documentados no contrato. | Não ler valores de campos em captura estrutural. Confirmar identidade antes de qualquer preparação L2. |
| `buttons` | Rota documentada `botoesNOVO.asp`; `data-action=return-list`, `Voltar` ou `Retornar`; relação de frame irmão documentada no contrato. | Tratar retorno como L1 somente após o gate. A relação de frame ainda precisa de confirmação real quando usada pela Phase 0. |
| `transitioning` | Estado permitido pelo vocabulário do contrato; sem sentinela ou papel emitido pelo scanner atual. | Não adivinhar destino. Fazer leitura estrutural limitada e aguardar um predicado estrutural; timeout é só limite superior. |
| `unknown` | Papel emitido quando o scanner não reconhece uma tela suportada. | Parar ações de navegação/escrita, capturar evidência L0 sanitizada e registrar o que falta identificar. |
| `ambiguous` | Estado permitido pelo contrato; sem papel ou sentinela emitidos atualmente pelo scanner. | Parar. Não escolher primeiro frame, formulário, radio, botão, processo ou interessado. Recolher evidência L0 que discrimine as possibilidades. |

## Fronteira das afirmações

- `transitioning` e `ambiguous` são estados de documentação/análise; o scanner
  atual não os emite. Não afirme que o runtime os detectou sem teste e
  implementação correspondentes.
- `portal-contract.json` atualmente não registra transições. Não derive uma
  transição de uma rota, fixture sintética ou ordem de frames.
- As rotas, IDs e relação entre frames não substituem uma captura real. Para
  cada sinal usado para mudar runtime, exija observação, captura sanitizada,
  fixture e teste RED.
- Quando vários documentos/frames satisfazem sinais diferentes, o resultado é
  `ambiguous`, mesmo que um deles apareça primeiro no DOM.
