# Runbook - sessao de qualificacao portal-real (16/09/2026)

Guia executavel para a sessao humana de captura e login. Ele NAO executa envio:
o passo de envio continua atras de autorizacao nova, imediata e especifica.

## Pre-requisitos (verificados no checkout)

- Pasta pronta: `outputs/TCE-fixed-2026-09-16`
- Launcher: `INICIAR-CAPTURA-AREA-RESTRITA.cmd` dentro da pasta pronta
- Runner: `real_portal_session.py` dentro da pasta pronta
- Serviço local: `INICIAR.cmd` da própria pasta pronta

A pasta pronta já contém 739 registros, 14.179 PDFs, o JSON da extensão, a
extensão `1.1.0`, a ponte e o runtime. A extração em `Versions/` e os ZIPs
originais foram preservados.

## Passo 1 - iniciar a pasta pronta

    cd <pasta-pronta>
    .\INICIAR-CAPTURA-AREA-RESTRITA.cmd

O launcher abre a ponte, chama o runner e abre um Chrome descartável com a
extensão carregada, pareia o painel com a ponte e abre a Área Restrita. Ele
grava, em `dados-locais`, o
`recording.json` sanitizado, o `trace.zip` e o `network.har`; cliques, mudancas,
tentativas de envio, navegacoes, console e falhas ficam registrados apenas de
forma estrutural. Faca o login manualmente na janela que abrir. Nao ha
digitacao de credencial por automacao.

Durante o início, `INICIAR.cmd ponte` pode mostrar `Pressione qualquer tecla
para continuar`; pressione uma tecla uma vez para liberar o runner. Aguarde
`REAL_PORTAL_SESSION_READY`. Se o portal abrir uma autenticação do navegador
ou uma página de erro de rede, resolva a autenticação e a navegação manualmente
na janela descartável; o runner permanece somente observacional.

Quando a sessao estiver pronta ele imprime REAL_PORTAL_SESSION_READY e passa a
regravar o JSON de saida a cada ciclo (--poll-seconds, padrao 5s).

## Passo 2 - fazer o login e navegar

Faça o login manualmente na janela que abrir. Não há digitação de credencial
por automação. A ponte grava `dados-locais/bridge/service.json` com o código de
pareamento durante a inicialização.

## Passo 3 - conferir a evidencia capturada

O JSON de saida contem, sem texto privado:

- portal.origin e portal_extension_origin_match
- portal_authenticated_ui_signal e portal.process_key_count
- portal_drift (drift, reason, missing_ids, changed_signals)
- portal_missing_contract_ids
- recording.run_id, recording.event_count e recording.error_count
- submission_performed_by_runner (precisa ser false)

Se portal_drift.drift for true, PARE: o portal mudou em relacao ao contrato e a
automacao nao deve prosseguir ate nova qualificacao.

## Passo 4 - tres preflights, sem envio

Escopo exigido: ProcessonoSetor.asp, source_scope=sector_finalistic, marcador
6189, identidade processo/interessado exata, catalogo atual e seis campos
obrigatorios (genero continua opcional).

Para cada preflight, confirmar: preparacao reversivel, releitura pos-escrita e
igualdade de identidade, frame, geracao, campos e catalogo. Divergencia, frame
stale ou resultado incerto interrompe o fluxo.

Preenchimento e reversao supervisionados:

ATENCAO, verificado no codigo: qa_project_chrome_fill.py conecta em CDP
127.0.0.1:63097, mas o runner de qualificacao NAO expoe essa porta - ele usa
contexto persistente do Playwright. As duas ferramentas nao se conversam.

Para o preenchimento com esse driver, o navegador precisa ter sido aberto com
--remote-debugging-port. O caminho do projeto ja faz isso em
portable/Coletar-Processos-TCE.ps1, que escolhe uma porta livre e grava
DevToolsActivePort no perfil; o 63097 e a porta historica usada em sessoes
anteriores. Se a porta em uso for outra, ajuste o CDP_URL do driver ou abra a
mesma sessao pela rotina do projeto.

    python qa_project_chrome_fill.py --fill          # requer CDP ativo
    python qa_project_chrome_fill.py --restore-empty # idem

O gravador NAO substitui isso: ele recusa reversible_fill sem runner
supervisionado verificado, de proposito.

Pre-requisitos do driver de preenchimento (verificados no codigo):

- o painel da extensao precisa estar aberto como pagina
  (chrome-extension://<id>/sidepanel/panel.html);
- o processo alvo precisa estar na previa, com o botao Preencher campos
  disponiveis habilitado; o argumento --process (padrao 101440/2026) deve ser
  ajustado ao ato do preflight;
- os tres preflights formais (identidade, frame, geracao, campos e catalogo)
  vem do caminho de preflight da automacao; este driver fornece a evidencia de
  preenchimento reversivel de um ato.

O driver exige que o preenchimento NAO navegue e que nenhum campo seja enviado;
ele tambem recusa quando nenhum campo mudou.

## Passo 5 - parar antes do envio

Ao terminar, interrompa o runner com `Ctrl+C`, confira o caminho privado do
`recording.json` e encerre a ponte:

    .\INICIAR.cmd parar

O envio NAO e executado neste runbook. Ele exige:

1. os tres preflights verdes;
2. o observador de resultado (ja implementado no fonte; ausente no pacote atual,
   que abortaria em OUTCOME_OBSERVER_UNAVAILABLE);
3. autorizacao nova, imediata e especifica, ato a ato.

## Limites

- autoSubmit=false e real_send_enabled=false permanecem a fronteira.
- Nao usar Chrome pessoal nem perfil pessoal; use o perfil descartavel do runner
  ou um perfil dentro de dados-locais.
- Nao publicar cookies, tokens, HAR, trace ou PDFs.
- Nao tratar fixture, ZIP ou health check como prova de efeito remoto.

## Depois da sessao

1. Converter a observacao em fixture sanitizada, preservando a observacao
   original e gravando o derivado em `automacao/fixtures`:

       python real_portal_session.py ^
         --fixture-input "<pasta-privada>\observacao-1.json" ^
         --fixture-output "<pacote>\acervo-tce\automacao\fixtures\portal-real-1.json"

   O comando imprime um JSON com `output` e `sha256`. O hash corresponde aos
   bytes exatos do fixture gravado; ele e a entrada de `fixture_hashes`.
   Observacao sem autenticacao, com erro de navegacao, origem inesperada,
   contrato incompleto, deriva ou qualquer identidade de processo e recusada.
2. Gerar `automacao/qualificacao.json` com versoes, hashes da fixture e o id
   do evento real, usando `write_qualification()`.
3. So entao considerar o envio supervisionado de um unico ato.
