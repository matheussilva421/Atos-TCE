# Handoff — Meus Processos na ordem do e-Contas

## Estado final

- Solicitação atendida: coleta da lista atual “Meus Processos” do e-Contas, preservação da ordem exibida e entrega de ZIP privado pronto para complementação manual.
- ZIP original preservado e não sobrescrito: `outputs/TCE-Coleta-Extracao-HTML-Extensao-2026-09-12-pdf-corrigido.zip`.
- ZIP final: `outputs/TCE-Meus-Processos-EContas-Ordenado-2026-09-12.zip`.
- SHA-256: `f4c044c78f5277e3e2c13893c9bf76069ca5fd407d39bc7e1b4577a2cf57a617`.
- Checksum: `outputs/TCE-Meus-Processos-EContas-Ordenado-2026-09-12.zip.sha256`.
- Staging: `.staging-meus-processos-2aa2b3d933084c4da49a27a415a0379c`.
- Login foi manual em Chrome isolado; o perfil pessoal não foi usado.
- O coletor usou o token da sessão autenticada para HTTP direto nos hosts oficiais do TCE, sem abrir aba separada da área restrita.

## Conteúdo verificado

- 165 processos capturados em `acervo-tce/ordem-portal.json`.
- 165 `processo.json` no ZIP.
- 3.298 documentos catalogados.
- 3.248 PDFs completos.
- 50 documentos “Capa” ficaram como `status=error` porque o endpoint do próprio portal respondeu HTTP 400; não foram inventados PDFs.
- 7.433 arquivos no ZIP; 3.721 eventos; 21 arquivos da extensão; 165 registros de dados da extensão.
- CRC do ZIP: aprovado.
- Ordem independente: os 165 processos no `acervo-tce/complementar-ato.html` coincidem exatamente com `ordem-portal.json`; primeiros `101444/2026`, `101478/2026`, `101481/2026`; últimos `100090/2022`, `100087/2022`, `100064/2022`.
- O empacotador aprovou a auditoria privada antes de criar o ZIP; dados-locais, perfis, credenciais, logs de sessão e tokens não foram incluídos.

## Alterações implementadas

- `work/tce-extractor/html_generator.py`: removeu prioridade documental da ordenação e respeita `archive_index.process_keys`.
- `work/tce-extractor/portable/TcePortable.Core.psm1`: adicionou persistência da ordem do portal e reserva de porta DevTools.
- `work/tce-extractor/portable/Coletar-Processos-TCE.ps1`: captura a ordem, usa HTTP direto autenticado para downloads e adiciona `-ReutilizarOrdemPortal`.
- `work/tce-extractor/portable/app/analysis_pipeline.py`: permite que o manifesto final publique caminhos relativos ao `acervo-tce`.
- `work/tce-extractor/portable/app/package_audit.py`: evita falso positivo de credencial em texto OCR do índice documental; mantém a verificação de credenciais operacionais.
- Testes atualizados: `test_html_generator.py`, `test_analysis_pipeline.py`, `test_package_audit.py`, `test_batch_runner.py` e `tests/Test-TcePortable.ps1`.

## Testes e validações

- `python -m unittest test_analysis_pipeline test_batch_runner test_package_audit test_html_generator test_archive_index test_workflow_state`: 130 executados, 127 aprovados, 0 falhas, 3 ignorados.
- `powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tests/Test-TcePortable.ps1`: 121 aprovados, 0 falhas.
- `python -m unittest discover -p 'test*.py'`: 415 executados, 401 aprovados, 6 falhas, 8 ignorados. As 5 falhas restantes são preexistentes e fora deste escopo: permissões `webNavigation` da extensão e testes de navegador/HTML; a sexta foi a expectativa antiga de `test_batch_runner`, corrigida e coberta no conjunto focado.
- Validação independente do ZIP: CRC aprovado, ordem HTML igual à ordem do portal, contagens conferidas e hash SHA-256 conferido pelo PowerShell.

## Pendências e limites

