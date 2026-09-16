# Fechamento dos gates locais de release - 16/09/2026

## Status

Os tres gates locais pendentes da retomada anterior foram fechados, o gate
unico de release passou verde de ponta a ponta, e tres falhas reais de produto
foram encontradas e corrigidas. Nenhum ato foi preenchido, concluido ou
enviado; a qualificacao portal-real continua pendente e exige sessao humana
isolada.

## Evidencia do gate unico

Comando: powershell.exe -NoProfile -ExecutionPolicy Bypass -File
work/tce-extractor/verify-project.ps1 -TimeoutSeconds 900

| Metrica | Valor |
|---|---:|
| Estagios | 7 |
| Executados | 1174 |
| Aprovados | 1172 |
| Falhados | 0 |
| Skips | 2 |
| Codigo de saida | 0 |

Estagios: extension, web, python, powershell, package, automation, diff -
todos passed.

## Correcoes aplicadas

### 1. Removido o bypass de TLS do runner de qualificacao

real_portal_session.py usava --ignore-certificate-errors, o que impedia usar
esse runner na qualificacao portal-real. A configuracao foi extraida para
build_launch_args() sem o bypass, e validate_session_profile() exige perfil
explicito dentro de dados-locais (None mantem o perfil temporario).

TDD: RED por ImportError; GREEN 8/8.

### 2. Gate de release passou a cobrir a automacao

verify-project.ps1 rodava unittest discover -s portable, que nao enxerga os
contratos de automacao da raiz. Foi adicionado o estagio automation (64
testes, codigo de saida 16) e tests/Test-ProjectVerification.ps1 foi
atualizado para sete estagios.

TDD: RED no teste do verificador; GREEN 45/45.

### 3. Instabilidade do painel estabilizada

tests/panel.test.mjs falhava em media 4 de 12 execucoes em "automatic
submission requires capability and an action-time confirmation". Causa: o
teste sincronizava com numero fixo de ticks e marcava o checkbox depois;
quando o pareamento demorava, o render seguinte zerava o checkbox antes de
startAutomation() ler o valor. O produto esta correto (o checkbox e reiniciado
de proposito e a confirmacao e exigida no momento da acao). Correcao:
sincronizar por estados observaveis, como nos outros casos do arquivo.

Evidencia: 25/25 verdes (antes 4/12 falhavam); painel 53/53; extensao 406/406.

### 4. Corrida de leitura do marcador de runtime

A execucao ativa drena entre metadata.exists() e metadata.read_text(). No
Windows a leitura falha nesse intervalo, e _active_runtime() classificava como
marcador invalido (TransferBusyError), recusando a transferencia com o runtime
ja drenado. Correcao em portable/app/prepare_transfer.py: FileNotFoundError
nessa leitura significa runtime inativo; erros de conteudo continuam
fail-closed.

TDD: RED deterministico com o erro de producao; GREEN test_prepare_transfer
12/12 e estagio package 81/81.

### 5. Modo de seguranca do gravador deixou de ser decorativo

qa_portal_recorder.py aceitava --safety-mode reversible_fill sem nenhum
caminho de escrita nem restauracao: o operador acreditava estar no modo
reversivel supervisionado e apenas observava. Correcao: validate_safety_mode()
ligada em start(); o modo exige runner supervisionado verificado e aborta
antes de abrir o Chrome.

TDD: RED por ImportError; GREEN 16/16. CLI: modo reversivel aborta;
observe_only inalterado.

### 6. Contrato de dependencias do portal e deteccao de mudanca (Fase 1)

A captura estrutural do runner de qualificacao usava uma allowlist propria com
quatro IDs que a extensao nao usa (btnComplementar, formComplementar,
iframeOBJ, radioInteressado) e cobria apenas UM dos nove controles que a
automacao realmente le. Ou seja: nao havia como detectar mudanca do portal nos
campos dos atos, entrega explicita da Fase 1.

Correcoes em real_portal_session.py:
- PORTAL_DEPENDENCY_IDS declara os nove controles lidos pela extensao, com
  fonte em content/form-detector.js (FIELD_MAP/SENTINEL_IDS) e o rotulo exato
  de envio de content/portal-submit.js.
