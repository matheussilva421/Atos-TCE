# Relatório QA integral

- Schema: `qa-matrix-v1`
- Execução: `qa-20260914T135539Z`
- Commit: `46587c68b3f4199ec5afe3497cda49af1a5bc911`

## Resumo

| Estado | Quantidade |
|---|---:|
| `BLOCKED` | 5 |
| `NOT_TESTED` | 20 |
| `PASS_FIXTURE` | 2 |
| `PASS_PACKAGE` | 3 |

## Matriz por função

| ID | Função | Camada | Risco | Automação | Estado | Evidência |
|---|---|---|---|---|---|---|
| offline.package-audit | Auditoria do pacote privado | offline | low | automatic | `PASS_PACKAGE` | bounded command exit code and output hash |
| offline.launcher-bat | INICIAR.bat delega ao launcher | offline | low | automatic | `NOT_TESTED` | no execution evidence |
| offline.launcher-cmd | INICIAR.cmd inicia ponte/menu | offline | medium | fixture | `NOT_TESTED` | no execution evidence |
| offline.review-launcher | ABRIR-MESA.cmd abre mesa HTTP | offline | low | fixture | `PASS_FIXTURE` | bounded command exit code and output hash |
| offline.menu-1 | Menu 1 coleta processos | offline | high | fixture | `NOT_TESTED` | no execution evidence |
| offline.menu-2 | Menu 2 analisa acervo | offline | medium | fixture | `NOT_TESTED` | no execution evidence |
| offline.menu-3 | Menu 3 gera HTML | offline | medium | fixture | `NOT_TESTED` | no execution evidence |
| offline.menu-4 | Menu 4 exporta dados da extensão | offline | high | fixture | `NOT_TESTED` | no execution evidence |
| offline.menu-5 | Menu 5 abre HTML existente | offline | low | fixture | `NOT_TESTED` | no execution evidence |
| offline.menu-6 | Menu 6 executa fluxo completo | offline | high | fixture | `NOT_TESTED` | no execution evidence |
| offline.menu-7 | Menu 7 diagnostica runtime | offline | low | automatic | `NOT_TESTED` | no execution evidence |
| offline.menu-8 | Menu 8 reseta acervo | offline | critical | fixture | `NOT_TESTED` | no execution evidence |
| offline.menu-9 | Menu 9 verifica ponte | offline | medium | fixture | `NOT_TESTED` | no execution evidence |
| offline.menu-10 | Menu 10 adquire lote congelado | offline | high | fixture | `NOT_TESTED` | no execution evidence |
| web.collections | Alternância Meus Processos/Setor | web | medium | automatic | `PASS_PACKAGE` | bounded command exit code and output hash |
| web.pdf-viewer | Viewer PDF e evidências | web | medium | automatic | `NOT_TESTED` | no execution evidence |
| web.review-controls | Busca, zoom, rotação, splitter e concluído | web | medium | automatic | `NOT_TESTED` | no execution evidence |
| extension.panel-tabs | Cinco abas do painel | extension | low | automatic | `PASS_PACKAGE` | bounded command exit code and output hash |
| extension.dataset | Importação e atualização do lote | extension | high | fixture | `NOT_TESTED` | no execution evidence |
| extension.search-review | Pesquisa manual e Revisado | extension | medium | automatic | `NOT_TESTED` | no execution evidence |
| extension.fill | Preencher campos disponíveis | extension | critical | fixture | `PASS_FIXTURE` | bounded command exit code and output hash |
| extension.override | Override individual de divergência | extension | critical | fixture | `NOT_TESTED` | no execution evidence |
| extension.bridge | Pareamento e reconexão da ponte | extension | high | fixture | `NOT_TESTED` | no execution evidence |
| extension.analysis | Análise do marcador e criação de lotes | extension | high | fixture | `NOT_TESTED` | no execution evidence |
| extension.execution | Execução, pausa, retomada e histórico | extension | critical | fixture | `NOT_TESTED` | no execution evidence |
| portal.observation | Fluxo humano observado na Área Restrita | portal | high | manual | `BLOCKED` | human checkpoint required |
| portal.marker | Marcador já selecionado e paginação | portal | high | manual | `BLOCKED` | human checkpoint required |
| portal.form | Interessado, formulário e preflight | portal | critical | manual | `BLOCKED` | human checkpoint required |
| portal.reversible-fill | Preenchimento reversível supervisionado | portal | critical | manual | `BLOCKED` | human checkpoint required |
| portal.send-gate | Gate futuro de conclusão/envio | portal | critical | manual | `BLOCKED` | human checkpoint required |

Os artefatos brutos permanecem na área privada da execução e não são incorporados a este relatório.
