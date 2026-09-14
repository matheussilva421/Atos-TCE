# Relatório QA integral

- Schema: `qa-matrix-v1`
- Execução: `qa-20260914T180904Z`
- Commit: `b21762efe73c09a61665d67bae90a20bb3d692cf`

## Resumo

| Estado | Quantidade |
|---|---:|
| `BLOCKED` | 5 |
| `PASS_FIXTURE` | 24 |
| `PASS_PACKAGE` | 1 |

## Matriz por função

| ID | Função | Camada | Risco | Automação | Estado | Evidência |
|---|---|---|---|---|---|---|
| offline.package-audit | Auditoria do pacote privado | offline | low | automatic | `PASS_PACKAGE` | bounded command exit code and output hash |
| offline.launcher-bat | INICIAR.bat delega ao launcher | offline | low | automatic | `PASS_FIXTURE` | bounded command exit code and output hash |
| offline.launcher-cmd | INICIAR.cmd inicia ponte/menu | offline | medium | fixture | `PASS_FIXTURE` | bounded command exit code and output hash |
| offline.review-launcher | ABRIR-MESA.cmd abre mesa HTTP | offline | low | fixture | `PASS_FIXTURE` | bounded command exit code and output hash |
| offline.menu-1 | Menu 1 coleta processos | offline | high | fixture | `PASS_FIXTURE` | bounded command exit code and output hash |
| offline.menu-2 | Menu 2 analisa acervo | offline | medium | fixture | `PASS_FIXTURE` | bounded command exit code and output hash |
| offline.menu-3 | Menu 3 gera HTML | offline | medium | fixture | `PASS_FIXTURE` | bounded command exit code and output hash |
| offline.menu-4 | Menu 4 exporta dados da extensão | offline | high | fixture | `PASS_FIXTURE` | bounded command exit code and output hash |
| offline.menu-5 | Menu 5 abre HTML existente | offline | low | fixture | `PASS_FIXTURE` | bounded command exit code and output hash |
| offline.menu-6 | Menu 6 executa fluxo completo | offline | high | fixture | `PASS_FIXTURE` | bounded command exit code and output hash |
| offline.menu-7 | Menu 7 diagnostica runtime | offline | low | automatic | `PASS_FIXTURE` | bounded command exit code and output hash |
| offline.menu-8 | Menu 8 reseta acervo | offline | critical | fixture | `PASS_FIXTURE` | bounded command exit code and output hash |
| offline.menu-9 | Menu 9 verifica ponte | offline | medium | fixture | `PASS_FIXTURE` | bounded command exit code and output hash |
| offline.menu-10 | Menu 10 adquire lote congelado | offline | high | fixture | `PASS_FIXTURE` | bounded command exit code and output hash |
| web.collections | Alternância Meus Processos/Setor | web | medium | automatic | `PASS_FIXTURE` | source web unit suite; target package has separate static audit |
| web.pdf-viewer | Viewer PDF e evidências | web | medium | automatic | `PASS_FIXTURE` | source web unit suite; target package has separate static audit |
| web.review-controls | Busca, zoom, rotação, splitter e concluído | web | medium | automatic | `PASS_FIXTURE` | source web unit suite; target package has separate static audit |
| extension.panel-tabs | Cinco abas do painel | extension | low | automatic | `PASS_FIXTURE` | source extension Node suite; target package has separate static audit |
| extension.dataset | Importação e atualização do lote | extension | high | fixture | `PASS_FIXTURE` | source extension Node suite; target package has separate static audit |
| extension.search-review | Pesquisa manual e Revisado | extension | medium | automatic | `PASS_FIXTURE` | source extension Node suite; target package has separate static audit |
| extension.fill | Preencher campos disponíveis | extension | critical | fixture | `PASS_FIXTURE` | bounded command exit code and output hash |
| extension.override | Override individual de divergência | extension | critical | fixture | `PASS_FIXTURE` | source extension Node suite; target package has separate static audit |
| extension.bridge | Pareamento e reconexão da ponte | extension | high | fixture | `PASS_FIXTURE` | source extension Node suite; target package has separate static audit |
| extension.analysis | Análise do marcador e criação de lotes | extension | high | fixture | `PASS_FIXTURE` | source extension Node suite; target package has separate static audit |
| extension.execution | Execução, pausa, retomada e histórico | extension | critical | fixture | `PASS_FIXTURE` | source extension Node suite; target package has separate static audit |
| portal.observation | Fluxo humano observado na Área Restrita | portal | high | manual | `BLOCKED` | human checkpoint required |
| portal.marker | Marcador já selecionado e paginação | portal | high | manual | `BLOCKED` | human checkpoint required |
| portal.form | Interessado, formulário e preflight | portal | critical | manual | `BLOCKED` | human checkpoint required |
| portal.reversible-fill | Preenchimento reversível supervisionado | portal | critical | manual | `BLOCKED` | human checkpoint required |
| portal.send-gate | Gate futuro de conclusão/envio | portal | critical | manual | `BLOCKED` | human checkpoint required |

Os artefatos brutos permanecem na área privada da execução e não são incorporados a este relatório.
