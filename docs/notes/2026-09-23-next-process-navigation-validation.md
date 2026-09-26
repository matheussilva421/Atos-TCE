# Validação de Próximo Processo — checkpoint 2026-09-26

## Estado

**Parcial; a validação real do portal não foi executada.** Os testes e gates automatizados passaram. Não declarar Task 8 ou o goal completo enquanto a matriz supervisionada e a comparação de tempo real estiverem pendentes.

## Implementação e gates automatizados

- Branch: `codex/atos-tce-unified`.
- Navegação implementada nas Tasks 1–7. Commits publicados: `be79ff7` (teste) e `a6f7572` (handoff). Correção pós-revisão `13f0503` trata recusas HTTP 409 `next_act_refused` como retryable sem abrir o bloqueio de incerteza; commit local até o fechamento deste handoff.
- `python -m unittest discover -s tests -p "test_*.py" -q`: 662 executados, 661 aprovados, 0 falhas, 1 skip.
- `npm test --prefix extension`: 190/190.
- `node --test app/web/tests/*.test.mjs`: 32/32 após a correção de recusas 409.
- `work/tce-extractor/verify-project.ps1`: 1.260 executados, 1.258 aprovados, 0 falhas, 2 skips; sete estágios verdes.
- `python -m unittest tests.test_packaging_contract -v`: 14/14, incluindo o ZIP standalone produzido.
- ZIP standalone em `dist/Atos-TCE-portable.zip`: 516 entradas, runtime pinado incluído (430 arquivos); verificador/smoke retornou `status: ok`, API v1, schema 7 e DB de teste vazio. Tamanho 96.155.474 bytes; SHA-256 `216f10546370c1215ee0aef6554b397c33b4c562fa4b46bf98409b8c47f55627`. A pasta temporária do smoke foi removida. O script reportou `Acesso negado` ao tentar encerrar um processo do smoke; o verificador terminou com exit 0 e a checagem posterior não encontrou a pasta temporária.
- Separação do fluxo: testes confirmam que Próximo Processo só solicita navegação, a Mesa só seleciona o alvo após sucesso e releitura exata, o módulo de navegação não expõe superfície de submit e a UI da Mesa não oferece enviar/finalizar.

## Revisão adversarial e correção

- Revisores independentes avaliaram o diff. A observação de que os arquivos ativos estariam fora de `work/tce-extractor` foi confrontada com o README e o plano canônico atuais, que identificam `app/`, `extension/` e `packaging/` como runtime ativo e `work/tce-extractor` como legado/fallback. Dois apontamentos de manutenção foram julgados heurísticos e sem correção necessária para esta tarefa.
- Foi confirmado um defeito P2: recusas de navegação HTTP 409 `next_act_refused` entravam no estado de incerteza e bloqueavam nova tentativa até recarga, embora o backend recusasse antes de criar comando. TDD: novo teste ficou RED porque `postJson` descartava status/payload; correção preserva ambos e a UI permite nova tentativa somente nesse 409 codificado. Falhas de transporte, 5xx, timeout e resposta ambígua continuam bloqueadas para releitura manual. Web: 32/32.
- A autorização recebida para salvar a captura estrutural L0 foi usada somente no diretório local ignorado `dados-locais/portal-lab/`. A captura contém metadados estruturais; não contém texto de páginas, valores, cookies, storage, tráfego ou screenshot. Não leu linhas da lista nem repetiu a análise oficial.

## Matriz real do portal

| Cenário | Cobertura automatizada | Portal real nesta sessão |
|---|---|---|
| Destino na mesma página | PASS — fixtures de roteador | NOT_RUN |
| Destino em página posterior | PASS — fixture cross-page | NOT_RUN |
| Seleção do interessado exato | PASS — teste de navegação | NOT_RUN |
| Marcador divergente e retenção | PASS — recusa sem restauração | NOT_RUN |
| Restauração do marcador | N/A — Phase 0 registrou `marker_restore: not_needed` | N/A |
| Alvo stale/removido sem escolher vizinho | PASS — retorna `TARGET_NOT_FOUND` | NOT_RUN |
| Frames ambíguos | PASS — recusa `FORM_AMBIGUOUS` | NOT_RUN |
| Fim da fila sem comando | PASS — resposta explícita e nenhum comando enfileirado | NOT_RUN |
| Formulário pronto e identidade relida | PASS — fixtures e contrato da API | NOT_RUN |
| Transição após clique final manual | Sem teste automático; ação final é humana | NOT_RUN |
| Comparação com tempo manual | Sem medição pareada atual | NOT_RUN |

## Motivo da lacuna live

- A única execução autorizada da análise oficial retornou `session_required`. Ela não foi repetida e a lista não foi lida por outra interface.
- O MCP listou páginas do portal/Mesa, mas a inspeção read-only dos endpoints locais `9222–9232` encontrou em `127.0.0.1:9222` apenas uma página de extensão e nenhum alvo da Área Restrita ou Mesa. Não foi possível provar que o MCP controla o Chrome QA dedicado exigido pelo Portal Lab; nenhuma navegação real foi iniciada.
- A captura estrutural L0 autorizada permanece somente em `dados-locais/portal-lab/area-restrita-structural-L0-2026-09-26.json`, ignorada pelo Git. Ela não contém texto, valores de campos, cookies, storage, tráfego ou screenshot e não substitui `SCAN_PAGE` nem uma validação de navegação.

## Próxima retomada

1. Reconciliar o Chrome QA dedicado e o MCP para que ambos apontem ao mesmo CDP loopback em `127.0.0.1:9222`, preservando login manual.
2. Confirmar no próprio endpoint a presença das abas da Área Restrita e da Mesa antes de qualquer transição.
3. Usar a fila já persistida e um alvo exato ainda elegível; não repetir a análise da lista. Fazer uma única transição L1 de navegação, capturar before/after estrutural e reler a identidade final.
4. Manter sem execução o clique final **Complementar Ato**; qualquer observação posterior depende do operador.
5. Registrar tempos e completar a matriz real. Se `session_required` persistir, parar a etapa live sem contorno.

## Fechamento documental — 2026-09-26

- `python -m unittest tests.test_packaging_contract -v`: 14 testes aprovados, 0 falhas.
- O ZIP foi refeito depois de `13f0503` e passou tanto `packaging/verify-package.ps1` quanto o teste de allowlist do pacote real. Artefato local ignorado: `dist/Atos-TCE-portable.zip`.
- Task 8 permanece parcial; Task 10 e o goal geral não estão concluídos enquanto faltarem validação supervisionada real e comparação de tempo. O clique final permanece manual.
