# Handoff — Professor IPERN: Área Restrita e lotes de 300

Data: 2026-09-14
Repositório: `C:\Users\slvma\Downloads\Github\Atos-TCE\work\tce-extractor`

## Estado atual

O fluxo autoritativo da planilha foi implementado no checkout. A opção 11 do
menu é `Analisar lista na Área Restrita e baixar em lotes de 300`; a opção 10
continua sendo o caminho técnico legado para uma fila congelada já existente.
O primeiro lote foi reconciliado e sua execução foi iniciada no Chrome isolado
do perfil portátil, com DevTools/CDP local na porta `9222`, após login humano.
Até o último checkpoint observado, os primeiros processos produziram
metadados/eventos, mas nenhum PDF efetivamente baixado; não houve envio,
complementação, tramitação ou finalização.

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

## Atualização de continuidade — marcador recarregado

O usuário confirmou que o marcador voltou a estar carregado. A retomada do
mesmo `analysis-0e2f3c9e...json`, lote 1, foi iniciada em 14/09/2026 no Chrome
isolado autenticado, com nova enumeração/reconciliação de 1.227 processos e
300/300 chaves válidas. Até a última atualização desta nota, a execução havia
alcançado 100/300 itens, reaproveitando PDFs existentes e baixando novos
documentos; um erro HTTP 400 de documento individual ficou isolado no registro
de falhas. O coletor segue sem OCR nesta etapa porque nenhum runtime de OCR foi
passado ao comando; a preparação local será executada depois da aquisição.

Também foi corrigida a configuração do tamanho de lote no painel: listas
autoritativas mantêm 300 como padrão, mas agora respeitam a escolha 50, 100,
200 ou 300, sempre com teto de 300 e confirmação humana por lote. O teste RED
foi reproduzido antes da alteração e a suíte do painel ficou verde depois.

## Pendências e retomada

1. Aguardar/revalidar o serviço do e-Contas até os marcadores carregarem e
   `PROFESSOR - IPERN` voltar a produzir uma fotografia não vazia; somente
   então retomar a fila do lote 1 e acompanhar os retries 502/503 até o
   término ou pausa fail-closed; conferir checkpoint, PDFs, eventos, erros e
   relatório reconciliado.
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

Para continuar, não recrie a fila nem inicie um segundo coletor concorrente:
consulte o processo atual, valide o checkpoint e retome com o mesmo arquivo
`analysis-0e2f3c9e...json` somente após o término/pausa. A Área Restrita e o
e-Contas devem permanecer autenticados por login humano; não automatizar
credenciais nem submissão. Restaurar o clipboard CUA e a paginação do e-Contas
já foi feito.
