# Handoff — Professor IPERN: Área Restrita e lotes de 300

Data: 2026-09-14
Repositório: `C:\Users\slvma\Downloads\Github\Atos-TCE\work\tce-extractor`

## Estado atual

O fluxo autoritativo da planilha foi implementado no checkout. A opção 11 do
menu é `Analisar lista na Área Restrita e baixar em lotes de 300`; a opção 10
continua sendo o caminho técnico legado para uma fila congelada já existente.
O primeiro lote foi reconciliado e sua execução foi iniciada no Chrome isolado
do perfil portátil, com DevTools/CDP local na porta `9222`, após login humano.
O lote 1 foi concluído no Chrome isolado após a reconciliação exata de 300/300
chaves: 5.798 PDFs novos, 129 reutilizados, 0 processos com falha. Não houve
envio, complementação, tramitação ou finalização.

O arquivo fonte foi preservado. A importação real de
`Complementar Ato - Professor IPERN.xlsx` produziu:

- 1.317 linhas de entrada;
- 1.128 chaves únicas;
- 189 linhas duplicadas;
- SHA-256 `c958c5717261a5a2bc158f5b74ffe2a896d31664a6e79f6e61b84b4d8d9e08e2`;
- relatório derivado verificado com 1.317 linhas de resultado.

## Implementado

- importador portátil `.xlsx` em `portable/app/process_list.py`, com cabeçalhos
  obrigatórios, números inteiros positivos (incluindo inteiros serializados
  pelo Excel como `float`), ordem, duplicidades, SHA-256 e manifesto;
- relatório `Resultados`/`Resumo`, sem sobrescrever a planilha fonte;
- serviço loopback autenticado para importar lista, consultar lista ativa e
  gerar relatório;
- contrato de análise v3 com proveniência da lista e compatibilidade v2 apenas
  no fluxo legado;
- varredura completa do marcador selecionado, consulta exata número/ano dos
  ausentes, restauração do filtro original e pausas fail-closed;
- classificação exclusiva do controle vermelho semântico `Complementar Ato`;
  `Ato Complementado`, texto solto e ícones não equivalentes ficam fora;
- classificações explícitas `PRECISA_COMPLEMENTAR`, `ATO_COMPLEMENTADO`,
  `NAO_ENCONTRADO_AREA_RESTRITA`, `AMBIGUO` e `BLOQUEADO`;
- fila em lotes determinísticos de no máximo 300, na ordem da primeira
  ocorrência da planilha, com confirmação humana por lote no painel;
- reconciliação técnica da fila congelada no e-Contas antes da sincronização,
  checkpoint, deduplicação e limite de downloads existentes preservados;
- driver de paginação endurecido para aguardar tabela preenchida por até 30
  segundos, exigir página numérica correta e assinatura não vazia/nova; isso
  corrigiu o bloqueio falso que ocorria durante a recarga assíncrona entre
  páginas;
- downloader do lote ajustado para usar a requisição HTTP autenticada direta
  do coletor ao host da URL temporária (`novaarearestrita.tce.rn.gov.br`),
  evitando o `fetch` cross-origin que falhava no contexto do e-Contas;
- por solicitação do usuário, documentos cujo resumo normalizado é `Capa` são
  ignorados; outros eventos e documentos continuam elegíveis. Arquivos de capa
  eventualmente baixados antes dessa decisão não foram apagados.
- indisponibilidade transitória do endpoint `/api/Processo` passou a ter até
  quatro tentativas com backoff de 1/3/8 segundos, restritas a HTTP 502/503;
  códigos 400/401/403/429 continuam sem retry silencioso.
- fotografia vazia também passou a falhar imediatamente quando o e-Contas
  exibe `0 registros`, evitando espera artificial de até dez minutos e
  bloqueando uma análise baseada em resultado vazio.
- leitor PowerShell da fila congelada atualizado para aceitar schema v3, com
  teste regressivo específico;
- `autoSubmit=false` no fluxo de lista e nenhuma ação de preenchimento,
  complementação, finalização, tramitação ou envio;
- fases do painel: lista importada, analisando marcador, prévia congelada,
  aguardando confirmação, baixando e concluído;
- runtime de build com `openpyxl==3.1.5` e `et-xmlfile==2.0.0`, wheels
  SHA-256 fixadas, cópia de licenças e probe isolado; QA reproduzível em
  `requirements-qa.txt` com Playwright e PyMuPDF fixados.