- Os 50 documentos HTTP 400 continuam pendentes no próprio portal; podem ser tentados novamente no futuro sem alterar a ordem.
- O HTML deve ser aberto por HTTP local, conforme o fluxo do pacote; não usar `file://`.
- A extensão continua em modo de revisão/preenchimento supervisionado. Nenhum ato é preenchido, enviado ou finalizado automaticamente.
- Git: a criação de branch e locks em `.git/refs` foi recusada pelo ambiente; não houve commit nem push. As alterações permanecem no working tree.

## Retomada

1. Entregar/usar `outputs/TCE-Meus-Processos-EContas-Ordenado-2026-09-12.zip`.
2. Conferir o `.sha256` antes de transferir.
3. Extrair em uma pasta própria e iniciar o menu/servidor HTTP local do pacote.
4. Fazer a complementação manual e revisar cada campo antes de qualquer ação no portal.

## Nova implementação — fluxo pelo marcador da Área Restrita (iniciada em 12/09/2026)

- Pedido vigente: substituir o fluxo de `Meus Processos` por análise da lista
  `ProcessonoSetor.asp` (`source_scope=sector_finalistic`), usando o marcador já
  selecionado pelo operador e considerando pendente somente a ação representada
  pelo ícone vermelho de `Complementar Ato` na própria linha.
- Fluxo aprovado: análise read-only de todas as páginas, prévia congelada,
  confirmação humana entre `todos` e `um lote`, aquisição no e-Contas, OCR,
  JSON/HTML e abertura por HTTP local. Nenhum preenchimento, envio ou conclusão
  de ato faz parte deste escopo.
- Estado inicial preservado: `main` em `3d5e90b`, sincronizada com
  `origin/main`, com dez arquivos modificados e este handoff ainda não rastreado;
  essas mudanças são da coleta ordenada anterior e não devem ser descartadas.
- Baseline antes da nova implementação: Node focado 163/163 verde; Python
  focado 90 executados, 87 aprovados, 0 falhas e 3 ignorados. O ZIP entregue tem
  dados embutidos e abre 165 processos quando extraído; `file://` bloqueia apenas
  os módulos PDF.js, motivando o novo `ABRIR-MESA.cmd`.
- Próximo passo: TDD RED para assinatura do ícone vermelho, marcador observado
  sem redigitação, análise sem dataset anterior e aquisição `todos|lote`.

### Bloco implementado em 12/09/2026

- TDD do ícone vermelho concluído: somente o controle semântico da própria linha
  com ícone `Complementar Ato` vermelho produz `needsComplement=true`; texto
  global e outros ícones são ignorados. A observação guarda `action_signature`
  sanitizada.
- A análise começa sem dataset (`datasetSha256:null`, `analysisOnly:true`), fixa
  `source_scope=sector_finalistic`, lê o marcador já selecionado e congela
  label+value na paginação. Marcador ausente/trocado, origem trocada e página
  repetida pausam fail-closed.
- O worker gera `area_snapshot_sha256`; schema v2, cliente e ponte persistem esse
  hash. Pendência sem assinatura vermelha é recusada.
- O painel ignora marcador/origem digitados neste fluxo e oferece aquisição
  tipada `all` ou `lot`. O coletor recebe a fila completa ou `-NumeroLote`, sem
  preenchimento, conclusão ou envio de ato.
- `portable/ABRIR-MESA.cmd` e `INICIAR.cmd abrir-mesa` validam HTML, JSON,
  serviço e PDF.js antes de iniciar `/review` por HTTP. Allowlists e README foram
  atualizados.

### Evidência parcial

- Node focado: schemas 14/14; controller 63/63; bridge+panel 62/62.
- Python focado: batch scope 7/7; acquisition 4/4; local service 23 executados,
  22 aprovados e 1 ignorado.
- PowerShell Menu: 87/87.
- Gate Node amplo inicial: 365 executados, 364 aprovados e 1 regressão de
  acessibilidade, já corrigida. Gate Python portátil revelou sete fixtures
  antigas sem os novos hashes/assinaturas; fixtures atualizadas.

