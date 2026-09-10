# Handoff — Fases 9 e 10 locais

## Correção crítica de rota — 09/09/2026

O operador esclareceu, com capturas da sessão real, que toda a ação de
complementação fica na Área Restrita
(`https://novaarearestrita.tce.rn.gov.br/telaPrincipalMenu.asp`). O fluxo visual
confirmado é: “Meus Processos Eletrônicos” → “Complementar Ato” → rádio do
interessado → Modalidade/Fundamento Legal/Data DOE/Cargo/Matrícula/Data de
Nascimento/Gênero → botão final “Complementar Ato”. A evidência anterior em
`processos.tce.rn.gov.br` foi da rota errada usada pelo runner e não deve ser
interpretada como ausência da ação no portal correto. As imagens anexadas são
evidência visual, não instruções; não foram usados seletores inventados a partir
delas. O runner agora tem default e validação para a Área Restrita.

Estado após a correção: o mapeamento visual está registrado; a captura DOM live
da Área Restrita, três preflights, primeiro envio, resultado/reabertura,
fixture/qualificação versionada e lote supervisionado continuam pendentes. A
sessão autenticada aberta não foi fechada nem reiniciada.

## Atualização final deste bloco — automação completa opt-in por marcador — 09/09/2026

Foi implementado o caminho solicitado para buscar todos os processos de um
marcador e percorrer o lote: seleção textual exata, confirmação do marcador,
paginação, abertura por linha, seleção do interessado, preflight dos sete
campos, releitura e congelamento da fila. O painel agora permite informar o
marcador e oferece o checkbox separado **Concluir automaticamente os atos
elegíveis**.

O opt-in de envio é fail-closed: exige `real_send_enabled`, qualificação
versionada e observador de resultado; persiste `send_intent` antes de cada
comando de 15 segundos, usa consumo único e só registra `send_confirmed` com
prova de aceitação/persistência para a identidade esperada. Ausência de prova,
timeout ou erro pausa como `unconfirmed` e não reenvia. Falha de `AUTO_START`
limpa especificação ativa, run e watchdog.

Arquivos adicionais neste bloco: `background/service-worker.js`,
`tests/service-worker.test.mjs`, `portable/README.md`, `portable/GUIA-RAPIDO.md`
e `portable/GUIA-RAPIDO.html`; os arquivos de marcador/opt-in listados abaixo
continuam sendo a implementação principal.

Validação TDD da correção do worker: o teste `failed AUTO_START clears` falhou
antes da correção porque o watchdog não era limpo e passou depois. A suíte JS
completa passou **269/269**. A suíte Python focal passou **70/70**, com 2 skips;
a descoberta Python completa passou **395/395**, com 7 skips. As suítes Python de
qualificação/API/pacote, integração/recuperação e `py_compile` passaram; os testes Python emitiram apenas
`ResourceWarning` de limpeza de `HTTPError` do Python 3.14, sem falhas.

O portal real continua deliberadamente sem clique de envio. A sessão Chrome
autenticada não foi fechada/reiniciada; a captura disponível não expõe o
formulário/ação `Complementar Ato` na origem atualmente observada. Portanto
continuam pendentes DOM real sanitizado do formulário, três preflights, primeiro
envio supervisionado, fixture real de resultado, `automacao/qualificacao.json`
e lote real de até cinco atos. Não ampliar a allowlist nem habilitar
`--enable-real-send` por suposição.

Artefato final deste bloco: [tce-processos-completo-portatil-final11.zip](C:/Users/slvma/Downloads/Github/Complementação%20de%20Atos/work/tce-extractor/outputs/tce-processos-completo-portatil-final11.zip), com 98.269.518 bytes e SHA-256
`e69008c18afbda3c04cc2dd243d57e975dfcf4f87847a8cbe32379dc5cfe2242`. A
extração passou `TESTAR-PACOTE.ps1` 6/6 e o smoke de Chrome descartável passou
1/1. O ZIP final10 foi preservado.

Checkpoint Git final: commit `e7564c1` (`feat: automate marker batch
workflow`) criado após `git diff --cached --check`. O working tree foi
confirmado sem alterações após o commit. `git remote -v` não retorna remoto
configurado neste checkout; nenhum push foi feito ou afirmado.

## Atualização de implementação — frames reais do Complementar Ato — 09/09/2026

