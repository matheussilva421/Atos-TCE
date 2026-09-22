# Handoff — análise de armazenamento do projeto (2026-09-18)

## Resumo

Foi feita uma auditoria somente leitura da pasta
`C:\Users\slvma\Downloads\Github\Atos-TCE`. Nenhum arquivo foi removido,
movido ou alterado durante a análise. O projeto ocupa aproximadamente **60,1
GB** em tamanho lógico de arquivos, enquanto o volume C: tinha **56,43 GB
livres** no momento da medição.

O consumo está concentrado em cópias privadas do acervo de processos e em
pacotes/extrações de QA. Não é o histórico Git: `.git` mede cerca de 6,2 MB.

## Medição por área

| Área | Tamanho aproximado | Arquivos | Interpretação |
|---|---:|---:|---|
| `outputs/` | 39,91 GB | 99.823 | três extrações grandes, dois ZIPs privados e artefatos de QA |
| `Versions/` | 10,59 GB | 33.060 | ZIP e extração de referência preservada |
| `work/` | 9,41 GB | 33.767 | fonte ativa + acervo privado local |
| `.worktrees/` | 105 MB | 363 | worktree R3 e estado de trabalho |
| `dados-locais/` | 38,8 MB | 740 | perfil/execuções de QA |
| `.git/` | 6,2 MB | 1.564 | metadados e objetos Git |

## Principal causa

O acervo `acervo-tce/processos/` contém **14.179 PDFs**, somando cerca de
**8,28 GB por cópia**. Ele aparece em:

- `work/tce-extractor/acervo-tce/processos/`;
- `Versions/TCE-Meus-Processos-165-e-Setor-156-Extensao-Reorganizada-2026-09-16-final-professor-ipern/acervo-tce/processos/`;
- `outputs/TCE-fixed-2026-09-16/acervo-tce/processos/`;
- `outputs/qa-extract-2026-09-17/acervo-tce/processos/`;
- `outputs/tce-r3-completo/acervo-tce/processos/`.

As quatro extrações privadas têm aproximadamente 8,67–8,68 GB cada. Índices
`indice-classificado.json`, `indice-local.json` e um PDF representativo
tiveram o mesmo SHA-256 em todas as cinco cópias. A medição de extensão no
acervo confirmou que os PDFs respondem por 8,28 GB; JSONs respondem por apenas
cerca de 24,4 MB.

Os três ZIPs/extrações abaixo são os maiores itens individuais:

- `outputs/Atos-TCE-Professor-IPERN-completo-2026-09-16.zip`: 5.845.389.892 bytes;
- `outputs/Atos-TCE-Professor-IPERN-completo-2026-09-17.zip`: 5.845.381.507 bytes;
- cada uma das três extrações privadas em `outputs/`: aproximadamente 9,31 GB.

Os dois ZIPs possuem 33.057 entradas e diferem em 52 entradas de código,
launchers ou metadados de pacote. O inventário não encontrou diferença de
caminho/tamanho/compressão dentro de `acervo-tce/processos/`; ainda assim, os
ZIPs têm SHA-256 diferentes e não devem ser tratados como byte a byte iguais.

## Estado operacional observado

Foi encontrado processo Python ativo cujo executável está em
`outputs/qa-extract-2026-09-17/runtime`. Portanto essa extração está em uso no
momento da auditoria e não pode ser removida enquanto a execução/QA estiver
ativa.

`work/tce-extractor/portable/dados-locais/perfil-navegador/` ocupa cerca de
333,8 MB. O perfil parece antigo pela data dos arquivos, mas sua remoção
exigiria novo login manual; não foi tocado. `dados-locais/chrome-qa-profile/`
e `dados-locais/qa-runs/` somam cerca de 38,8 MB e contêm evidência de QA que
deve ser preservada até a conclusão dos gates.

## Fronteiras preservadas

- `Versions/` continua preservado como referência do projeto, conforme
  `AGENTS.md`.
- `work/tce-extractor/acervo-tce/` continua preservado como fonte/dado privado
  local do extrator.
- `outputs/TCE-fixed-2026-09-16/` continua preservado porque o handoff anterior
  o identifica como fonte do runtime verificado para empacotamento.
- `outputs/qa-extract-2026-09-17/` continua preservado por estar em uso.
- Nenhum conteúdo ignorado pelo Git foi incluído em commit; as zonas pesadas
  continuam fora do índice Git.