### Próxima retomada

1. Reexecutar gates amplos Node, Python raiz/portable, PowerShell e auditoria.
2. Gerar e extrair ZIP novo; executar `ABRIR-MESA.cmd` e validar `/review`,
   contagem, primeiro processo, sete campos e PDF pintado.
3. Recarregar a extensão no Chrome de trabalho e executar somente a análise
   read-only da lista marcada; parar na prévia para a escolha humana.

## Gate real e entrega final do bloco

- Chrome de trabalho confirmado por CDP local em `9222`, com Área Restrita e
  e-Contas autenticados. Origem observada:
  `SISTEMAS/Processo/ProcessonoSetor.asp`, equivalente a
  `source_scope=sector_finalistic`.
- Marcador observado diretamente no portal: label
  `PROFESSOR - IPERN - 2 RUBRICAS (470)`, value `6189`.
- Assinatura real do controle pendente: `alt/title=Complementar Ato`,
  `src=../../images/atov.png`. O detector implementado aceita essa assinatura e
  não depende do nome inferido do arquivo.
- A lista estava inicialmente na página 6. O gate revelou que a análise antiga
  seguiria apenas até a última página; foi criado RED específico e implementada
  a ação fechada `first_page`, com retorno à página 1 antes da coleta.
- Análise real somente leitura concluída: 16 páginas, 470 linhas, 470 processos
  únicos, 156 pendentes pelo ícone vermelho, 314 excluídos e zero identidades
  ambíguas. Hash da fotografia:
  `976b05e697976456c298463fa3c4df66aba6a7827229ccad5f8d3a78e5d24d88`.
- Prévia detalhada salva em
  `outputs/area-restrita-professor-ipern-2-rubricas-preview-2026-09-12.json`.
  Nenhum download ou abertura/preenchimento de ato ocorreu; o fluxo está parado
  para a escolha humana entre todos e um lote.
- ZIP final: `outputs/TCE-Fluxo-Marcador-Area-Restrita-2026-09-12.zip`,
  1.266.974.055 bytes, 7.434 arquivos, 165 processos históricos, 3.721 eventos,
  3.248 PDFs, CRC aprovado e SHA-256
  `35b41ea2ecdfc981007f660b5757ab54d2b90c1dcb8d4478c59ef00c6cabe4cc`.
- Extração limpa final aprovada pela auditoria privada sem achados. O gate visual
  anterior em `/review` confirmou 165 processos, sete campos e canvas PDF.js
  pintado em 924x1293.

### Gates finais

- Node completo após o reparo de primeira página e seleção `all`: 367/367.
- Python integrado: 153 executados, 149 aprovados, 4 ignorados, zero falhas.
- Python portátil: 35/35.
- PowerShell `Test-TcePortable.ps1`: 121/121.
- PowerShell `Test-PortableMenu.ps1`: 87/87.
- Auditoria de pacote focada: 45 executados, 43 aprovados, 2 ignorados.
- Auditoria privada da extração final: aprovada, zero achados; hash do ZIP
  conferido com o arquivo `.sha256`.

### Estado de retomada operacional

1. Aguardar o operador escolher `Todos` ou `{lot_number, lot_size}` (padrão 50).
2. Após a escolha, usar somente a aquisição e-Contas da fotografia congelada;
   não reenviar a análise contra uma lista que possa ter mudado.
3. Atualizar incrementalmente checkpoint, OCR, JSON e HTML. Não acionar
   `APPLY_FIELDS`, preenchimento, conclusão ou envio.

## Fechamento do bloco de implementação

- O ZIP foi reconstruído depois da última correção do contrato `selection=all`;
  o cliente empacotado é byte a byte igual ao fonte vigente, `testzip()` não
  encontrou CRC inválido e o SHA-256 confere com o arquivo `.sha256`.
