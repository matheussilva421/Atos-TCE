# Validação de Próximo Processo — checkpoint 2026-09-26

## Estado

**Parcial; a navegação portal-real não foi concluída.** A tentativa única pelo botão da Mesa foi recusada com HTTP 404 antes de criar comando; a Área Restrita permaneceu na lista, sem formulário aberto. Os gates automatizados passaram. Não declarar Task 8 ou o goal completo enquanto a matriz supervisionada e a comparação de tempo real estiverem pendentes.

## Implementação e gates automatizados

- Branch: `codex/atos-tce-unified`.
- Navegação implementada nas Tasks 1–7. Commits publicados: `be79ff7` (teste), `a6f7572` (handoff), `13f0503` (correção pós-revisão) e `c9e0428` (handoff final). O push foi aceito em `origin/codex/atos-tce-unified`, de `a6f7572` até `c9e0428`.
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
| Ação Próximo Processo nesta sessão | Cobertura automatizada PASS | BLOCKED — API local respondeu 404; nenhum comando criado |
| Transição após clique final manual | Sem teste automático; ação final é humana | NOT_RUN |
| Comparação com tempo manual | Sem medição pareada atual | NOT_RUN |

## Motivo da lacuna live

- A única execução autorizada da análise oficial retornou `session_required`. Ela não foi repetida e a lista não foi lida por outra interface.
- A correspondência MCP/CDP foi comprovada: `127.0.0.1:9222` e `list_pages` expuseram as mesmas origins/paths da Área Restrita, da Mesa local e da extensão. A Mesa retornou health API v1/schema 7, mas `POST /api/v1/portal/next-act` respondeu HTTP 404 em 4 ms. O processo servidor iniciou antes do commit que adicionou essa rota (`5510362`, 2026-09-26 18:36 -03); o snapshot local registrou zero comando `OPEN_NEXT_ACT` novo e a Área Restrita continuou na lista. O root cause é um backend Mesa antigo ainda em execução.
- A lista salva mais recente (scan id 9) tem 1.197 itens, 354 pendentes; dois itens consecutivos elegíveis `PRONTO`/`PRECISA_COMPLEMENTAR` foram verificados somente em memória como âncora/alvo. Identidades não foram incluídas no handoff. Nenhuma releitura/varredura da lista autenticada foi executada.
- O DOM anterior da aba Mesa estava antigo; recarga local sem cache fez reaparecer a ação. O âncora foi selecionado localmente e o botão foi clicado uma única vez. A API 404 impediu qualquer comando/navegação; nenhum ato ou campo foi alterado.
- Captura estrutural `before` autorizada em `dados-locais/portal-lab/next-process-before-2026-09-26.json`, ignorada pelo Git: 9 documentos/frames do portal e um documento da Mesa, só origens/rotas e contagens de estrutura. Sem texto, valores, cookies, storage, headers, corpos ou screenshot.
- Para carregar o endpoint novo será necessário reiniciar a Mesa. `Bridge` mantém sessões em memória, portanto a reinicialização invalida a sessão local da Mesa e exigirá bootstrap manual no Chrome QA. O login da Área Restrita permanece separado. O agente não deve ler/copiar o token de bootstrap. No diagnóstico, não havia jobs ativos nem comandos enfileirados.

## Próxima retomada

1. Reiniciar somente o backend Mesa na branch/código atual após reconciliar que não há jobs/comandos ativos; reabrir `127.0.0.1:18743` no Chrome QA e concluir o bootstrap local manual sem compartilhar o token no chat.
2. Reconfirmar Mesa conectada e abas da Área Restrita/Mesa em CDP `127.0.0.1:9222`.
3. Usar o snapshot persistido; não repetir a análise da lista. Uma única transição supervisionada, captura estrutural `after` e releitura exata do alvo.
4. Manter sem execução o clique final **Complementar Ato**; registrar tempos e completar a matriz real.

## Fechamento documental — 2026-09-26

- `python -m unittest tests.test_packaging_contract -v`: 14 testes aprovados, 0 falhas.
- O ZIP foi refeito depois de `13f0503` e passou tanto `packaging/verify-package.ps1` quanto o teste de allowlist do pacote real. Artefato local ignorado: `dist/Atos-TCE-portable.zip`.
- Task 8 permanece parcial; Task 10 e o goal geral não estão concluídos enquanto faltarem validação supervisionada real e comparação de tempo. O clique final permanece manual.
- Estado Git ao fechar: branch canônica publicada em `c9e0428`; captura L0 e ZIP continuam locais/ignorados.
- Atualização posterior: a aba Mesa está comprovadamente ligada ao CDP, mas o backend ativo precede a rota `next-act`; uma tentativa HTTP 404 terminou sem comando nem navegação. Restart exigirá bootstrap Mesa humano devido ao `Bridge` em memória.