O handoff de 2026-09-17 registrou uma limpeza anterior de 13,7 GB. Os novos
artefatos `qa-extract-2026-09-17`, `tce-r3-completo` e o ZIP de 2026-09-17
explicam parte do crescimento posterior.

## Candidatos, somente após autorização e encerramento dos processos

Não são ações executadas; são opções para a próxima etapa:

1. Após terminar o QA, escolher uma única extração privada canônica. Remover ou
   arquivar `outputs/tce-r3-completo/` recuperaria aproximadamente 8,67 GB,
   mas somente depois de confirmar que o smoke/gate R3 não depende dela.
2. Se `TCE-fixed-2026-09-16/` continuar sendo a fonte de runtime, manter essa
   pasta e eliminar apenas cópias derivadas aprovadas. Se a fonte for migrada,
   duas extrações redundantes poderiam liberar aproximadamente 17,34 GB.
3. Escolher o ZIP oficial entre 16/09 e 17/09 depois de comparar o release
   esperado. A remoção de um deles liberaria aproximadamente 5,85 GB, mas os
   52 arquivos de código diferentes exigem decisão explícita.
4. Depois de fechar o QA e aceitar novo login manual, limpar o perfil de
   navegador portátil para recuperar aproximadamente 333,8 MB.

Para segurança, a próxima limpeza deve usar manifesto, SHA-256 e quarentena
reversível; não apagar diretamente `Versions/`, `acervo-tce/` ou uma extração
que esteja em execução.

## Git e validação

- Branch: `main`, alinhada a `origin/main` na leitura inicial.
- O worktree já estava sujo antes desta auditoria, com alterações locais em
  `README.md`, fontes/testes do extrator e `.codex-live-pilot.py`; essas
  alterações foram preservadas e não foram incluídas neste diagnóstico.
- A única alteração desta tarefa é este handoff.
- Não foram executados testes funcionais, pois a tarefa foi de diagnóstico de
  armazenamento e não alterou código.

## Retomada

Antes de qualquer remoção: (1) encerrar/confirmar os processos que usam
`qa-extract`; (2) definir com o operador qual extração e qual ZIP são
canônicos; (3) gerar manifesto com caminhos, tamanhos e SHA-256; (4) mover
primeiro para quarentena fora do caminho de execução; (5) revalidar os gates e
o espaço livre; (6) só então considerar exclusão autorizada.

## Segunda medição — 2026-09-18

O estado atual foi medido novamente sem alterações destrutivas:

- `outputs/`: 39.909.298.353 bytes, praticamente igual à medição anterior
  (variação de aproximadamente +102 KB);
- `Versions/`: 10.585.452.797 bytes, sem variação relevante;
- `work/`: 9.407.409.500 bytes, sem variação relevante;
- total lógico do projeto: aproximadamente 60,1 GB;
- espaço livre no volume C: 56,59 GB, contra 56,43 GB na medição anterior.

O crescimento está concentrado em `outputs/qa-extract-2026-09-17/`, que passou
de 33.059 para 33.063 arquivos e aumentou 98.555 bytes. Os novos/atualizados
artefatos incluem `.workflow-state.lock`, estado de execução, ordem/progresso
do portal e `dados-locais/bridge/service.json`. A pasta foi atualizada às
08:14 e continua operacionalmente ativa; não é candidata segura a remoção.

Foi observado também um estado que precisa de reconciliação antes de qualquer
limpeza: o marcador de serviço dessa extração registra
`real_send_enabled=true` com `real_send_qualification=missing`, mas aponta para
o PID 16140, que não está em execução. Há outro Python ativo usando o runtime
da extração de QA. Esse marcador pode ser obsoleto, mas deve ser tratado como
estado operacional sensível: não apagar, não reutilizar e não interpretar como
qualificação válida sem confirmar o serviço atual e a fronteira
`real_send_enabled=false`.

O Git avançou para `fe35a0c` (`origin/main`) e o worktree agora só mostra o
arquivo não rastreado `work/tce-extractor/.codex-live-pilot.py`. Nenhum arquivo
foi modificado por esta segunda auditoria.

## Terceira medição — 2026-09-22

Nova auditoria somente leitura executada após o Explorer informar 73,6 GB. A
varredura terminou sem erros, com 204.531 arquivos e 79.040.865.327 bytes
lógicos (**73,61 GiB**). O volume C: tinha **43,89 GiB livres**.

