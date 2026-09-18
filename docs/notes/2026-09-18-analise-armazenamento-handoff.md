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