- materializador browser-free `portable/app/materialize_area_analysis.py`,
  com teste TDD, para juntar a fotografia sanitizada completa ao manifesto da
  lista e regenerar uma análise v3 com todos os lotes.

## Arquivos relevantes

Produção: `portable/app/process_list.py`, `area_restrita_analysis.py`,
`batch_scope.py`, `analysis_preview.py`, `local_service.py`, `menu.ps1`,
`build-portable-runtime.ps1`, `portable/runtime-manifest.json`,
`portable/TESTAR-PACOTE.ps1`, `portable/TcePortable.Core.psm1` e
`portable/extensao-complementar-ato/{background,content,lib,sidepanel}`.

Testes: `test_process_list.py`, `test_area_restrita_analysis.py`,
`test_local_service.py`, `test_runtime_paths.py`,
`portable/extensao-complementar-ato/tests/` e os dois testes PowerShell em
`tests/`.

Documentação/dependências: `portable/README.md`, `portable/licenses/README.md`,
`QA-DEPENDENCIAS.md` e `requirements-qa.txt`.

A allowlist do repositório em `..\..\.gitignore` foi ajustada para preservar
esses arquivos de QA e os handoffs em `work/tce-extractor`.

## Validação executada

- `C:\Python314\python.exe -m unittest discover -p 'test*.py'`: 449 testes,
  449 aprovados, 8 skips, 0 falhas;
- `node --test` em `portable/extensao-complementar-ato`: 375 aprovados,
  0 falhas;
- `tests/Test-TcePortable.ps1`: 122 aprovados, 0 falhas;
- `tests/Test-TcePortable.ps1` após a correção do driver: 129 aprovados,
  0 falhas;
- `tests/Test-TcePortable.ps1` após a correção cross-origin do downloader: 130
  aprovados, 0 falhas;
- `tests/Test-TcePortable.ps1` após a regra de ignorar capas: 132 aprovados,
  0 falhas;
- `tests/Test-TcePortable.ps1` após o retry limitado para 502/503: 134
  aprovados, 0 falhas;
- `tests/Test-TcePortable.ps1` após a guarda de resultado vazio: 136
  aprovados, 0 falhas;
- `tests/Test-PortableMenu.ps1`: 91 aprovados, 0 falhas;
- importação/relatório da planilha fonte: 1.317 linhas verificadas;
- `git diff --check`: verde.
- suíte focada após a correção de QA (`test_process_list`,
  `test_area_restrita_analysis`, `test_local_service`, `test_runtime_paths`):
  53 testes, 52 aprovados, 1 skip esperado, 0 falhas;
- probe do Python de QA: `openpyxl=3.1.5`, `et_xmlfile=2.0.0`,
  `pymupdf=1.28.2`, `playwright=1.58.0`;
- varredura live da Área Restrita: marcador observado
  `PROFESSOR - IPERN (1227)`, 1.227 chaves, 726 `PRECISA_COMPLEMENTAR`,
  501 `ATO_COMPLEMENTADO`, 0 ambíguas; paginação restaurada para `1 - 30`;
- reconciliação live do e-Contas: 1.227 chaves únicas em 13 páginas, marcador
  `PROFESSOR - IPERN`, setor `[CBP]`, lote 1 com 300/300 chaves presentes,
  sem duplicidade, ausência ou ambiguidade;
- fila local preparada e validada em
  `acervo-tce/automacao/analises/analysis-0e2f3c9e075f3c3c4db23608.json`, com
  300 itens, `lot-1`, SHA-256
  `0e2f3c9e075f3c3c4db2360831790e0ee5b045c306589aabcd1dcb10f9506923`;
- teste PowerShell após a correção schema v3: 123 aprovados, 0 falhas;
- verificação inicial do coletor contra o Chrome CUA: não encontrou porta
  (`port=NONE`); por isso foi aberto, com autorização do usuário, o perfil
  portátil isolado em `portable/dados-locais/perfil-navegador`, com DevTools
  confirmado na porta `9222`; o usuário concluiu o login manualmente;
- reprodução live do bug de paginação: a tabela ficava vazia por mais de 10
  segundos após alguns cliques, embora o marcador já tivesse mudado; a janela
  foi ampliada para 30 segundos e a reprodução passou a enumerar 1.227/1.227;
