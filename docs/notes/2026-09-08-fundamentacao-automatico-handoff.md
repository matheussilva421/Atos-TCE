# Handoff — plano por fases de fundamentação e automação

## Trabalho concluído

- Entrevista de requisitos consolidada em plano detalhado de 11 fases (0 a 10), vinculado aos módulos reais da extensão e serviço Python.
- Inspecionados contratos de dataset/mensagens, matcher, detector, worker, cliente HTTP, serviço, progresso, extração, pipeline e empacotador.
- Registrados interfaces propostas, TDD por fase, critérios de aceite, regras operacionais, relatório incremental, matriz de interrupções e gates reais.
- Revisão solicitada posteriormente: redesign completo acrescentado à fase 8, com entregas 8A–8E, tokens visuais, wireframes, estados, acessibilidade, componentes, testes e impacto no pacote.

## Arquivos

- Criado `docs/notes/2026-09-08-fundamentacao-automatico-plano-fases.md`.
- Criado este handoff.
- Nenhum código funcional, dado de processo, pacote ou configuração alterado.

## Decisões principais

- EC41 art. 6º ou 7º; art. 7º isolado aceito operacionalmente pelo usuário.
- Variante §5 somente quando CF art. 40 §5 constar na resolução; cargo não basta.
- EC47 art. 3º para terceira família; outras opções por maior semelhança conforme escolha expressa, com risco e rastreabilidade documentados.
- Todos os disponíveis; pendências documentais e divergências são registradas e puladas; envio incerto pausa sem repetição automática.
- Sete campos atuais; diário SQLite separado do progresso legado; relatórios HTML/CSV locais e painel.
- Proposta visual para implementação futura: Ato atual / Execução / Histórico, configurações recolhidas, campos verticais e trilha Resolução → Regra → Opção. Tema claro azul-petróleo, fontes locais e nenhuma tabela larga no painel estreito.
- Ajuste posterior solicitado no wireframe: botão “Preencher campos disponíveis” e indicação do modo manual no topo de Ato atual, logo abaixo das abas e antes da fundamentação. Plano, wireframe e critério de aceite atualizados; ação não será duplicada no rodapé. Somente documentação alterada.
- Histórico passa a exigir endpoints autenticados paginados de execuções/eventos; contratos adicionados na seção 13.4 e vinculados à fase 4.

## Validação e testes

- Baseline JS executada na etapa anterior desta mesma sessão: `npm test`, 124 testes, 124 passaram, 0 falharam.
- Nesta entrega documental não se implementaram os testes futuros descritos no plano.
- Inspeção manual anterior: portal autenticado, 170 processos/9 páginas, catálogo e frames verificados; nenhum envio ou preenchimento realizado, retorno à lista confirmado.
- Verificação documental executada: 8 verificações, 8 passaram, 0 falharam. Conferidos 11 fases, 18 seções, blocos de código balanceados, ausência de TBD/TODO, critérios de aceite, contrato de consumo único, handoff e fontes de empacotamento.
- Plano com mais de 600 linhas; revisão adicionou contrato explícito de consumo único e procedimento de habilitação após piloto.
- Redesign fundamentado na leitura de `panel.html`, `panel.css`, `panel.js` e contratos de testes; tabela atual tem largura mínima de 42rem. Não houve renderização, screenshot ou QA visual real nesta revisão; esses gates constam nas entregas 8A/8D.
- Verificação da revisão de redesign: 8 verificações, 8 passaram, 0 falharam (11 fases preservadas, cinco subseções, fences balanceadas, wireframes, API de histórico, QA responsiva, empacotamento e escopo documental). `git diff --check` passou. Suíte funcional não reexecutada, pois somente Markdown mudou.
- `git diff --cached --check` deve passar antes do commit. Nenhuma suíte funcional adicional necessária para estes dois arquivos Markdown.

## GitHub

- Estado inicial desta entrega: `main`, limpo, nenhum remoto configurado.
- Os dois documentos integram o commit documental desta entrega; obter seu identificador com `git log -1 --oneline -- docs/notes/2026-09-08-fundamentacao-automatico-plano-fases.md`.
- Push indisponível sem destino; não configurar remoto arbitrário. Nenhum envio ao GitHub realizado.

## Problemas e soluções

- Primeiro `git add` falhou por acesso negado a `.git/index.lock` no sandbox.
- Com permissão ampliada, Git detectou proprietário diferente. Resolvido com `git -c safe.directory='C:/Users/slvma/Downloads/Github/Complementação de Atos'`, limitado ao comando; configuração global não alterada.
- Staging limitado nominalmente aos dois Markdown; nenhum `git add .` utilizado.

## Pendências e retomada

1. Ler o plano salvo, especialmente decisões da seção 1 e contratos da seção 4.
2. Implementação não iniciada. Iniciar fase 0 com baseline atualizada e reprodução RED.
3. Não interpretar `completed` legado nem sinal DOM como envio confirmado.
4. Confirmação real após envio ainda não foi observada. Fase 9 define como obter e transformar em fixture/teste.
5. Não executar lote real apenas porque o plano foi salvo. Esta solicitação foi de documentação.
6. Nenhuma reversão funcional necessária; só dois documentos novos nesta entrega.
7. Para o redesign, ler toda a seção 13.1–13.5 antes de trocar a marcação: `ELEMENT_IDS`, `renderRows`, mensagem permanente, fixtures e allowlist precisam ser atualizados juntos na implementação. Nesta revisão apenas os dois documentos existentes foram alterados.