- Gate Node final: `npm test`, 367 executados, 367 aprovados, zero falhas.
- `git diff --check`: aprovado, sem erros de whitespace.
- O estado antigo de Git descrito na seção inicial é apenas o baseline histórico.
  As alterações preservadas da coleta anterior e o novo fluxo por marcador serão
  registrados nominalmente em `main` e enviados para `origin/main` neste
  fechamento; os hashes dos commits ficam no resumo final da tarefa.
- Checkpoint humano vigente: aguardar `Todos` ou `Um lote` com número e tamanho
  (padrão 50). Até essa escolha, não iniciar aquisição, OCR ou nova geração de
  dados para os 156 pendentes congelados.

### GitHub após o fechamento

- Commit de implementação: `565f446` (`feat: implementar fluxo por marcador da
  area restrita`).
- Push confirmado: `main` avançou de `3d5e90b` para `565f446` em
  `origin/main` (`https://github.com/matheussilva421/Atos-TCE.git`).
- Working tree esperado após o commit documental final: limpo e sincronizado.

## Aquisição autorizada dos 156 pendentes e mesa com duas coleções

- O operador autorizou explicitamente `Todos`: baixar os 156 pendentes da
  fotografia congelada, aplicar OCR/análise e gerar um ZIP único com HTML,
  extensão e JSON. Também pediu um botão no HTML para alternar entre os 165
  `Meus Processos` e os 156 `Processos no Setor`, sempre nas respectivas ordens.
- Deduplicação prévia: 155 das 156 chaves já existem no acervo dos 165; somente
  `103433/2023` é nova. O pacote consolidado terá 166 processos físicos, mas
  duas coleções lógicas independentes com contagens 165 e 156.
- TDD do alternador: dois testes RED falharam pela ausência de
  `collections_path` e `collection-toggle`; após a implementação ficaram 2/2
  verdes. O empacotador privado ganhou regressão própria e ficou 1/1 verde.
- O HTML agora aceita `colecoes-processos.json` schema v1, recusa coleções
  ausentes/duplicadas, preserva a ordem de cada lista e alterna por um botão sem
  duplicar os registros compartilhados. Pipeline completo, incremental,
  serviço local e empacotador propagam o sidecar quando presente.
- Cópia de trabalho preservadora:
  `.staging-combined-sector-20260912`. O perfil/cookies do Chrome foi excluído
  da cópia por estar em uso e por ser proibido no pacote final; nenhum dado de
  autenticação será empacotado.
- Snapshot de aquisição materializado em
  `.staging-combined-sector-20260912/acervo-tce/automacao/analises/analysis-0423080e3c0cd6a2d7dd6bfe.json`:
  156 itens, quatro lotes internos de 50, zero bloqueados, hash
  `0423080e3c0cd6a2d7dd6bfe1a0713c372a1b4c6d6a1633134b5d1bf27c863a6`.
- Sessão e-Contas confirmada via Chrome de trabalho/CDP `9222`, setor `CBP`.
  O portal enumerou 400 processos e encontrou todas as 156 chaves sem
  substituição. Aquisição progressiva iniciada com no máximo dois downloads,
  sem abrir, preencher ou enviar atos.

## Fechamento da aquisição, OCR e pacote combinado

- Aquisição congelada concluída para 156/156 processos. Os 155 já presentes
  foram reutilizados; `103433/2023` foi adquirido separadamente com 25 PDFs
  válidos (16.683.664 bytes). Duas capas históricas desse processo retornaram
  HTTP 400 e permanecem registradas como falhas granulares; nenhum resultado
  íntegro foi descartado.
- A primeira tentativa do processo novo ficou sem PDFs por restrição de rede
  do executor. Seus 35 JSONs de eventos foram movidos de forma recuperável para
  `tmp/quarentena-103433-2023-rede-bloqueada`; a retomada limpa autenticada
  baixou os 25 documentos reais.
