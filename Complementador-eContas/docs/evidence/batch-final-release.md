# Release 2.0.0 — Complementador e-Contas

Data: 06/11/2026
Branch: `codex/complementador-e-contas`
Versão: `2.0.0`
Estado: `RELEASE_2.0_READY` / `G7_PENDING_HUMAN_ACCEPTANCE`

A automação em lote foi homologada no Chrome QA com 25 processos examinados e 10 salvamentos reais, todos verificados independentemente no portal. O Chrome profissional não foi tocado.

## ZIP funcional

| Item | Valor |
| --- | --- |
| Arquivo | `release/Complementador-eContas-2.0.0.zip` |
| Bytes | 645.261 |
| SHA-256 | `5606E669696FBF734BBFC01D197731D60EBA95393F3FC7519088C9E652E7A13A` |
| Manifesto | 2.0.0 |
| Extração de ensaio | `work/release-2.0.0-extract` |
| Divergências de hash | 0 |

### Arquivos do ZIP

| Arquivo | Bytes | SHA-256 |
| --- | ---: | --- |
| manifest.json | 1.201 | `F5E80C53C04BF09E3E0476C8FC8BFB045919D85D564DF1D933440A3F46EDD3FB` |
| background.js | 133.842 | `50E2CE856CD2C49E4FD605B94AD7E4C3F2D6865478C014DC10502C8E404B2D03` |
| form-content.js | 57.831 | `544711B11E12963FFDB6092524AFEF1A7E36AE973C9B08423D8F8B1B002E5C9E` |
| autos-content.js | 984.542 | `F8A4496DC6AB8B218E40DB010B5A16BDA4E16EAF7C5FFD6E96FEBD59ED5F0FDB` |
| list-content.js | 27.760 | `52251C5E859BB929B58D991D6D639EBA53527D66B140214DB8044F165CCA91F8` |
| vendor/pdf.worker.mjs | 1.417.586 | `BD88805178A26C729DB8C0107A5B630CB900EC070F4D8C7529A3E45530AFD41D` |

O build funcional tem `BATCH_EXECUTION_ENABLED=true`, `BATCH_SAVE_ENABLED=true` e `BATCH_FILL_ONLY=false`. O lote só começa após clique explícito em “⚡ Rodar automação”; não há início automático de lote no carregamento.

## Homologação

- 25 processos distintos examinados; 10 preenchidos, 10 salvos e 10/10 confirmados no portal.
- 15 revisões: 9 `MULTIPLE_INTERESTED`, 3 `DOCUMENT_NOT_FOUND`, 2 `GUIA_NOT_MATCHED`, 1 `FIELD_NOT_PRESENT`.
- 0 `SAVE_UNCERTAIN`; 10 `SAVE_ACK`; nenhum segundo clique.
- Duração 243 s; p50 10,4 s, p95 23,5 s, máximo 31,9 s.
- Relatório detalhado: `docs/evidence/batch-2.0-homologation-attempt.md`.

## Testes

| Comando | Resultado |
| --- | --- |
| `node --test tests/unit/*.test.mjs` | **326 PASS** |
| `npm run test:browser` | **24 PASS** |
| `npm run build` / `build:test` | PASS |
| Extração do ZIP | PASS, 0 divergências |

## Abas

- Após `CONFIRMED`, a extensão fecha as abas de Autos e Complementar Ato daquele processo.
- Processos em revisão, falha ou incerteza mantêm as abas para conferência.
- Nesta sessão, as abas dos 10 atos salvos foram fechadas; permaneceram a listagem e abas de revisão.

## Backup e rollback

- Backup imutável: `work/batch-final-baseline-2026-11-05` (128 arquivos; ZIP SHA-256 `2AAF8D1449C838D9DFC42669622A0F30163E26FFE50652E1352960EF25FA3C1E`).
- Candidato seguro anterior: `release/Complementador-eContas-0.1.1-batch-safe.zip`.
- Rollback: remover/desativar a 2.0.0 e carregar o backup ou o candidato seguro. Reverter código não desfaz ato já gravado no e-Contas.

## Instalação

1. Extrair `Complementador-eContas-2.0.0.zip` em pasta local.
2. Abrir `chrome://extensions`, ativar modo desenvolvedor e carregar a pasta extraída.
3. Confirmar versão 2.0.0 e iniciar cada lote explicitamente.
4. Não instalar no Chrome profissional sem autorização institucional.

## Gates

| Gate | Estado |
| --- | --- |
| F0–F6 | PASS |
| F7 H2 adaptador | PASS — 10 salvamentos reais, 10/10 verificados |
| F8 H3 lote | PASS — 25 examinados, 10 salvos, 0 incertos |
| F9 Chrome profissional | NOT_RUN — não instalado |
| G7 aceite | PENDENTE — revisão do operador |

## Limitações

- Kill físico do service worker/reinício do navegador: `MV3_WORKER_KILL_TEST_NOT_RUN` (lógica coberta por testes puros/estáticos).
- Autosave do portal: `UNKNOWN`.
- A homologação real usou o build QA 0.1.1 com o mesmo caminho de preenchimento/salvamento; a 2.0.0 acrescenta apenas o fechamento pós-save das abas, testado em unitários e navegador.