- _sanitize_page() recebe a lista por argumento; a allowlist interna foi
  substituida pelo contrato (uma unica fonte de verdade).
- compare_portal_snapshot() compara observacao contra contrato e reporta
  missing_ids, unexpected_ids e changed_signals, fail-closed quando a
  observacao esta ausente.
- A sessao agora grava portal_contract_ids, portal_missing_contract_ids e
  portal_drift em cada captura, inclusive no laco --stay-open.

TDD: RED por ImportError das duas funcoes; GREEN 14/14. A fiacao foi provada
pelo caminho real de page.evaluate (o teste de captura agora informa
txtModalidade e txtNumeroProcesso). Efeito colateral intencional: com o
contrato correto, o runner passa a reportar drift quando o portal nao expoe os
campos dos atos - antes esse caso passava silenciosamente.


### 7. Gerador do artefato de qualificacao (real_send_enabled)

O validador fail-closed de qualificacao existia e estava ligado ao servico
local, mas nao existia nenhum gerador do artefato: o passo de criar
automacao/qualificacao.json dependia de escrever JSON a mao.

Correcao em portable/app/qualification.py:
- inspect_qualification_content() extrai a validacao do conteudo ja decodificado;
  inspect_qualification() passa a delegar para ela (sem mudar o comportamento
  externo nem os testes existentes).
- write_qualification() grava o artefato e reusa o mesmo inspetor antes de
  escrever, recusando fixture_hashes vazios, malformados ou duplicados e
  real_event_id vazio ou invalido.

TDD: RED por ImportError de write_qualification; GREEN 8/8 em
test_automation_qualification, incluindo um teste de integracao que prova que
o artefato gravado e aceito pelo gate do servico com o EXTENSION_VERSION real
(1.1.0). O que falta continua sendo o evento real, nao o formato.


### 8. Versao da extensao presa ao manifest distribuido (fail-open corrigido)

local_service.py mantinha EXTENSION_VERSION = "1.1.0" como literal a mao,
enquanto o manifest distribuido tambem declara 1.1.0 (e package_audit.py tem
um terceiro literal igual). Como a qualificacao real fica presa a versao da
extensao, subir o manifest sem subir esse literal faria uma qualificacao
antiga liberar real_send_enabled para uma versao nunca qualificada - exatamente
o risco de "versionamento de regras" do relatorio tecnico.

Correcao: local_service._shipped_extension_version() le
portable/extensao-complementar-ato/manifest.json e passa a ser a unica fonte
de verdade; o literal permanece so como fallback quando a arvore nao inclui a
extensao (manifest ausente ou invalido). Nenhum comportamento externo mudou
enquanto os valores concordam.

TDD: RED no teste de integracao que exige o valor lido do manifest (o literal
nao e aceito); GREEN test_automation_qualification 13/13, incluindo os dois
casos de fallback e um caso que prova que o valor vem do manifest (9.9.9).

### 9. Trava contra deriva da versao das regras

RULES_VERSION = "legal-foundation-v2" existe em local_service.py e
LEGAL_FOUNDATION_RULES_VERSION em lib/legal-foundation.js, sem nenhum teste
que os mantivesse iguais. Deriva ali muda a regra aplicada sem falhar nada.

Correcao: dois testes em test_qa_workflow.py leem a declaracao real do JS e
exigem igualdade com o servico (e com a regra da versao publicada). Nao ha
mudanca de codigo de producao; a trava e o teste.

TDD: GREEN test_qa_workflow + test_qa_matrix_runner 18/18.


### 10. Indicadores de desempenho da operacao (Fase 4)

A Fase 4 pede "indicadores de desempenho" e "monitoramento continuo", mas so
existia relatorio por execucao (automation_report.py) e listagem paginada
(list_runs). Nao havia nenhuma agregacao entre execucoes, ou seja, sem como
acompanhar taxa de confirmacao, falhas ou fila pendente ao longo do tempo.