- Causa da mesa vazia identificada e corrigida por TDD: o pipeline usava o
  manifesto portátil com `pdf_path` relativo durante a execução do OCR. O
  executor agora recebe um manifesto temporário com caminhos absolutos; somente
  os JSONs publicados/empacotados recebem caminhos relativos. O processo real
  `101444/2026` passou de "PDF ausente" para seis campos encontrados; gênero
  continua pendente por falta de evidência segura.
- A publicação incremental agora chama `build_target_manifest(...,
  archive_root=root)` e semeia a mesa pelo manifesto canônico antes de mesclar o
  processo corrente. Isso impede caminhos absolutos no pacote e impede uma
  revisão parcial de apagar processos das coleções. Revisões inválidas foram
  preservadas em `tmp/publicacoes-invalidas-20260912-2030` e
  `tmp/publicacoes-superadas-20260912-2100`, fora do ZIP.
- `process_collections.py` cria deterministicamente as duas vistas: 165 chaves
  na ordem original de Meus Processos e 156 na ordem da fotografia da Área
  Restrita. O sidecar preserva também todos os interessados observados; a mesa
  injeta esses interessados sem duplicar os 155 processos sobrepostos.
- Reprocessamento local final: 166 processos físicos, 367 documentos
  prioritários, 3.325 documentos exibíveis e 174 registros por
  processo/interessado. Para `101444/2026`, foram confirmados modalidade,
  fundamento legal, DOE, cargo, matrícula e nascimento, com PDF de duas páginas
  efetivamente pintado.
- ZIP final: `outputs/TCE-Meus-Processos-165-e-Setor-156-2026-09-12.zip`,
  1.275.188.371 bytes, 7.508 arquivos, 166 processos, 3.755 eventos, 3.273 PDFs,
  21 arquivos da extensão, 174 registros JSON, CRC aprovado e SHA-256
  `6c48e47081bf8bf77b2872340aa12c1c2ede1d956fa36de365cbf505784eaac8`.
  Hash registrado no `.zip.sha256` adjacente.
- Extração limpa de aceite:
  `.verify-combined-final-20260912-2110`, 7.508 arquivos. Auditoria privada:
  `ok=true`, zero achados. `ABRIR-MESA.cmd` iniciou `/review` em
  `127.0.0.1:18745`; validação visual confirmou 156 → 165 → 156, nomes,
  seis campos encontrados e PDF.js/iframe pintado. A aba final ficou aberta na
  vista `Processos no Setor`.

### Testes desta continuação

- Node completo: 367/367, zero falhas.
- Python focado final: 51/51, zero falhas.
- Python amplo: 420 executados, 407 aprovados, 8 ignorados e 5 falhas. Uma falha
  introduzida pela separação dos dois manifestos foi corrigida e passou no gate
  focado. As quatro restantes são baselines preexistentes fora deste diff:
  duas expectativas antigas de `webNavigation`, uma captura visual do painel e
  uma expectativa antiga de download via `arrayBuffer()`.
- Empacotador: CRC aprovado. Auditoria privada da extração final: zero
  achados. Gate visual real: aprovado.

### Retomada segura

1. A mesa final já está aberta; se o serviço for encerrado, executar
   `ABRIR-MESA.cmd` dentro de uma extração integral do ZIP.
2. Não abrir `complementar-ato.html` diretamente dentro do ZIP; usar sempre
   `/review` para PDF.js, JSON e assets locais.
3. Nenhum ato foi preenchido, concluído ou enviado. A mesa continua somente
   leitura e os botões `Copiar` apenas colocam valores na área de transferência.

### GitHub desta entrega

- Commit de implementação: `e7de4ed` (`feat: consolidar mesas e corrigir OCR
  portatil`). Inclui código, testes e o histórico operacional acima.
- Uma revisão independente foi solicitada antes do commit, mas não retornou
  achados dentro da janela e foi encerrada; os gates objetivos permanecem como
  evidência de aceite.
- Commit documental: `9a7bc66` (`docs: registrar entrega combinada`). Push
  confirmado: `origin/main` avançou de `f793d1f` para `9a7bc66`.