As capturas e a fundamentação identificam `botoesNovo.asp` como frame separado
do formulário `ComplementarAto.asp`. A extensão agora registra o frame de
botões quando encontra exatamente um controle habilitado com texto **Complementar
Ato**, mantendo o frame do formulário como a única fonte para releitura da
identidade e dos sete campos. O comando de envio carrega `frame_id` do botão e
`form_frame_id` do formulário; o worker aceita o comando somente do frame de
botões autorizado e encaminha duas verificações de estado ao frame do
formulário, antes do consumo e antes do clique.

O registro é persistido em `storage.session`, invalidado junto com a navegação
da aba e rejeitado quando há mais de um frame de botão elegível. O observador
de resultado continua obrigatório no caminho de produção; ausência dele não
consome comando nem clica. Foram adicionados os contratos tipados
`SUBMIT_FRAME_READY` e `AUTO_VERIFY_SUBMIT_STATE`, com autorização de origem,
aba, frame, geração, identidade e hash dos campos.

TDD do bloco: o RED inicial teve 2 falhas esperadas (método de registro ausente
e verificação cruzada inexistente); o GREEN passou depois da implementação.
Suíte JavaScript completa: **272 testes, 272 aprovados, 0 falhas**. A suíte
Python ampla teve uma falha transitória de `test_prepare_transfer` causada
por disputa de arquivo temporário no Windows; a reprodução isolada passou
**1/1**. A suíte Python será repetida antes do commit final. O ZIP final12
será gerado somente após essa repetição e terá auditoria e smoke do pacote
extraído.

Este bloco não altera o estado real do portal: não fecha o Chrome autenticado,
não reinicia o runner existente, não preenche ato real e não clica em envio.
DOM live da Área Restrita, observação/reabertura e qualificação real continuam
gates separados da seção 14.2.

## Atualização de implementação — lote automatizado por marcador — 09/09/2026

Foi implementada a busca e descoberta de lote por marcador na extensão:

- `RunSpec`/bridge/API aceitam `marker` textual fechado e o persistem sem
  permitir payload arbitrário.
- `portal-navigation.js` identifica o select ligado a “Marcador”, seleciona a
  opção exata, clica somente no “Consultar” do escopo correspondente e inclui
  o marcador observado no snapshot.
- A tabela usa o cabeçalho “Interessado” para não confundir o nome com os
  ícones anteriores mostrados nas capturas. A fila por marcador só aceita uma
  linha quando a ação semântica “Complementar Ato” é observável; identidade
  canônica sem essa ação fica pendente.
- `automation-controller.js` confirma o marcador antes da primeira coleta, em
  cada página e em cada retorno; pagina até o fim e congela apenas a fila
  filtrada. O painel tem o campo “Marcador do lote (opcional)” e mostra o
  marcador da execução.

Testes do bloco: 99 testes JS focais passaram; o contrato Python de criação de
execução por marcador passou 1/1; `git diff --check` passou. A execução real
continua sem envio: o Chrome autenticado não foi fechado/reiniciado e a rota
observada ainda não expôs o formulário/ação necessários.

Arquivos alterados neste bloco: `content/portal-navigation.js`,
`background/automation-controller.js`, `lib/messages.js`,
`lib/automation-schema.js`, `lib/bridge-client.js`, `sidepanel/panel.html`,
`sidepanel/panel.js`, `sidepanel/panel-view.js`, `portable/app/local_service.py`
e os testes correspondentes.

Próxima retomada segura: na mesma janela autenticada, abrir manualmente a
Área Restrita correta, selecionar um marcador e parar antes do clique final;
então capturar o DOM sanitizado das linhas e do formulário. Não ampliar a
allowlist nem habilitar `--enable-real-send` por suposição.

## Atualização de retomada autenticada — 09/09/2026

O operador informou que a Área Restrita também está autenticada e pediu
continuidade sem fechar o Chrome. O Chrome descartável atual foi mantido aberto;
não reiniciar o runner nem o perfil sem um novo checkpoint humano, pois a sessão
pode ser perdida.