Correcao:
- automation_store.operation_indicators() agrega, por workflow root, apenas
  contagens: runs_total, by_run_state, items_total e os totais confirmed,
  unconfirmed, failed, pending e filled. Nenhum identificador de processo ou
  interessado sai do metodo, e ele nao altera estado (somente SELECT).
- local_service expoe GET /api/v1/automation/indicators com o mesmo envelope
  autenticado das demais rotas ({api_version: 1, ...}).

TDD: RED por AttributeError (metodo inexistente) e depois 404 na rota; GREEN
test_automation_store 23/23 (2 novos) e test_automation_api 25/25 (1 novo,
incluindo 401 sem token). Os novos testes tambem exigem que a resposta nao
contenha os process_key usados na fixture.

Nota: a tabela de rotas em docs/notes/2026-09-08-fundamentacao-automatico-plano-fases.md
e registro historico de um plano de fase e nao foi alterada; o endpoint novo
fica documentado aqui.

## Ex-bloqueio critico: observador de resultado IMPLEMENTADO em 16/09

Auditoria de 16/09 (somente leitura) encontrou a lacuna mais importante do
caminho de envio real: o observador de resultado do portal nao esta
implementado em lugar nenhum.

Evidencia:

- content/portal-submit.js le globalThis.TCEPortalOutcome em dois pontos
  (hasPortalOutcomeObserver() na linha 28 e defaultWaitForOutcome() na 189).
- Busca com --no-ignore em todo o checkout retorna exatamente 4 ocorrencias,
  todas LEITURAS, sendo duas no fonte e duas na extracao distribuida. Nenhuma
  escrita, definicao, injecao ou manifest entry cria esse objeto.
- Nao existe permissao "scripting" no manifest nem injecao em MAIN world;
  nada define TCEPortalOutcome.

Consequencia no fluxo automatico: em submitVerifiedAct(), quando
waitForOutcome e o default de producao, requireOutcomeObserver fica true;
hasPortalOutcomeObserver() retorna false e a funcao lanca
OUTCOME_OBSERVER_UNAVAILABLE antes de clicar. O comportamento e fail-closed e
correto - nenhum clique ocorre e nenhum envio parcial e feito - mas significa
que o estado "confirmed" e inalcancavel no portal real com este pacote.

Por que os testes nao revelam isso: os testes de portal-submit injetam
waitForOutcome explicitamente (tres casos com accepted+persisted). A
classificacao classifyPortalOutcome() e o caminho de recusa estao cobertos; a
producao do observador, nao.

