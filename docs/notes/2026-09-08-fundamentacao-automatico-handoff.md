# Handoff — plano por fases de fundamentação e automação

## Estado da execução

- Implementação iniciada em `codex/fundamentacao-automatico`, derivada de `main` em `dc84402`.
- O ledger vivo está em `.superpowers/sdd/2026-09-08-fundamentacao-automatico-plano-fases/progress.md` (git-ignorado) e registra tasks, conflitos e decisões.
- Task atual: Fase 1 — contexto documental completo e sidecar versionado.
- Baseline desta execução: `npm test` 124/124 pass; Python focal 99/99 pass, 1 skip ambiental. Warnings de `fitz` depreciado e `ResourceWarning` já aparecem na baseline e não foram introduzidos nesta branch.
- Fase 0 concluída e revisada: commits `b99fd80` e `54dcf9f`; fixtures/testes sanitizados aprovados em re-revisão Luna. A suíte JS pós-fase ficou 125/126 porque a regressão RED do matcher continua intencional para a Fase 2.
- Envio real continua bloqueado; nenhum PDF, dado de processo ou sessão autenticada será publicado no Git.

## Trabalho documental concluído

- Entrevista de requisitos consolidada em plano detalhado de 11 fases (0 a 10), vinculado aos módulos reais da extensão e serviço Python.
- Inspecionados contratos de dataset/mensagens, matcher, detector, worker, cliente HTTP, serviço, progresso, extração, pipeline e empacotador.
- Registrados interfaces propostas, TDD por fase, critérios de aceite, regras operacionais, relatório incremental, matriz de interrupções e gates reais.
- Revisão solicitada posteriormente: redesign completo acrescentado à fase 8, com entregas 8A–8E, tokens visuais, wireframes, estados, acessibilidade, componentes, testes e impacto no pacote.

## Arquivos

- Criado `docs/notes/2026-09-08-fundamentacao-automatico-plano-fases.md`.
- Criado este handoff.
- Nenhum código funcional foi alterado na entrega documental original; a implementação funcional desta execução ocorrerá somente na branch acima.

## Decisões principais

- EC41 art. 6º ou 7º; art. 7º isolado aceito operacionalmente pelo usuário.
- Variante §5 somente quando CF art. 40 §5 constar na resolução; cargo não basta.
- EC47 art. 3º para terceira família; outras opções por maior semelhança conforme escolha expressa, com risco e rastreabilidade documentados.
- Todos os disponíveis; pendências documentais e divergências são registradas e puladas; envio incerto pausa sem repetição automática.
- Sete campos atuais; diário SQLite separado do progresso legado; relatórios HTML/CSV locais e painel.
- Proposta visual para implementação futura: Ato atual / Execução / Histórico, configurações recolhidas, campos verticais e trilha Resolução → Regra → Opção. Tema claro azul-petróleo, fontes locais e nenhuma tabela larga no painel estreito.
- Ajuste posterior solicitado no wireframe: botão “Preencher campos disponíveis” e indicação do modo manual no topo de Ato atual, logo abaixo das abas e antes da fundamentação. Plano, wireframe e critério de aceite atualizados; ação não será duplicada no rodapé. Somente documentação alterada.
- Histórico passa a exigir endpoints autenticados paginados de execuções/eventos; contratos adicionados na seção 13.4 e vinculados à fase 4.

## Validação e testes da entrega documental

- Baseline JS executada na etapa anterior desta mesma sessão: `npm test`, 124 testes, 124 passaram, 0 falharam.
- Nesta entrega documental não se implementaram os testes futuros descritos no plano.
- Inspeção manual anterior: portal autenticado, 170 processos/9 páginas, catálogo e frames verificados; nenhum envio ou preenchimento realizado, retorno à lista confirmado.
- Verificação documental executada: 8 verificações, 8 passaram, 0 falharam. Conferidos 11 fases, 18 seções, blocos de código balanceados, ausência de TBD/TODO, critérios de aceite, contrato de consumo único, handoff e fontes de empacotamento.
- Plano com mais de 600 linhas; revisão adicionou contrato explícito de consumo único e procedimento de habilitação após piloto.
- Redesign fundamentado na leitura de `panel.html`, `panel.css`, `panel.js` e contratos de testes; tabela atual tem largura mínima de 42rem. Não houve renderização, screenshot ou QA visual real nesta revisão; esses gates constam nas entregas 8A/8D.
- Verificação da revisão de redesign: 8 verificações, 8 passaram, 0 falharam (11 fases preservadas, cinco subseções, fences balanceadas, wireframes, API de histórico, QA responsiva, empacotamento e escopo documental). `git diff --check` passou. Suíte funcional não reexecutada, pois somente Markdown mudou.
- `git diff --cached --check` deve passar antes do commit. Nenhuma suíte funcional adicional necessária para estes dois arquivos Markdown.