No perfil `C:\Users\slvma\AppData\Local\Temp\tce-real-chromium-profile-20260909-i`,
o runner alcançou a rota autenticada de “Meus Processos” em
`https://processos.tce.rn.gov.br/`. A captura sanitizada atual confirma
`authenticated_ui_signal=true`, `local_storage_auth_signal=true`,
`route_signals.dashboard=true` e `route_signals.meus_processos=true`, com 3
formulários, 160 controles, 70 links e 88 botões visíveis. Nenhum ato foi
aberto, nenhum campo foi preenchido e `submission_performed_by_runner=false`.
Não há ação exata `Complementar Ato` na tela atual e o origin efetivo não é a
allowlist da extensão (`novaarearestrita.tce.rn.gov.br`); não alterar o
manifesto sem observar a tela real autorizada.

O sanitizador recebeu um probe adicional, testado em fixture local, que retorna
somente sinais booleanos/estruturais, IDs conhecidos e contagem de chaves de
processo; nunca retorna token, nomes, texto bruto ou URL com hash. O RED foi
observado por `KeyError: process_key_count` e o GREEN passou em 1/1 com
`python -m unittest test_real_portal_session -v`.

## Atualização de implementação local — qualificação e pacote final10

Foi adicionado `portable/app/qualification.py`, com validação fail-closed e
versões exatas para extensão `1.1.0`, serviço/schema jurídico/regras e
classificador `portal-outcome-v1`. O serviço agora aceita `--enable-real-send`
somente quando `<workflow_root>/automacao/qualificacao.json` existe, tem schema
estrito, hashes SHA-256 válidos, ID de evento e versões iguais às atuais; sem a
flag ou com qualquer divergência, `real_send_enabled` permanece falso e o lote
comum devolve `REAL_SEND_DISABLED`. O arquivo é estado local e não é colocado
no ZIP.

A allowlist pública e o diagnóstico `TESTAR-PACOTE.ps1` agora incluem
`app\qualification.py`. O teste de contrato teve RED por módulo ausente e
GREEN após a inclusão. O ZIP final10 foi recomposto em caminho separado:
95.839.875 bytes, SHA-256
`06fc7a5fc005f698b35f332239bafb26979b0f95569f0c9cdd97d81149d23920`; a cópia
extraída passou as 6 verificações offline e o smoke Chrome descartável passou
1/1 (`pair`, capabilities, sincronização e token de sessão).

O smoke revelou ainda uma regressão de observabilidade: a sincronização do
dataset apagava o texto “Mesa local conectada.”. O teste JS reproduziu RED e a
correção mínima passou o teste focado; o status final agora mantém o prefixo de
conexão e informa que nenhum campo foi preenchido.

Verificação final do bloco: `python -m unittest test_automation_qualification
test_automation_api test_package_audit -v` executou 67 testes, aprovou 65,
falhou 0 e teve 2 skips ambientais; `npm test` executou 256/256; `git
diff --check` passou.

Este bloco foi commitado em `4dd10c0` (`feat: gate real send by
qualification`). O repositório continua sem remoto configurado; nenhum push foi
feito.

Último checkpoint sem mutação: `GET http://127.0.0.1:18744/health` respondeu
`401`, confirmando que a ponte continua escutando e protegida; a captura real
ainda mostra a lista autenticada, sem formulário/ato aberto. A janela não deve
ser fechada ou reiniciada. Para retomar, o operador precisa abrir manualmente
um formulário “Complementar Ato” nessa mesma janela e parar antes do botão de
envio; então a captura sanitizada e os três preflights poderão continuar.

Próximo passo seguro: mantendo esta janela aberta, obter a tela de formulário
real na Área Restrita e localizar três atos representativos por navegação
supervisionada. Só depois fazer preflight sem envio. O primeiro clique real e o
lote continuam bloqueados até a observação/reabertura e a qualificação.

## Atualização de execução real — 09/09/2026

O pacote final8 foi extraído em perfil/pasta temporários e passou a auditoria
`TESTAR-PACOTE.ps1`. O `INICIAR.cmd` real foi executado pelo teste opt-in
`test_portable_launcher.py` e iniciou o serviço antes de exibir o menu. O
smoke `test_portable_zip_browser_smoke.py` confirmou `pair`, capabilities e
token de sessão da extensão no Chrome descartável. Artefato temporário:
95.838.420 bytes, SHA-256
`25223A75101031BBFD70CA2BD9750A507C4D630660406608927E7A60EAC44E17`.

