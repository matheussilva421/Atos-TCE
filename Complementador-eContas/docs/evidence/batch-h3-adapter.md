# F8 — H3 adaptador: lote pequeno (GATE B)

Data: 05/11/2026
Estado: `H3_ADAPTER_NOT_RUN`

Este gate só pode começar depois de F7/H2-adaptador `PASS` e de nova autorização específica do operador. Não é autorizado pelo H3 supervisionado antigo nem pelos quatro salvamentos já feitos.

## Pré-condições

- F7/H2-adaptador com resultado `PASS` e aceite registrado.
- Build de QA com salvamento habilitado, em caminho novo.
- Limites definidos pelo operador (exemplo: até 3 examinados, até 2 salvos), sem ultrapassar.
- Lista com estados mistos, se disponível: pendente elegível, já concluído, múltiplos interessados e dado ausente.
- Perfil QA, nunca Chrome profissional.

## Procedimento (somente após autorização)

1. Registrar a autorização, os limites e o escopo dos processos.
2. Confirmar lista, filtro, contexto e ausência de outro lote ativo.
3. Iniciar uma vez; observar a fila congelada, a ordem sequencial e os limites.
4. Confirmar que nenhum processo inelegível recebe clique e que cada salvamento tem checkpoint/prova.
5. Parar em qualquer incerteza; não repetir clique.
6. Reconciliar o relatório com leitura independente do portal.
7. Registrar examinados, elegíveis, salvos com prova, ignorados, revisão, incertezas, duração e hashes.

## Resultado

| Item | Valor |
| --- | --- |
| Status | `NOT_RUN` |
| Dependência | F7/H2-adaptador PASS + autorização nova |
| Processos examinados | 0 |
| Salvamentos confirmados | 0 |
| Evidência | nenhuma execução |

## Condições de parada

- Qualquer `SAVE_UNCERTAIN`, diálogo desconhecido, sessão expirada, filtro alterado ou aba fechada.
- Limite atingido, fila esgotada ou falha sistêmica repetida.
- Divergência entre relatório e portal.

Não promover este gate a PASS por equivalência com o H3 supervisionado anterior.
