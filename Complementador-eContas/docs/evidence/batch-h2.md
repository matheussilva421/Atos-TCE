# H2/H3 — salvamento real supervisionado (05/11/2026)

Estado: `EXECUTED_WITH_EXPLICIT_USER_AUTHORIZATION`

O usuário autorizou o salvamento dos quatro atos que a automação havia preenchido. Cada ato foi tratado individualmente, com uma única confirmação, sem repetição de clique.

## Procedimento observado

1. Conferência dos quatro campos e da modalidade em cada aba preenchida.
2. Clique em **Complementar ato**.
3. Diálogo reconhecido como confirmação padrão: título **“Complementar ato”**, botão de confirmação **“sim, complementar”** e cancelamento **“NÃO”**; o corpo lista os dados preenchidos.
4. Uma única confirmação por ato.
5. Verificação independente: a mesma URL do ato, reaberta em aba nova, **não exibe mais o botão “Complementar ato”**.

## Resultado

| Atos preenchidos | Atos salvos | Atos com botão de complementar após verificação |
| --- | --- | --- |
| 4 | 4 | 0 |

Nenhum ato foi salvo sem ter passado pela conferência dos cinco campos. Os seis processos que ficaram em revisão não foram tocados.

## Limitações

- O salvamento foi executado de forma supervisionada pelo operador, não pelo adaptador automático da extensão. O caminho `BATCH_SAVE` está implementado e testado, mas permanece desligado até nova decisão.
- Não há prova de readback interno do portal além da ausência do botão; a confirmação visual de sucesso do portal foi observada após cada confirmação.
- Registro sem números de processo, nomes, CPF, matrícula ou datas, conforme a política do projeto.