- execução do lote 1 iniciada com a fila congelada: ordem do portal 1.227,
  fila validada 300/300, sem download iniciado antes da reconciliação; no
  último checkpoint observado chegou a `[17/300]`; a tentativa foi
  interrompida para corrigir o downloader e não gravou PDFs;
- probe live do endpoint de documento: `/api/informacao/2032884/pdf` retornou
  200 e uma URL temporária; GET autenticado direto nessa URL retornou
  `200 application/pdf` com 2.338.007 bytes, confirmando que a falha anterior
  era CORS da origem, não ausência do documento.
- duas tentativas do lote foram pausadas para corrigir a origem do download e
  a regra de capas; a segunda chegou a 6/300 e acumulou 18 PDFs antes da
  pausa. A próxima retomada usa a mesma fila/checkpoint e não deve rebaixar
  capas.
- uma execução completa com a rede elevada reconciliou 1.227 processos e
  percorreu 300/300 da fila; concluiu 101 downloads novos, 28 reutilizações e
  291 falhas de HTTP 502 posteriores do endpoint de processo. O acervo contém
  os PDFs já obtidos e os erros estão preservados para retomada; nenhum ato foi
  enviado.
- uma retomada posterior encontrou o e-Contas autenticado, mas com o filtro
  exibindo `Nenhum Processo Encontrado` e `0 registros`; foi interrompida antes
  de persistir nova ordem ou baixar qualquer documento.
- depois de uma recarga controlada, os marcadores não chegaram a carregar e a
  aplicação recusou `PROFESSOR - IPERN` como marcador inexistente; a tentativa
  foi encerrada antes de nova ordem/download. O acervo parcial ficou com 16
  processos materializados, 135 PDFs e 123.639.551 bytes.

O `TESTAR-PACOTE.ps1` ainda não pode aprovar este checkout porque o diretório
`portable/runtime` não está materializado no repositório; o builder é o caminho
de geração do runtime. A validação de QA usa o Python 3.14 do ambiente com as
dependências fixadas, não um runtime embutido incompleto.

## Git e isolamento

O checkout está na branch `main`, com alterações locais anteriores a este
handoff preservadas. A criação do worktree/branch isolado foi tentada e recusada
porque `.git/refs` está somente leitura (`unable to create directory ...`). O
trabalho permanece no checkout atual. Os commits `5d50a75`, `b38a61c` e
`65f320e` foram criados e enviados com sucesso para `origin/main`; o último
contém a compatibilidade schema v3 do coletor, o reconhecimento de `atov.png`
e este estado live do lote 1.

## Atualização de continuidade — marcador recarregado e lote 1 concluído

O usuário confirmou que o marcador voltou a estar carregado. A retomada do
mesmo `analysis-0e2f3c9e...json`, lote 1, foi iniciada em 14/09/2026 no Chrome
isolado autenticado, com nova enumeração/reconciliação de 1.227 processos e
300/300 chaves válidas. Até a última atualização desta nota, a execução havia
alcançado 100/300 itens, reaproveitando PDFs existentes e baixando novos
documentos; um erro HTTP 400 de documento individual ficou isolado no registro
de falhas. O coletor segue sem OCR nesta etapa porque nenhum runtime de OCR foi
passado ao comando; a preparação local será executada depois da aquisição.

O marcador voltou a estar carregado, a fotografia completa permanece disponível
na sessão CUA e foi preservada localmente como evidência sanitizada. A análise
v3 antiga `analysis-0e2f3c9e075f3c3c4db23608.json` foi identificada como
incompleta para retomada: contém apenas 1 linha e 1 lote de 300. Ela não deve
ser usada para iniciar o lote 2. O materializador acima deve gerar uma nova
análise a partir do manifesto `input-c958c5717261a5a2bc158f5b.json` e da
fotografia completa; a expectativa da varredura já observada é fila de 724
elegíveis, lotes `300/300/124`, com as demais chaves bloqueadas por
complementação concluída ou ausência explícita.

O lote 1 foi encerrado com 5.798 downloads novos, 129 arquivos reutilizados e
0 processos com falha. O acervo local passou a conter 300 diretórios de
processos e 5.933 PDFs; o checkpoint permanece em
`acervo-tce/checkpoint.json`. A tentativa de lote 2 com a análise antiga falhou
seguramente antes de qualquer download, com `Lote inexistente: 2`.