| Área | Bytes lógicos | GiB | Participação |
|---|---:|---:|---:|
| `outputs/` | 39.909.298.301 | 37,17 | 50,5% |
| `data/` | 17.859.792.897 | 16,63 | 22,6% |
| `Versions/` | 10.585.452.797 | 9,86 | 13,4% |
| `work/` | 9.472.346.061 | 8,82 | 12,0% |
| demais áreas | 1.213.975.271 | 1,13 | 1,5% |

Nota: os quatro grupos principais somam 77.826.890.056 bytes. O restante é
formado principalmente por `tmp/` (598.425.400 bytes), `staging-runtime/`
(258.566.158), `dist/` (192.231.504) e `.worktrees/` (105.099.422).

Por extensão, os PDFs dominam: 99.756 arquivos e 62.409.323.788 bytes
(**58,12 GiB; 79,0%**). Os 37 ZIPs somam 13.288.583.388 bytes (**12,38
GiB; 16,8%**). Código e histórico Git não explicam o consumo: `.git/` mede
10.203.230 bytes.

### Causa do crescimento desde 18/09

`outputs/`, `Versions/` e o acervo legado em `work/` permaneceram praticamente
no mesmo patamar. O novo bloco é `data/archive/`, criado pela migração da Mesa
Local e atualmente com 17.830.058.617 bytes lógicos (**16,61 GiB**):

- `data/archive/blobs/`: 14.205 PDFs canônicos, 8.907.628.790 bytes;
- `data/archive/processos/`: visão por processo dos mesmos 14.205 PDFs, mais
  JSONs; os PDFs são hardlinks para os blobs;
- `data/archive/publicacoes/`: dois arquivos, 6.445.854 bytes.

O par blob/visão não representa duas cópias físicas. `fsutil hardlink list`
confirmou no PDF amostrado que os dois caminhos apontam para a mesma identidade
NTFS. A contagem também é exata: 14.205 blobs e 14.205 PDFs na visão. Uma
segunda varredura por identidade de arquivo encontrou aproximadamente **65,19
GiB** de bytes únicos e **8,66 GiB** de sobrecontagem por entradas hardlink no
projeto. Assim, os 73,6 GiB do Explorer são tamanho lógico; o consumo físico
atribuível aos arquivos é menor, embora ainda alto.

O acervo canônico cresceu 26 PDFs desde o relatório de 18/09 (14.179 para
14.205). Isso é crescimento real de dados. A duplicação histórica continua
maior: o corpus de aproximadamente 8,3 GiB ainda existe fisicamente em
`work/`, em `Versions/`, em três extrações de `outputs/` e agora uma vez no
acervo canônico. Além disso, os dois ZIPs principais de `outputs/` somam cerca
de 10,89 GiB.

### Estado e retomada

- Nenhum arquivo pesado foi removido, movido ou regravado.
- Branch observada: `codex/mesa-local-refactor`, alinhada ao upstream em
  `98e4f8c` antes desta atualização documental.
- O arquivo preexistente não rastreado
  `work/tce-extractor/.codex-live-pilot.py` foi preservado.
- O relatório `data/logs/storage-audit.json` é de 18/09 e não deve autorizar
  uma limpeza atual sem nova auditoria completa com hashes.
- Antes de qualquer limpeza, medir processos/locks novamente, gerar recibo
  atual com hashes e escolher explicitamente quais pacotes derivados podem ser
  colocados em quarentena reversível. `data/archive/` é o acervo canônico e não
  é candidato.

### Validação da terceira medição

- `verify-project.ps1`: 1.258 testes/checks executados, 1.256 aprovados, 2
  pulados, 0 falhas; extensão, web, Python portátil, PowerShell, pacote,
  automação e `git diff --check` passaram.
- `python -m unittest discover -s . -p 'test_*.py' -q`, dentro de
  `work/tce-extractor`: 528 executados, 519 aprovados, 8 pulados e 1 falha.
  A falha está em
  `test_analysis_pipeline.AnalysisPipelineTests.test_classifies_title_content_and_never_targets_event_one`
  (`test_analysis_pipeline.py:828`): o primeiro documento foi classificado
  como `pendente_ocr`, enquanto o teste esperava `outro_documento`.
- A falha ampla não foi corrigida nesta tarefa porque a alteração realizada é
  somente documental e o pedido foi diagnóstico de armazenamento. Ela deve ser
  reproduzida e investigada separadamente antes de declarar a suíte raiz
  totalmente verde.
