# Handoff — Professor IPERN: Área Restrita e lotes de 300

Data: 2026-09-14
Repositório: `C:\Users\slvma\Downloads\Github\Atos-TCE\work\tce-extractor`

## Estado atual

O fluxo autoritativo da planilha foi implementado no checkout. A opção 11 do
menu é `Analisar lista na Área Restrita e baixar em lotes de 300`; a opção 10
continua sendo o caminho técnico legado para uma fila congelada já existente.
Nenhum download ou envio foi iniciado nesta sessão. O primeiro lote foi
reconciliado, mas permaneceu pendente de execução porque o Chrome controlado
pela sessão não expõe uma porta DevTools/CDP local reutilizável.

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
- verificação do coletor contra o ambiente live: `Get-TceExistingPortalDevToolsPort`
  não encontrou porta (`port=NONE`); o perfil portátil também ainda não
  existe/autenticado. Portanto não foi aberto navegador paralelo nem iniciado
  download sem sessão confirmada.

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

## Pendências e retomada

1. Retomar pelo lote congelado já validado somente após disponibilizar um
   Chrome autenticado com DevTools/CDP local para o coletor (ou executar o
   pacote portátil pelo seu launcher e concluir login humano nessa janela).
2. Executar o builder em staging reservado para materializar o runtime e rodar
   `portable/TESTAR-PACOTE.ps1` contra o pacote gerado; conferir manifest,
   hashes, CRC/extração limpa e allowlist.
3. Fazer o piloto supervisionado nos Chrome já autenticados: uma linha vermelha,
   uma complementada e uma ausente; depois um lote pequeno de qualificação.
4. Somente com o piloto verde, analisar as 1.128 chaves e apresentar a prévia.
5. Confirmar cada lote produtivo de até 300 individualmente; interromper se a
   reconciliação exata do e-Contas encontrar ausência ou ambiguidade.
6. Para futuras alterações, verificar `git status`, adicionar somente os
   arquivos da mudança com `git add --`, fazer commit nominal e `git push`.

Para continuar, não recrie a fila: valide o arquivo `analysis-0e2f3c9e...json`,
verifique a identidade do navegador autenticado e execute o coletor com
`-FilaCongelada ... -NumeroLote 1 -EscopoPortal sector_finalistic
-NaoInterativo -Python C:\Python314\python.exe` somente quando o CDP local
estiver disponível. A Área Restrita e o e-Contas devem permanecer autenticados
por login humano; não automatizar credenciais nem submissão. Restaurar o
clipboard CUA e a paginação do e-Contas já foi feito.