Com autorização explícita do usuário para o teste real, o runner
`real_portal_session.py` abriu outro perfil descartável, pareou a extensão e
acessou o portal oficial. O inventário sanitizado está em
`work/tce-extractor/outputs/real-portal-dom-sanitized-2026-09-09.json` e
contém apenas estrutura/contagens/origens. O portal respondeu em
`https://processos.tce.rn.gov.br/` na tela de login: 1 formulário, 3
controles e ação `ENTRAR`; nenhum ato foi aberto, nenhum campo foi preenchido
e nenhum envio ocorreu. A extensão ficou conectada ao serviço local, mas não
há injeção esperada na origem inicial `processos.tce.rn.gov.br`, que difere da
allowlist atual `novaarearestrita.tce.rn.gov.br`.

O runner foi endurecido após uma corrida de inicialização: aguarda o `init` do
painel e a habilitação do botão antes do `pair`, registra apenas o status
sanitizado em caso de falha e recarrega uma vez a SPA se o corpo vier vazio.
Um teste isolado confirmou `pair=200` e `/api/v1/dataset=200` fora do painel;
os serviços concorrentes/locks obsoletos foram removidos somente nas pastas
temporárias do teste.

Checkpoint de retomada: fazer login manualmente na janela descartável, sem
compartilhar credenciais, e responder `continue`. Depois disso, capturar a
origem/DOM autenticados, localizar três atos representativos e executar apenas
preflight supervisionado antes de qualquer primeiro envio. Se o login não
redirecionar para a origem permitida ou não expuser a tela esperada, parar e
registrar o bloqueio; não ampliar a allowlist por suposição.

## Estado atual

Branch: `codex/fundamentacao-automatico`.

As entregas locais das Fases 9 e 10 estão no checkout e foram commitadas em
`25ca99e` (`test: qualify local automation and package release`), `692ed27`
(`test: add formal panel accessibility gate`), `61dce28` (`feat: add opt-in
automation pilot guard`) e `c4246c6` (`fix: route automation controls through
worker`), seguidos de `453a043` (`docs: record portable runtime probe`) e
`0ec7109` (`docs: reconcile local phase tasks`), com documentação intermediária
em `9ad2a50`, `76e37f5`, `5e1617c` e `407ca6c`, além de `42eeeac`
(`fix: require portable service readiness`) e `21e9a63` (`docs: record launcher
gate boundary`), `9d21441` (`feat: harden automation confirmation recovery`),
`a8ae6e2` (`fix: complete portable package inventory`), `1fcfad8` (`docs:
record verified portable composition`) e `e1d9618` (`test: verify portable
bridge startup sequence`), seguido de `8de1b87` (`docs: record portable bridge
qualification`). O repositório não possui remoto configurado, portanto não há
push.

O launcher portátil agora exige `service.json` produzido pelo próprio helper;
se o processo encerra ou não confirma a ponte, o menu não fabrica PID/porta e
preserva o modo manual.

Atualização final de 09/09/2026: o commit `03b5b8e` (`fix: qualify portable
bridge in Chrome`) corrigiu o listener do código de pareamento no painel, a
opção CORS do cliente loopback e a compatibilidade de autenticação para GETs
sem `Origin` (somente leituras; mutações continuam exigindo origem de
extensão). O smoke `test_portable_zip_browser_smoke.py` abriu a extensão do
ZIP final6 em Chrome com perfil descartável, iniciou o Python portátil,
pareou, sincronizou dataset/capabilities e confirmou o token em
`chrome.storage.session`. ZIP final6: 95.838.384 bytes, SHA-256
`4ecbbf150a13e1f45b454a5097f67329d7086994cef3cde24d67b9ad54f73770`.
Nenhum portal real, ato real ou envio foi acessado.

## Arquivos principais