Impacto no objetivo: este e o mesmo item que o plano de fases lista como
pre-requisito fail-closed ("sem tres preflights reais, observador de
resultado, automacao/qualificacao.json ... nao e seguro declarar o envio real
funcionando"). O servico tambem mantem real_send_enabled=false, portanto ha
dois bloqueios independentes.

O que isso muda na pratica: executar os tres preflights portal-reais e
necessario, mas NAO e suficiente para liberar envio. Antes de qualquer envio
supervisionado e preciso implementar e qualificar o observador de resultado
(ler accepted/persisted e a identidade pos-envio no portal), com teste de
integracao e evidencia real. Este trabalho ja esta autorizado como parte do
objetivo e nao depende de login; o que depende de humano continua sendo a
observacao no portal.


### 11. Observador de resultado do portal (era o bloqueio critico)

O bloqueio documentado na revisao anterior foi resolvido neste turno. O
adaptador globalThis.TCEPortalOutcome, lido por portal-submit.js mas nunca
definido, agora existe em content/portal-submit.js.

O que foi implementado:

- readPortalOutcome(documentRef, expected) le o snapshot tipado de
  portal-navigation (a mesma leitura usada em toda a automacao) e procura a
  identidade esperada. So retorna persisted quando a classificacao observada
  e ATO_COMPLEMENTADO, que e a unica que prova gravacao pelo portal.
  Identidade diferente, ato ainda pendente ou ausencia do leitor resultam em
  accepted/persisted falsos ou timeout - nunca em confirmacao inventada.
- createPortalOutcomeObserver({documentRef}) expoe read() e subscribe() com
  MutationObserver + polling de 1 s. subscribe() so notifica quando a
  persistencia e observada.
- installPortalOutcomeObserver() registra o adaptador global; o bundle de
  producao o instala automaticamente antes de installPortalSubmit().

Bug real encontrado ao escrever o teste ponta a ponta: defaultWaitForOutcome
chamava adapter.read(documentRef) e adapter.subscribe(documentRef, notify)
sem passar a identidade esperada, e o adaptador tinha assinatura na ordem
errada. Sem essa correcao o leitor jamais casaria a identidade e todo envio
terminaria em unconfirmed mesmo com o portal gravando. Corrigido: a identidade
do comando agora e repassada como expectativa nos dois caminhos.

TDD: RED por ImportError das tres funcoes novas; GREEN tests/portal-submit.test.mjs
14/14 (4 novos) e npm test da extensao 410/410 (era 406). O teste ponta a ponta
instala o observador, dispara AUTO_SUBMIT_COMMAND pelo listener de producao e
exige status confirmed, exatamente 1 consumo e exatamente 1 clique - o mesmo
cenario que antes falhava em OUTCOME_OBSERVER_UNAVAILABLE.

Leitura entre documentos: o resultado pode ser renderizado no proprio frame, no
documento de topo ou em um frame IRMAO do quadro de acoes (o portal usa frames
irmaos para formulario e botoes). readPortalOutcome percorre o documento local,
o topo e os contentDocument dos iframes alcancaveis, ignorando qualquer leitura
bloqueada por acesso; se nenhuma leitura produzir evidencia o retorno continua
sendo timeout/unconfirmed. Coberto por teste proprio que exige a leitura no
documento do frame irmao.

Leitura entre frames: o resultado pode ser renderizado no documento deste frame
ou no topo (o portal usa frames irmaos para formulario e quadro de acoes).
readPortalOutcome tenta o documento local e depois globalThis.top.document,
ignorando silenciosamente leituras bloqueadas por acesso; se nenhuma leitura
produzir evidencia, o retorno continua sendo timeout/unconfirmed.

Limite mantido: o observador le o portal; ele nao clica, nao preenche e nao
navega. A evidencia ainda precisa ser produzida em sessao real - o que mudou e
que agora existe caminho de codigo para confirmar, e nao mais um aborto
garantido.

## Evidencia adicional da suite completa da raiz (16/09)

O gate unico NAO executa todos os modulos de teste da raiz. Ele roda
`unittest discover -s portable` (2 modulos) mais cinco modulos citados a mao
(`test_extension_zip_packager`, `test_package_complete_archive`,
`test_package_audit`, `test_prepare_transfer`) e o estagio `automation` com
cinco modulos. Medicao direta: existem 49 modulos `test_*.py` na raiz e 40
deles nao sao executados por nenhum estagio.

Para nao deixar esse universo sem prova, a suite completa da raiz foi
executada explicitamente:


| Comando | Resultado |
|---|---|
| `python -m unittest discover -s . -p 'test_*.py' -q` | 495 executados, OK, 8 skips, saida 0 |


Isso cobre os 40 modulos fora do gate, incluindo `test_real_portal_session`,
`test_local_service`, `test_batch_runner`, `test_html_generator`,
`test_workflow_state` e `test_evidence_geometry`. Continua valendo que esses
testes nao entram no gate unico: quem roda `verify-project.ps1` obtem 1174
executados, nao 495+1174.

Melhoria recomendada (nao aplicada): trocar a lista manual de modulos do
estagio `package`/`automation` por descoberta na raiz
(`unittest discover -s . -p 'test_*.py'`), para que o gate cubra tambem os
arquivos futuros. Uma tentativa foi feita com teste RED proprio e foi
interrompida pelo usuario antes de aplicar; o gate permanece como esta no
commit `fb60cc6`.

## Prova em Chrome real: o observador esta ativo (16/09)

O teste unitario prova o observador; faltava provar que ele esta de fato
registrado na extensao carregada no Chrome real. Sondagem somente leitura
executada com o simulador local:

1. Abriu o simulador, carregou a extensao empacotada e enviou
   `PORTAL_GET_SNAPSHOT` pelo caminho real de mensagens.
2. Resolveu o frame de formulario e montou um `AUTO_SUBMIT_COMMAND` com
   identidade, geracao e hash dos campos reais.
3. Resultado: `error_code = COMMAND_ALREADY_CONSUMED`, com
   `observer_unavailable = false` e `click_count = 0`.

Por que isso e prova: em submitVerifiedAct a checagem do observador
(`OUTCOME_OBSERVER_UNAVAILABLE`) acontece ANTES de `consumeCommand`, e
`COMMAND_ALREADY_CONSUMED` e o retorno de `consumeCommand` que falha DEPOIS.
Um retorno posterior implica que a checagem anterior passou:
`hasPortalOutcomeObserver()` devolveu verdadeiro no Chrome real com o manifest
real. O clique permaneceu em zero, ou seja, nenhum envio foi executado.

Limite: isso nao prova que o portal real classifica o ato como
`ATO_COMPLEMENTADO`; prova que o gate do observador nao bloqueia mais o caminho
de envio e que o observador esta registrado onde o envio o procura. A evidencia
de persistencia continua dependendo da sessao autenticada.

## Pacote distribuido: o que serve e o que nao serve (16/09)

Sondagens somente leitura contra a extensao EMPACOTADA em
`Versions/...-final-professor-ipern`, com o simulador sintetico local:

| Capacidade | Resultado no pacote distribuido |
|---|---|
| Lista autenticada (`PORTAL_GET_SNAPSHOT`) | ok, role `list` |
| Formulario e preflight (`GET_FORM_SNAPSHOT`) | ok, 7 campos |
| Preenchimento controlado (`APPLY_FIELDS`) | **ok** |
| Botao de envio clicado | 0 |
| Envio automatico (`AUTO_SUBMIT_COMMAND`) | `OUTCOME_OBSERVER_UNAVAILABLE` |

Ou seja: o pacote atual ja executa coleta, leitura do formulario e o
preenchimento controlado sem clicar no envio. O que ele NAO consegue e o
envio real, porque o `portal-submit.js` distribuido contem a guarda
`OUTCOME_OBSERVER_UNAVAILABLE` mas nao contem o instalador do observador
(2 referencias, 0 definicoes).

Comparacao arquivo a arquivo dentro da extensao: apenas
`content/portal-submit.js` difere entre pacote e fonte. `form-detector.js`,
`portal-navigation.js`, `automation-preflight.js`, `automation-controller.js`,
`service-worker.js`, `automation-schema.js` e `manifest.json` estao identicos.

Consequencia pratica para a proxima sessao:

- Os tres preflights e o preenchimento reversivel supervisionado PODEM ser
  executados com o pacote atual, porque dependem de preflight e APPLY_FIELDS.
- O envio supervisionado NAO pode: abortaria antes do clique. Para esse passo
  e necessario reempacotar com o `portal-submit.js` da fonte.
- Contraste medido: com o `portal-submit.js` da fonte, o mesmo probe chegou a
  `COMMAND_ALREADY_CONSUMED` (checagem do observador aprovada).

Observacao de contrato descoberta no caminho (nao e defeito): `APPLY_FIELDS`
so e aceito quando usa o MESMO `requestId` do `GET_FORM_SNAPSHOT` que o
antecedeu; com id diferente retorna `APPLY_BLOCKED`. O probe inicial usou ids
distintos e foi bloqueado; ao repetir com id compartilhado, o preenchimento
passou.

## Riscos residuais conhecidos (nao corrigidos)

- package_audit.py mantem o terceiro literal "1.1.0" como expectativa de
  auditoria (agora com teste que falha se divergir do manifest).
- _sanitize_page tem cobertura indireta (um cenario); o laco --stay-open nao
  tem teste de integracao.
- _read_pairing_code retorna None e o runner estoura em TypeError se o
  service.json nao aparecer em 10s (mensagem pouco clara, fail-closed).

## Cobertura de teste do que foi mudado

| Arquivo alterado | Teste que cobre |
|---|---|
| real_portal_session.py | test_real_portal_session.py (14) |
| qa_portal_recorder.py | test_qa_workflow.py (18) |
| portable/app/prepare_transfer.py | test_prepare_transfer.py (12) |
| portable/app/qualification.py | test_automation_qualification.py (13) |
| portable/app/automation_store.py | test_automation_store.py (23) |
| portable/app/local_service.py (indicators) | test_automation_api.py (25) |
| verify-project.ps1 | tests/Test-ProjectVerification.ps1 (45) |
| panel.test.mjs | tests/panel.test.mjs (53) |
| content/portal-submit.js | tests/portal-submit.test.mjs (15) |

## Arquivos alterados

- work/tce-extractor/portable/app/automation_store.py
- work/tce-extractor/test_automation_store.py
- work/tce-extractor/test_automation_api.py
- work/tce-extractor/portable/app/local_service.py
- work/tce-extractor/portable/app/qualification.py
- work/tce-extractor/test_automation_qualification.py
- work/tce-extractor/real_portal_session.py
- work/tce-extractor/test_real_portal_session.py
- work/tce-extractor/verify-project.ps1
- work/tce-extractor/tests/Test-ProjectVerification.ps1
- work/tce-extractor/portable/extensao-complementar-ato/tests/panel.test.mjs
- work/tce-extractor/portable/extensao-complementar-ato/content/portal-submit.js
- work/tce-extractor/portable/extensao-complementar-ato/tests/portal-submit.test.mjs
- work/tce-extractor/portable/app/prepare_transfer.py
- work/tce-extractor/test_prepare_transfer.py
- work/tce-extractor/qa_portal_recorder.py
- work/tce-extractor/test_qa_workflow.py
- este handoff

## O que continua pendente

1. A qualificacao portal-real permanece BLOCKED: sao necessarios os tres
   preflights reais em sessao Chrome isolada com login humano
   (ProcessonoSetor.asp, source_scope=sector_finalistic, marcador 6189,
   identidade processo/interessado exata, catalogo atual e seis campos
   obrigatorios).
2. Com os tres preflights verdes, um unico envio supervisionado - somente com
   autorizacao nova, imediata e especifica.
3. Executar os tres preflights reais, criar a fixture sanitizada do resultado
   e gerar automacao/qualificacao.json com write_qualification() usando os
   hashes da fixture e o id do evento real. O gerador e o validador agora
   existem e sao testados; falta somente o evento real. real_send_enabled
   continua false ate esse arquivo existir no acervo.
4. O piloto de ate cinco atos continua sujeito a qualificacao real.
5. Extracao distribuida desatualizada por um arquivo: Versions/...-final-professor-ipern
   contem o prepare_transfer.py anterior (80B68312.. vs 05CD6E87.. no fonte).
   Reempacotar exige staging verificado e e decisao do usuario.
6. Cobertura parcial de teste no runner de qualificacao: compare_portal_snapshot
   e portal_dependency_ids sao testados, mas _sanitize_page tem cobertura
   indireta (um cenario) e o laco --stay-open nao tem teste de integracao.

## Limites mantidos

- autoSubmit=false e real_send_enabled=false continuam sendo a fronteira segura
  ate a qualificacao real.
- Nenhum login, credencial, cookie, HAR, trace, PDF particular, envio,
  conclusao ou tramitacao foram produzidos nesta sessao.
- Versions/ nao foi tocado.
- O bypass de certificado permanece apenas em test_extension_browser.py
  (fixture de host local), nao no runner de qualificacao.

## Retomada

Ler junto de docs/notes/2026-09-16-automacao-complementacao-analise-handoff.md.
Comando do gate: verify-project.ps1 na raiz. Proximo passo continua sendo abrir
a extracao final-professor-ipern em sessao Chrome isolada com login humano,
repetir a observacao e executar apenas os tres preflights, com envio desligado.