## Atualização live — lote 2 concluído

Depois de materializar a análise v3 completa
`acervo-tce/automacao/analises/analysis-08b6d6b32c5870043e81a9cc.json`, o lote
2 foi reconciliado no escopo `sector_finalistic`/setor `CBP` do e-Contas e
executado no Chrome autenticado em 14/09/2026. Foram concluídos 300/300
processos, com 5.785 documentos baixados, 0 reutilizados, 0 duplicados e 0
processos com falha. A contagem física conferida após o lote é 600 diretórios,
11.718 PDFs e 7.597.598.148 bytes. O checkpoint foi atualizado pelo coletor.

O aviso repetido de preparação incremental sem runtime não interrompeu a
coleta; OCR/HTML/JSON da extensão continuam como etapa posterior sobre o
acervo completo. O lote 3, com as 124 chaves restantes da mesma fila congelada,
é o próximo passo e pode ser retomado com o comando registrado abaixo.

## Atualização live — aquisição integral concluída

O lote 3 foi reconciliado e concluído no mesmo Chrome autenticado em
14/09/2026: 124/124 processos, 2.461 documentos baixados, 0 reutilizados,
0 duplicados e 0 processos com falha. Somados aos lotes anteriores, a fila
congelada de 724 elegíveis foi totalmente processada. A conferência física
imediata encontrou 724 diretórios de processos, 14.179 PDFs e
8.892.090.055 bytes em `acervo-tce/processos`; o Excel fonte continua
preservado.

O próximo estágio é local: indexação, OCR somente onde necessário,
extração/HTML, exportação do JSON da extensão, relatório reconciliado e
empacotamento. A preparação incremental emitida pelo coletor não foi executada
durante a coleta por ausência de runtime explícito; o Tesseract instalado no
host foi localizado para a preparação posterior.

Também foi corrigida a configuração do tamanho de lote no painel: listas
autoritativas mantêm 300 como padrão, mas agora respeitam a escolha 50, 100,
200 ou 300, sempre com teto de 300 e confirmação humana por lote. O teste RED
foi reproduzido antes da alteração e a suíte do painel ficou verde depois.

## Pendências e retomada

1. Executar indexação/OCR/extrator local e conferir os artefatos derivados.
   A autorização do usuário permite seguir sem pausa humana entre os lotes,
   mas continuam obrigatórias as travas de escopo, sessão e reconciliação.
2. Executar o builder em staging reservado para materializar o runtime e rodar
   `portable/TESTAR-PACOTE.ps1` contra o pacote gerado; conferir manifest,
   hashes, CRC/extração limpa e allowlist.
3. Fazer o piloto supervisionado nos Chrome já autenticados: uma linha vermelha,
   uma complementada e uma ausente; depois um lote pequeno de qualificação.
4. Somente com o piloto verde, analisar as 1.128 chaves e apresentar a prévia.
5. Confirmar cada lote produtivo de até 300 individualmente; interromper se a
   reconciliação exata do e-Contas encontrar ausência ou ambiguidade.
6. Montar o ZIP portátil final, preservando a planilha original e incluindo
   scripts, runtime/dependências licenciadas, configuração de lotes 50/100/200/
   300 ou outro tamanho, OCR opcional, gerador JSON da extensão, gerador HTML
   com links relativos aos PDFs, manifests, README e handoff; validar a
   extração limpa antes de entregar.
7. Para futuras alterações, verificar `git status`, adicionar somente os
   arquivos da mudança com `git add --`, fazer commit nominal e `git push`.

Para continuar, não recrie uma fila parcial nem inicie um segundo coletor
concorrente: materialize a nova análise a partir da fotografia completa,
valide seus lotes e use o mesmo arquivo para os lotes 2 e 3. A Área Restrita e
o e-Contas devem permanecer autenticados por login humano; não automatizar
credenciais nem submissão. Capas continuam ignoradas para novas sincronizações;
capas que já existam não são apagadas.

## Encerramento live — aquisição, preparação e pacote entregável