## GitHub e branch atual

- Estado inicial desta execução: `main`, limpo, nenhum remoto configurado; branch de implementação criada como `codex/fundamentacao-automatico`.
- Os dois documentos integram o commit documental desta entrega; obter seu identificador com `git log -1 --oneline -- docs/notes/2026-09-08-fundamentacao-automatico-plano-fases.md`.
- Push indisponível sem destino; não configurar remoto arbitrário. Nenhum envio ao GitHub realizado.

## Problemas e soluções

- Primeiro `git add` falhou por acesso negado a `.git/index.lock` no sandbox.
- Com permissão ampliada, Git detectou proprietário diferente. Resolvido com `git -c safe.directory='C:/Users/slvma/Downloads/Github/Complementação de Atos'`, limitado ao comando; configuração global não alterada.
- Staging limitado nominalmente aos dois Markdown; nenhum `git add .` utilizado.

## Tasks e retomada

1. [x] Ler o plano salvo, especialmente decisões da seção 1 e contratos da seção 4.
2. [x] Criar branch de implementação e ledger vivo.
3. [x] Executar fase 0 com baseline atualizada, reprodução RED e fixtures sanitizadas.
4. [~] Implementar fases 1–10 em ordem de dependência, atualizando este handoff após cada bloco; Fase 1 em preparação.
3. Não interpretar `completed` legado nem sinal DOM como envio confirmado.
4. Confirmação real após envio ainda não foi observada. Fase 9 define como obter e transformar em fixture/teste.
5. Não executar lote real apenas porque o plano foi salvo. Esta solicitação foi de documentação.
6. Nenhuma reversão funcional necessária; alterações funcionais serão feitas apenas na branch de execução.
7. Para o redesign, ler toda a seção 13.1–13.5 antes de trocar a marcação: `ELEMENT_IDS`, `renderRows`, mensagem permanente, fixtures e allowlist precisam ser atualizados juntos na implementação.

## Registro por fase — Fase 0

- Comandos: `node --test tests/matcher.test.mjs tests/normalizer.test.mjs`; `npm test`; `python -m unittest test_tce_extractor test_analysis_pipeline test_extension_exporter test_local_service -q`.
- Resultado: focal 34 testes, 33 pass, 1 RED conhecido; full JS 126, 125 pass, 1 RED conhecido; Python focal 85 pass, 1 skip ambiental. A baseline anterior foi 124/124 JS e 99/99 Python focal ampliado.
- RED: matcher legado escolhe `synthetic-ec41-without-p5` em texto sem referências, onde a Fase 2 deverá retornar pendência/null.
- GREEN: catálogo, fixtures simuladas, IDs duplicados no frame e contratos de sanitização passaram após os fixes.
- Validação: somente fixtures sintéticas; nenhum clique, preenchimento ou envio real.
- Limitação: a Fase 0 não corrige produção; a falha RED é esperada até o resolvedor da Fase 2.
- Próximo passo: implementar `legal_context.py`/testes da Fase 1, preservando o dataset v1 e publicando sidecar atômico.

## Registro por fase — Fase 1

- Estado: implementação local concluída no commit `f0a72b5`.
- Arquivos: `work/tce-extractor/portable/app/legal_context.py`,
  `work/tce-extractor/test_legal_context.py`,
  `work/tce-extractor/portable/app/analysis_pipeline.py` e
  `work/tce-extractor/test_analysis_pipeline.py`.
- Contrato: sidecar `fundamentos-contexto.v1.json` com contexto multipágina,
  citações `{document_id,event_id,page,pdf_sha256}`, texto operativo sem
  truncamento, versão de extração e estados `complete`/`missing`/`incomplete`/
  `conflict`.
- Integração: `run_local_pipeline` reutiliza caches locais e vincula o sidecar
  ao `batch.logical_sha256` do dataset v1; não chama OCR adicional nem portal.
- TDD: suíte obrigatória Python 75/75; `test_batch_runner` 19/19; `git diff
  --check` verde. A RED JavaScript do matcher permanece 1 falha intencional.
- Escopo deliberadamente preservado: `empacotar-coletor-portatil.ps1` e
  `test_portable_end_to_end.py` estão byte a byte no HEAD `08cf8b9`. Como
  consequência, o teste do ZIP autocontido falha por não incluir o novo módulo;
  não tratar esse concern sem autorização/fase apropriada.
- Retomada: manter o matcher RED e resolver a dependência do empacotador somente
  em escopo posterior autorizado.
