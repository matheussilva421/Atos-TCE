# AGENTS.md - contrato de estrutura do projeto Atos-TCE

Este arquivo existe para agentes. Ele descreve ONDE cada coisa vive, O QUE pode
ser usado como fonte de verdade e O QUE nunca deve ser alterado sem autorizacao.
Nao reinterprete o layout: os caminhos abaixo sao resolvidos por caminho relativo
pelos empacotadores e scripts. Mover ou renomear quebra o pacote.

## Regra de ouro

Para o runtime portátil atual e o Reliability Reset da Área Restrita, a fonte
de produção é a árvore da raiz: `app/`, `extension/`, `tests/`, `packaging/` e
`scripts/`. O builder copia essa árvore para o ZIP. Nunca implemente uma
correção de produção somente em `work/tce-extractor/` ou em um pacote extraído.

`work/tce-extractor/` é a árvore legada de compatibilidade/laboratório e contém
o verificador legado `verify-project.ps1`; ela não substitui nem espelha a fonte
do runtime atual. Alterações nela só se aplicam quando uma tarefa pedir
explicitamente manutenção daquele legado.

Não edite cópias geradas para corrigir a fonte. Preserve artefatos privados e
de referência; não os trate como código-fonte.

## Layout de nivel superior

| Caminho | O que é | Git | Editável |
|---|---|---|---|
| app/ | Runtime portátil e serviços da Mesa/Área Restrita | Sim | Sim, com TDD |
| extension/ | Extensão Chrome MV3 do runtime portátil | Sim | Sim, com TDD |
| tests/ | Testes Python e de integração do runtime da raiz | Sim | Sim, com TDD |
| packaging/ | Builder, contrato e verificador do ZIP portátil | Sim | Sim, com TDD |
| scripts/ | Ferramentas operacionais do runtime atual | Sim | Sim, com TDD |
| work/tce-extractor/ | Árvore legada, compatibilidade/laboratório e verificador legado | Sim (allowlist) | Só para tarefa explícita do legado |
| docs/ | ESTRUTURA.md, planos, handoffs e notas | Sim | Sim (documentacao) |
| README.md | Visao geral e como executar | Sim | Sim |
| outputs/ | ZIPs, extracoes e entregas privadas | Ignorado | Nunca como fonte |
| Versions/ | Extracoes de referencia preservadas | Ignorado | Nao sem autorizacao |
| dados-locais/ | Perfis Chrome de QA e execucoes de teste | Ignorado | Estado local |
| .superpowers/sdd/ | Ledger de tarefas e relatorios | Sim | Apenas registro |

## Árvore legada `work/tce-extractor/`

Os caminhos abaixo pertencem somente ao extrator legado e não são os módulos
de produção do runtime portátil atual.

| Caminho | Finalidade |
|---|---|
| portable/app/ | Servico local, menu, ferramentas Python do pacote |
| portable/app/web/ | Mesa HTML de revisao (frontend) |
| portable/extensao-complementar-ato/ | Extensao Chrome (MV3): background, content, lib, sidepanel |
| portable/portable/*.ps1/.psm1 | Launchers e modulos do pacote |
| tests/ | Testes PowerShell (Test-*.ps1) |
| test_*.py | Testes Python na raiz do extrator |
| docs/notes/ | Notas internas do extrator |
| acervo-tce/ | DADOS PRIVADOS locais (processos, PDFs, automacao) - ignorado |

Arquivos que vivem na RAIZ do extrator (nao em portable/app/):
batch_runner.py, html_generator.py, package_complete_archive.py, tce_extractor.py,
consolidate_results.py, organize_pdfs.py, targeted_collection.py, process_collections.py.
Eles sao copiados para dentro do pacote pelo empacotador como app/<nome>.py.
Nao procure esses arquivos em portable/app/ - eles nao estao la.

## Fluxo de dados do extrator legado

Este fluxo só se aplica a tarefas explicitamente voltadas ao extrator legado;
ele não redefine a origem do runtime portátil atual.

1. Coletar processos (menu 1 / Coletar-Processos-TCE.ps1)
2. Analisar acervo (menu 2)
3. Gerar HTML (menu 3)
4. Exportar JSON para a extensao (menu 4) -> acervo-tce/dados-complementar-ato.json
5. Importar o JSON no painel da extensao
6. Conferir/Complementar Ato no portal (manual por padrao)

O JSON atende o lote inteiro. Nao gere um por processo.

## fronteiras de seguranca (nao violar)

- autoSubmit=false e real_send_enabled=false sao a fronteira ate a qualificacao
  real no portal.
- Envio real exige: 3 preflights reais + observador de resultado +
  automacao/qualificacao.json valido. Falta o evento real.
- Nunca digite credenciais por automacao. Login e sempre humano.
- Nunca versione: PDFs, ZIPs, perfis de navegador, tokens, HAR, trace.
- Preserve Versions/: e referencia, nao area de trabalho.

## Validação antes de concluir qualquer mudança

Para a árvore raiz, rode os gates do plano ativo. No Reliability Reset, isso
inclui a suíte Python da raiz, testes da extensão, testes web e o contrato de
pacote. `work/tce-extractor/verify-project.ps1` é um verificador legado exigido
como gate adicional quando o plano ativo assim determinar; ele não substitui
os gates da árvore raiz.

    powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1

Para cobertura Python da fonte atual, execute na raiz do repositório:

    python -m unittest discover -s tests -p 'test_*.py' -q

## Arquivos legados que não devem ser "consertados" às cegas

Todos os caminhos desta tabela são relativos a `work/tce-extractor/` e não são
os módulos de produção do runtime portátil atual.

| Arquivo | Por que |
|---|---|
| `portable/app/package_audit.py` | Fail-closed por desenho; exige versão e módulos |
| `portable/app/qualification.py` | Guarda de envio real; mexe em real_send_enabled |
| `package_complete_archive.py` | Define EXCLUDED_DIRECTORIES (dados-locais, perfis, logs) |
| `portable/extensao-complementar-ato/content/portal-submit.js` | Envio real: observador obrigatório |
| `portable/app/prepare_transfer.py` | Quiescência de runtime e lock de operação |

## Convencoes

- Handoff em docs/notes/YYYY-MM-DD-escopo-handoff.md, sempre atualizado.
- TDD: teste que falha primeiro, correcao minima, teste verde.
- Nunca altere arquivo de Versions/ nem de outputs/ para "corrigir" codigo.
- Antes de concluir, verifique git status e o SHA; nao afirme push sem conferir.