Em 15/09/2026, a fila congelada v3 foi concluída sem submissão nos portais:
724/724 processos elegíveis, distribuídos em 300/300/124, com 0 falhas de
processo. A aquisição somou 5.798 downloads novos + 129 reutilizados no lote 1,
5.785 no lote 2 e 2.461 no lote 3. O acervo final conferido contém 724
diretórios, 14.179 PDFs e 8.892.090.055 bytes em
`acervo-tce/processos`; o arquivo Excel original não foi alterado.

Foi executada a preparação local com Tesseract 5.4.0.20240606 e PyMuPDF
1.28.2. Foram gerados `indice-local.json`, `indice-classificado.json`,
`checkpoint-extracao.json`, `pdfs-alvo-manifest.json`, `doc.md`,
`complementar-ato.html`, `dados-complementar-ato.json`,
`evidencias-visuais.json` e `fundamentos-contexto.v1.json`. A planilha
reconciliada está em
`acervo-tce/automacao/relatorios/area-restrita-input-c958c5717261a5a2bc158f5b74ffe2a896d31664a6e79f6e61b84b4d8d9e08e2.xlsx`;
ela contém as 1.317 linhas da fonte e o resumo 1.128/189/724/212/192/0/0/3.

O runtime portátil foi materializado em staging com 430 arquivos, 0 hashes
divergentes, licenças para Python/PyMuPDF/openpyxl/et_xmlfile/Tesseract e
idiomas `por`, `eng` e `osd`. O ZIP privado final foi criado fora do checkout:
`C:\Users\slvma\Downloads\Github\Atos-TCE\work\Atos-TCE-Professor-IPERN-completo-2026-09-14.zip`.
O empacotador reportou 32.979 arquivos, 724 processos, 17.619 eventos,
14.179 PDFs, 739 registros da extensão, `crc_ok=true` e o SHA-256
`8fba5c6f7e58fcd4cc064ebaf732b4fb5249eeff2631bfb082e0f98b5474eedb`.

O auditor privado passou com `ok=true` e 0 findings depois que `.xlsx` e
`.sqlite3` foram incluídos como binários permitidos e o `.part` incompleto foi
excluído somente do staging. O arquivo parcial correspondente na fonte não foi
apagado. O staging intermediário pode ser removido após a validação do ZIP;
isso não afeta o acervo em `acervo-tce` nem o ZIP final.

O Git ainda precisa de commit/push para as alterações desta sessão: houve
falha anterior de permissão em `.git/index.lock` e de conexão com GitHub. Antes
de integrar, revisar `git status`, adicionar somente os arquivos de código,
testes e handoff, e então fazer commit nominal e push.

## Validação final da sessão

O dataset da extensão passou `extension_exporter.py --validate`; o ZIP final
foi inspecionado por lista de membros e contém a extensão (21 arquivos), a
planilha original, a análise v3, o receptor local e o materializador. A suíte
focada final executou 85 testes, com 83 aprovados, 2 skips e 0 falhas; a suíte
Node do painel executou 48/48; `git diff --check` passou. O ZIP reportou
`crc_ok=true` e SHA-256
`7db7eb4bff96898b95650aa72e3a399fad59e90a8f9093fee93d13a561c5c355`.

Os diretórios `staging-final` e `staging-verified` foram removidos após a
validação para liberar espaço; nenhum arquivo em `acervo-tce` foi removido.
O receptor loopback foi encerrado. Para retomar o acervo, abra o ZIP ou use
diretamente `acervo-tce`; não é necessário repetir a coleta dos lotes 1–3.

## Documento filtrado — processos ausentes

Em 15/09/2026 foi criado o workbook
`outputs/01a0a10f-5286-7cb0-95d1-d78b57c226af/processos-nao-encontrados-area-restrita-192.xlsx`.
Ele contém exatamente 192 processos únicos classificados como
`NAO_ENCONTRADO_AREA_RESTRITA`, preservando a ordem da primeira ocorrência na
planilha. Cada linha registra número/ano, linha original, linhas duplicadas,
classificação, marcador observado, estado do e-Contas, OCR e hash da
fotografia. O resumo registra 381 linhas de origem, 189 duplicidades e zero
downloads para esse subconjunto; a fonte original não foi alterada.

Validação do workbook: 192 linhas de detalhe, 192 chaves únicas, 192
classificações ausentes, zero downloads e zero erros de fórmula. A prévia
visual da aba única foi conferida antes da limpeza dos arquivos auxiliares.