- `work/tce-extractor/test_automation_browser.py`
- `work/tce-extractor/tests/fixtures/automatic-portal/simulator.html`
- `work/tce-extractor/tests/fixtures/automatic-portal/form.html`
- `work/tce-extractor/portable/test_automation_integration.py`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/automation-controller.test.mjs`
- `work/tce-extractor/portable/app/package_audit.py`
- `work/tce-extractor/package_complete_archive.py`
- `work/tce-extractor/test_package_audit.py`
- `work/tce-extractor/test_portable_end_to_end.py`
- `work/tce-extractor/test_panel_accessibility.py`
- `work/tce-extractor/test_automation_api.py`
- `work/tce-extractor/portable/app/automation_store.py`
- `work/tce-extractor/portable/app/bridge_auth.py`
- `work/tce-extractor/portable/app/local_service.py`
- `work/tce-extractor/portable/app/qualification.py`
- `work/tce-extractor/portable/extensao-complementar-ato/lib/bridge-client.js`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/automation-schema.test.mjs`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/automation-controller.test.mjs`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/panel.test.mjs`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/bridge-client.test.mjs`
- `work/tce-extractor/test_bridge_auth.py`
- `work/tce-extractor/test_local_service.py`
- `work/tce-extractor/test_portable_zip_browser_smoke.py`
- `work/tce-extractor/portable/extensao-complementar-ato/sidepanel/panel.js`
- `work/tce-extractor/portable/TESTAR-PACOTE.ps1`
- `work/tce-extractor/empacotar-coletor-portatil.ps1`
- `work/tce-extractor/test_automation_qualification.py`
- `work/tce-extractor/portable/extensao-complementar-ato/manifest.json`
- `docs/notes/2026-09-08-fundamentacao-automatico-plano-fases.md`
- `docs/notes/2026-09-09-fase9-10-task-9-10-report.md`

## Testes e decisões

O primeiro teste SQLite esperava `running` depois da reabertura. A implementação
correta do store pausa execuções ativas durante recovery; o teste foi ajustado
para exigir `paused`, preservar `unconfirmed`/`pending` e aceitar somente
`run_resumed` explícito. A primeira suíte ampla revelou que o fixture de pacote
não copiava `legal_context.py`; o fixture foi corrigido e
`test_portable_end_to_end` ficou verde.

O teste de navegador usa a API `chrome.tabs.sendMessage` a partir de uma página
da extensão, pois content scripts rodam em isolated world. O envio é bloqueado
sem bridge e o botão sintético permanece sem clique. Isso é uma qualificação
local de integração, não uma prova do portal real.

O gate adicional de acessibilidade passou em 3/3: contraste mínimo dos tokens
de texto/status/ação/foco, `lang=pt-BR`, IDs únicos, targets de labels existentes
e cópia estática de segurança. O smoke combinado de painel e automação passou
em 5/5.

O runtime staging disponível foi executado diretamente com `-I -B -s`: Python
3.14.4, SQLite 3.50.4 e imports de `automation_store`/`local_service` passaram.
Depois, o packager público foi corrigido para copiar oito assets de automação
que estavam ausentes da allowlist. A validação de startup revelou também que
`local_service.py` precisava de `automation_report.py`, `automation_store.py` e
`legal_context.py`; os três módulos agora são copiados explicitamente. A
composição final extraída em pasta limpa passou runtime Python/Tesseract,
manifesto, auditoria pública e diagnóstico PowerShell: ZIP final6 de
95.838.384 bytes, SHA-256
`4ecbbf150a13e1f45b454a5097f67329d7086994cef3cde24d67b9ad54f73770`.

No mesmo ZIP, o serviço portátil publicou `service.json`, aceitou `pair=200`,
respondeu `capabilities=200` autenticado com `real_send_enabled=false`,
rejeitou o reuso do código com 401 e foi encerrado pelo helper. O smoke Chrome
adicional também passou no mesmo pacote extraído; isso é evidência local da
integração, não qualificação do portal real.

O diagnóstico PowerShell também foi alinhado à permissão `alarms` do manifesto.
O RED foi observado primeiro no contrato da allowlist (8 assets) e depois no
teste PowerShell do manifesto; ambos ficaram verdes após as correções. Isso é
evidência offline e de integração local da composição, não qualificação do
portal real.

O smoke Chrome acrescentado depois encontrou e corrigiu duas falhas de
integração locais: o botão não era reabilitado ao editar o código e os GETs
autenticados chegavam sem `Origin`. Há regressões para ambos os casos. A
extração final6 passou `TESTAR-PACOTE.ps1`, pareamento, dataset e capabilities
no Chrome descartável; o fixture limpa `service.json` anterior e usa um lote
sanitizado válido. A versão final do pacote é o hash registrado no bloco de
estado acima.

O incidente do launcher foi coberto em TDD: o teste RED reproduziu a ausência
de confirmação para um processo encerrado; a correção passou no teste completo
do menu portátil, 75/75, e foi commitada em `42eeeac`. A mudança é local e
não converte o incidente de pareamento real da seção 14.2 em PASS.

O bloco seguinte fechou gates locais da Fase 7: histórico durável por identidade
impede reenvio em outro lote, hash alterado retorna `ACT_REQUIRES_REVIEW`,
reconciliação após `unconfirmed` exige leitura explícita, `send_confirmed`
renderiza o relatório antes da resposta da API e o submitter aguarda observação
por 30 s com uma releitura final. Tudo está em `9d21441`; isso não habilita
envio real.

Foi adicionada uma regressão de segurança na API: execução comum não pode
consumir comando quando `real_send_enabled=false`; o serviço devolve
`REAL_SEND_DISABLED` sem persistir `command_consumed`. O piloto opt-in ainda não
foi executado no portal; sua infraestrutura local agora exige `--automation-pilot`,
identidade explícita, conserva o limite de um comando após reinício e recebe
`AUTO_START`/`AUTO_PAUSE`/`AUTO_RESUME`/`AUTO_STOP` no worker/controller do
painel.

Três auditorias Luna xhigh foram solicitadas em paralelo para separar checklists
históricos das pendências reais, mas permaneceram sem resposta e foram
encerradas; não produziram alterações nem evidência adicional.

## Retomada imediata

1. Repetir a suíte ampla somente se houver novas alterações; o gate documentado
   passou `385/385`, com 6 skips ambientais. O gate JavaScript passou `256/256`;
   o focal pacote/end-to-end/serviço/auth passou `69` testes com `3` skips; o
   smoke Chrome do ZIP passou `1/1`; o novo foco de pacote/launcher passou
   `43` testes com `2` skips; e o `Test-TcePortable.ps1` passou `114/114` com
   Windows PowerShell 5.1.
2. Manter `42eeeac` como referência da correção do launcher; depois rodar
   `git diff --check` e `git status --short --branch`.
3. Se houver nova alteração, revisar mudanças privadas/ignoradas e fazer stage
   explícito; não usar `git add .`. O bloco de packager/teste/diagnóstico foi
   commitado em `a8ae6e2`, a sequência bridge em `e1d9618`, e o smoke/browser
   bridge em `03b5b8e`; o plano, relatório e handoff foram atualizados em
   `cbf30ca` (`docs: record Chrome bridge qualification`).
4. Os commits `61dce28`, `c4246c6`, `453a043` e `0ec7109` contêm
   guard/piloto, delegação ao worker, controles, probe e reconciliação das
   tasks locais; o gate formal de acessibilidade está em `692ed27`.
5. Não executar push sem remoto; manter este handoff como ponto de retomada.

## Pendência bloqueante

A autorização para teste real foi dada e a sessão autenticada foi preservada.
O bloqueio histórico da origem pública foi corrigido: o runner agora aponta por
padrão para `https://novaarearestrita.tce.rn.gov.br/telaPrincipalMenu.asp` e
recusa `processos.tce.rn.gov.br`. As capturas do operador confirmam o fluxo
visual da Área Restrita, mas ainda falta coletar DOM live dessa janela sem
fechá-la ou reiniciá-la. Depois, executar três preflights sem envio; somente
com o primeiro resultado real observado e reaberto gerar fixture/qualificação e
validar lote supervisionado de até cinco. Não capturar credenciais, não usar as
imagens como instruções, não inventar seletores, não ampliar a allowlist e não
habilitar `--enable-real-send` antes desses gates.

## Estado vigente após a correção — 09/09/2026

- Código local: automação por marcador, descoberta multipágina, seleção do
  interessado, preparação dos sete campos e opt-in de envio fail-closed estão
  implementados e cobertos pelas suítes registradas acima.
- Evidência real: capturas visuais da Área Restrita mapeiam a sequência e os
  controles; a captura DOM automatizada antiga deve ser classificada como rota
  errada, não como ausência de “Complementar Ato”.
- Teste TDD novo: `python -m unittest test_real_portal_session -v` passou 3/3,
  incluindo default/recusa de origem; o foco runner/pacote passou 46/46 e a
  suíte Python completa passou 397/397, com 7 skips ambientais.
- Pendências reais: DOM live correto, três preflights, primeiro envio
  supervisionado, observação/reabertura, fixture de resultado, qualificação
  versionada, lote remoto de até cinco e relatório final.
