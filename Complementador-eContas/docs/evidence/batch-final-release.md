# Release 2.0.4 — Complementador e-Contas

Data: 06/11/2026
Branch: `codex/complementador-e-contas`
Versão: `2.0.4`
Estado: `RELEASE_2.0.4_READY` / `G7_PENDING_HUMAN_ACCEPTANCE`

A automação em lote foi homologada no Chrome QA com 25 processos examinados e 10 salvamentos reais, todos verificados no portal. O patch 2.0.4 adiciona suporte a **Meus Processos**, separa presets por rota e amplia tempos para máquinas mais lentas. O Chrome profissional não foi tocado.

## ZIP funcional

| Item | Valor |
| --- | --- |
| Arquivo | `release/Complementador-eContas-2.0.4.zip` |
| Bytes | 646.605 |
| SHA-256 | `817A8D3B2B55E3A85967A555255C2B9A548522BF11685F62983DC62B73A0D8A3` |
| Manifesto | 2.0.4 |
| Extração de ensaio | `work/release-2.0.4-extract` |
| Divergências de hash | 0 |

### Arquivos do ZIP

| Arquivo | Bytes | SHA-256 |
| --- | ---: | --- |
| manifest.json | 1.201 | `69DF58508106E47A68EC72E48BE1F8E904F0E6C5508ED463B7D59ABDA307DF40` |
| background.js | 138.418 | `0FC2C0B801CF1F6D662EA246004AEB0010790BC66E000C117316E1BC3233ED2E` |
| form-content.js | 57.943 | `C8E29A40ECBBFEA51D484356332F550831B241CD50D93409762DFC8FB166A6FC` |
| autos-content.js | 984.654 | `E35BFE18E66DE5E4FD92E567FA786260FCB16ACB849873F7A6136EEFE30E593E` |
| list-content.js | 30.637 | `DE7A600D936AC91A3B4130A4C8D139A048BC031678BE2CEBA005B41BDFDEF60A` |
| vendor/pdf.worker.mjs | 1.417.586 | `BD88805178A26C729DB8C0107A5B630CB900EC070F4D8C7529A3E45530AFD41D` |

O build funcional tem `BATCH_EXECUTION_ENABLED=true`, `BATCH_SAVE_ENABLED=true` e `BATCH_FILL_ONLY=false`. O lote só começa após clique explícito em “⚡ Rodar automação”; não há início automático no carregamento.

## Homologação

- 25 processos distintos examinados; 10 preenchidos, 10 salvos e 10/10 confirmados no portal.
- 15 revisões: 9 `MULTIPLE_INTERESTED`, 3 `DOCUMENT_NOT_FOUND`, 2 `GUIA_NOT_MATCHED`, 1 `FIELD_NOT_PRESENT`.
- 0 `SAVE_UNCERTAIN`; 10 `SAVE_ACK`; nenhum segundo clique.
- Duração 243 s; p50 10,4 s, p95 23,5 s, máximo 31,9 s.
- Relatório: `docs/evidence/batch-2.0-homologation-attempt.md`.

## Meus Processos

- Rota `#/dashboard/meus/meus-processos` reconhecida.
- Verificação real: 25 linhas, 23 pendentes e 2 concluídos; painel e pré-visualização funcionando.
- Presets separados por rota:
  - `complementadorFilterPreset` para `processos-no-setor`;
  - `complementadorFilterPreset:meus-processos` para Meus Processos.
- O preset antigo não é mais aplicado automaticamente em Meus Processos.

## Tempos ampliados

- Leitura/aplicação do lote: 180 s.
- Busca documental: 600 s.
- Espera de abas: 30 s.
- Espera do iframe de Autos: 60 s.
- Retry de content script em aba nova: 40 s.

## Testes

| Comando | Resultado |
| --- | --- |
| `node --test tests/unit/*.test.mjs` | **337 PASS** |
| `npm run test:browser` | **25 PASS** |
| `npm run build` / `build:test` | PASS |
| Extração do ZIP | PASS, 0 divergências |

## Zerar lote e janela

- Botão **Zerar lote** limpa o diário e reabilita o Iniciar; recusa quando há `SAVE_UNCERTAIN`/`saveAttemptId`.
- As abas são criadas na janela onde o lote foi iniciado; outra janela não recebe os processos.

## Abas

- Checkbox **“Manter abas de processos com problema”**, marcado por padrão.
- Marcado: revisão/falha mantêm Autos e Complementar Ato abertos; desmarcado: fecham.
- `SAVE_UNCERTAIN` sempre mantém as abas; `CONFIRMED` sempre fecha.
- A preferência é persistida em `chrome.storage.local`.
- As abas de trabalho são fixadas na janela onde o lote foi iniciado; outra janela aberta no segundo monitor não recebe os processos.

## Backup e rollback

- Backup imutável: `work/batch-final-baseline-2026-11-05` (128 arquivos; ZIP SHA-256 `2AAF8D1449C838D9DFC42669622A0F30163E26FFE50652E1352960EF25FA3C1E`).
- Rollback: `release/Complementador-eContas-0.1.1-batch-safe.zip` (SHA-256 `D820E4A9E32FB66F99C27D5B8B2E777E65E901153BC9076DE05EE154A8319E0C`).
- Reverter código não desfaz ato já gravado no e-Contas.

## Instalação no outro PC

1. Remover/desativar a 2.0.0.
2. Extrair o ZIP 2.0.4 e carregar a pasta em `chrome://extensions` com modo desenvolvedor.
3. Confirmar versão 2.0.4.
4. Aplicar o filtro, definir os limites e iniciar explicitamente o lote.

## Gates

| Gate | Estado |
| --- | --- |
| F0–F6 | PASS |
| F7 H2 adaptador | PASS — 10 salvamentos reais, 10/10 verificados |
| F8 H3 lote | PASS — 25 examinados, 10 salvos, 0 incertos |
| Meus Processos | PASS — 25 linhas, 23 pendentes, 2 concluídos |
| F9 Chrome profissional | NOT_RUN — não instalado |
| G7 aceite | PENDENTE — revisão do operador |

## Limitações

- Kill físico do service worker/reinício do navegador: `MV3_WORKER_KILL_TEST_NOT_RUN`.
- Autosave do portal: `UNKNOWN`.
- A outra máquina não foi acessada diretamente; o patch amplia os limites e corrige a rota, mas a confirmação final é no ambiente do operador.
- A homologação real usou o build QA 0.1.1 com o mesmo caminho de preenchimento/salvamento; a 2.0.4 acrescenta limpeza pós-save, rota Meus Processos e tempos maiores, cobertos por testes.
