# Status da automação em lote — 05/11/2026

Branch: `codex/complementador-e-contas`. `main` permanece em `6e1acd5`.

## Resumo

A automação em lote está funcional de ponta a ponta no Chrome QA, com uma ressalva importante: **o preenchimento foi automatizado; o salvamento dos quatro atos preenchidos foi supervisionado pelo operador**, não pelo adaptador automático. O adaptador existe, está testado e permanece desligado.

## Entregas de código

- Fila congelada da página atual, deduplicação, exclusão de concluídos e dois limites independentes.
- Máquina de estados com `SAVE_PENDING`, `SAVE_NOT_DISPATCHED`, `MARK_FILLED` e recusa de transições ilegais.
- Diário mínimo sanitizado em `chrome.storage.local`, com falha fechada em corrupção, quota e schema.
- Leitor da listagem com status por classe, contexto de filtros e sem paginação.
- Painel na listagem: pré-visualizar, iniciar, pausar, parar, continuar, salvar e restaurar filtros.
- Filtros persistentes com aplicação e BUSCAR automáticos em sessão nova.
- Fluxo por processo: abas novas dedicadas, verificação de identidade, interessado único, preenchimento, validação e gate de salvamento.
- Modo só-preenchimento (`BATCH_FILL_ONLY=1`) no qual o salvamento é impossível por construção; abas preenchidas são mantidas para revisão.
- Adaptador de salvamento com clique único, diálogo desconhecido falhando fechado e captura do diálogo para aprendizagem.

## Evidência real (Chrome QA)

| Verificação | Resultado |
| --- | --- |
| Contrato da listagem | PASS (10 linhas, status por classe, filtros) |
| Rota de Autos | PASS (iframe, 54 cartões, content script ativo) |
| Filtros salvos + busca automática | PASS (chips confirmam marcador) |
| Lote 10/1 só-preenchimento | 10 examinados, **4 FILLED**, 6 em `MISSING_FIELDS`, 0 salvos |
| Campos nas 4 abas | PASS (quatro campos + modalidade em todas) |
| Salvamento dos 4 atos | PASS (uma confirmação por ato) |
| Verificação pós-salvamento | PASS (4 de 4 sem o botão “Complementar ato” ao reabrir) |

Diálogo real: título **“Complementar ato”**, confirmação **“sim, complementar”**, cancelamento **“NÃO”**.

## Testes

- `node --test tests/unit/*.test.mjs`: **266 testes PASS**.
- Navegador: 23 especificações; 22 PASS na última execução completa e o novo `batch-filters.spec.mjs` PASS isolado.
- `npm run build`: PASS.

## Gates

| Gate | Estado |
| --- | --- |
| G0 baseline e backup | PASS |
| G1 listagem e Autos | PASS; UI de salvamento aprendida no H2 |
| G2 núcleo determinístico | PASS |
| G3/H1 sintético | PASS (com lacunas de MV3 e cache real) |
| G5/H2 um salvamento real | PASS supervisionado, fora do adaptador |
| G6/H3 lote real pequeno | PASS supervisionado (4 atos, com autorização) |
| G7 release/aceite | PENDENTE |

## O que falta

1. Salvamento automático pelo adaptador, com o diálogo já conhecido, provado em um ato novo.
2. Entender por que 6 processos não trouxeram os cinco campos (seleção de documento ou dado ausente).
3. Ciclo de vida MV3 (suspensão do service worker e reinício do navegador).
4. Isolamento de cache entre dois processos reais.
5. Comportamento de autosave do portal.
6. Validação no Chrome profissional (não executada).
7. Release G7: build final sem flags, pacote, hashes e aceite.
8. Contabilidade: o diário ainda marca os 4 como `FILLED`; os salvamentos supervisionados não foram registrados como `CONFIRMED` pelo motor.

## Segurança

- Nenhum dado pessoal foi persistido; a evidência é sanitizada.
- Nenhum salvamento ocorreu sem autorização explícita do operador.
- O build de entrega deve ser gerado **sem** `BATCH_FILL_ONLY` e **sem** `BATCH_EXECUTION`, mantendo o motor desligado por padrão.
