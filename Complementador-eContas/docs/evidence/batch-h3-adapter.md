# F8 — H3 adaptador: lote pequeno (GATE B)

Data: 06/11/2026
Estado: `H3_ADAPTER_PASS`

O lote autorizado de 25 examinados / 10 salvos foi executado no Chrome QA após o H2 adaptador. Resultado: **25 examinados, 10 salvos, 15 revisão, 0 incertos**.

## Resultado

| Métrica | Valor |
| --- | ---: |
| Capturados | 25 |
| Examinados | 25 |
| Preenchidos | 10 |
| Salvos | 10 |
| Confirmados pelo motor | 10 |
| Confirmados por verificação independente | 10/10 |
| Revisão | 15 |
| Salvamentos incertos | 0 |
| Duração | 243 s |
| Tempo por processo | p50 10,4 s; p95 23,5 s; máximo 31,9 s |

## Revisões

| Motivo | Quantidade |
| --- | ---: |
| `MULTIPLE_INTERESTED` | 9 |
| `DOCUMENT_NOT_FOUND` | 3 |
| `GUIA_NOT_MATCHED` | 2 |
| `FIELD_NOT_PRESENT` | 1 |

Nenhum processo de revisão foi salvo. Nenhum valor foi inventado.

## Contabilidade

- 25 processos distintos; 26 eventos `BEGIN_PROCESS` porque a segunda fila recapturou o primeiro item da página.
- 10 `SAVE_ACK`, 0 `MARK_UNCERTAIN`, nenhum segundo clique.
- Os quatro atos concluídos antes desta homologação não foram tocados.
- Verificação independente no portal: 10/10 sem botão “Complementar ato”.

## Segurança e limites

- Filtros mantidos; nenhuma página adicional foi processada.
- Abas de processos `CONFIRMED` são fechadas após o ACK; revisões/incertezas permanecem para conferência.
- Chrome profissional não foi alterado.
- Kill físico do worker e autosave continuam limitações separadas.

## Veredito

`H3_ADAPTER_PASS`. O lote real está homologado; o release 2.0.0 pode ser entregue como funcional, com aceite humano G7 pendente.
