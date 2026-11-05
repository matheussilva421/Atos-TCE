# Reconhecimento sanitizado da listagem (T01 / G1)

Data: 05/11/2026
Ambiente: Chrome QA isolado (`C:\Users\slvma\.codex\qa-econtas`), extensão 0.1.1 carregada, sessão autenticada pelo operador.
Escopo: leitura de estrutura DOM e de rótulos de interface. Nenhum processo foi aberto, nenhum formulário foi enviado e nenhum clique em salvar/complementar foi executado.

## Rota confirmada

- `#/dashboard/processos-no-setor/no-setor`
- Componente Angular: `processos-consulta-processo`.
- A rota foi adicionada a `src/shared/routes.mjs` como `parseListRoute`, restrita à origem do portal.

## Contrato observado da listagem

| Elemento | Seletor observado |
| --- | --- |
| Tabela | `tce-table#tabela-processos-consulta-id table.table.table-striped.text-center` |
| Linhas | `tbody tr` (10 por página) |
| Seleção da linha | `input[type="checkbox"].checkbox-custom` na primeira célula |
| Marcadores | `td.cel-marcadores` com `i.fa-bookmark` |
| Link do processo | `td.cel-processo a[href="#/dashboard/processos/<id>"]` |
| Rótulo do processo | texto de `td.cel-processo`, no formato `<número>/<ano> - <tipo>` |
| Ações | `td.cel-acoes` |
| Status pendente | `i.fa-solid.fa-file-signature.complemento-ato-pendente` |
| Status completo | `complemento-ato-completo` (token presente no bundle público do portal) |
| Paginação | `pagination-controls` / `ul.ngx-pagination`, com botões anterior/próximo |
| Filtro de marcador | `tce-select-field[formcontrolname="idMarcador"]` |
| Filtro de complementação | `tce-select-field[formcontrolname="atoComplementado"]` |
| Pendência de ato | `tce-select-field[formcontrolname="PossuiPendenciaAto"]` |
| Situação do processo | `tce-select-field[formcontrolname="OptInformacao"]` |

Os três tokens de classe foram confirmados no bundle público carregado pelo próprio portal: `complemento-ato-pendente`, `complemento-ato-completo` e `complementoAtoPessoalService`.

## Validação contra o DOM real

O leitor `src/list/list-reader.mjs` foi executado sobre o HTML da página aberta, com estes resultados:

| Verificação | Resultado |
| --- | --- |
| Reconhecimento da rota | PASS |
| Linhas lidas na página atual | 10 |
| IDs numéricos válidos | PASS |
| Rótulos normalizados (`número/ano`) | PASS |
| Paginação detectada | PASS (a leitura não avança de página) |
| Status classificados | 10 `pending` |
| Impressão de nomes, CPF, matrícula ou datas | nenhuma |

## O que permanece desconhecido

- URL real da aba de Autos: a varredura dos bundles já carregados pela listagem (05/11/2026) não encontrou o literal "autos", e a navegação para um processo não foi observada. O construtor `autosUrl` em `src/batch/workspace.mjs` é provisório e não deve ser tratado como contrato.
- Estrutura e texto do botão de salvamento e de eventual diálogo de confirmação: não observados sem executar um salvamento real. Permanecem `UNKNOWN_UNTIL_H2`.
- Prova pós-salvamento no portal: não observada.
- Comportamento de linhas com status ambíguo (nem pendente nem completo): o leitor classifica como `unknown` e exclui da fila.
- Semântica de outros filtros além de marcador e complementação: não usada pelo leitor.

## Consequência para os gates

- G1: contrato de listagem considerado comprovado para rota, linhas, IDs, status e contexto de filtros.
- G1 permanece incompleto para a UI de salvamento; isso bloqueia T12 e H2, não o desenvolvimento sintético do restante.
