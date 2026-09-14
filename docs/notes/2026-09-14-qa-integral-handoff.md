# Handoff — QA integral, gravador e correções

## Estado atual

- Data: 2026-09-14.
- Pacote de referência: `Versions/TCE-Meus-Processos-165-e-Setor-156-Extensao-Reorganizada-2026-09-14`.
- Hash de árvore da referência: `aa847c5173ba0bfee0a9b75ee0b0374eabddca8036c707f4f11406ca2a9478cf`.
- O pacote de referência não recebeu alterações de código.
- A worktree/branch `codex/qa-integral-2026-09-14` não pôde ser criada porque o ambiente não permite criar refs em `.git`; o trabalho continua em `main` sem reset destrutivo.

## Implementado

- Contrato `qa-run-v1`, sanitização de eventos e matriz declarativa com 31 funções.
- Runner bounded da matriz com estados `PASS_REAL`, `PASS_PACKAGE`, `PASS_FIXTURE`, `FAIL_REPRODUCED`, `BLOCKED` e `NOT_TESTED`.
- Gravador observacional com trace, HAR, screenshots, console, navegação, falha de rede e eventos estruturais sem valores digitados.
- Perfil privado exato `dados-locais/chrome-qa-profile`; o CLI agora separa a raiz privada do pacote com `--private-root`.
- Detecção segura do service worker alvo; workers de componentes do Chrome não são aceitos como extensão Atos-TCE.
- Fechamento/relatório `BLOCKED` em falhas de inicialização.
- Identidade da execução preservada entre pasta privada e `run.json`.
- Classificação explícita de desafio inicial de autenticação, abortos de navegação e página interna `chromewebdata`, evitando falso positivo no campo `errors`.
- Opção explícita `--browser chromium` para fixture/QA quando o Chrome instalado estiver impedido por política; o padrão continua sendo Chrome instalado.
- `npm test` publicado no app web.
- Correções TDD de teste de abas, manifesto `webNavigation`, download autenticado via `fetch`, OCR com runtime empacotado, arquivos de runtime/licença, verificação de documentação e compatibilidade PowerShell.

## Evidências de teste

- Extensão fonte: 369/369.
- Web: 6/6, agora também por `npm test`.
- Python completo: 435 executados, 435 aprovados, 0 falhas, 8 skips.
- Contratos QA: 15/15.
- Verificação completa via Windows PowerShell 5.1: 1024 executados, 1022 aprovados, 0 falhas, 2 skips.
- PowerShell: `Test-TcePortable.ps1` 122/122; documentação 19/19; verificação 43/43; limpeza 307/307; menu 87/87.
- Chromium QA: manifesto, service worker e `sidepanel/panel.html` carregados; trace/HAR privados gerados.
- Chrome instalado: bloqueado pela política/ambiente gerenciado; o gravador registrou somente o componente Google Network Speech e encerrou como `BLOCKED`.
- Contratos QA finais: 15/15.
- Auditoria private da referência após retirar `dados-locais`: aprovada.
- O gate chamado via `pwsh` apresentou falso negativo por `PSModulePath`; o mesmo gate via Windows PowerShell 5.1 passou integralmente.
- A matriz final foi regenerada usando a referência imutável em `Versions/...`; a tentativa com `work/tce-extractor/portable` foi descartada porque a fonte não distribui o runtime portátil.
- Matriz final atual: `BLOCKED=5`, `PASS_FIXTURE=24`, `PASS_PACKAGE=1`, total de 30 funções; nenhum `FAIL_REPRODUCED`.

## Relatórios

- Inicial: `docs/notes/qa-initial-2026-09-14/qa-report.md` e `.json`.
- Final: `docs/notes/qa-final-2026-09-14/qa-report.md` e `.json`; resumo `BLOCKED=5`, `PASS_FIXTURE=24`, `PASS_PACKAGE=1`.
- Sessão real observacional: `docs/notes/qa-real-2026-09-14/qa-observation.md` e `.json`.
- Causas-raiz: `docs/notes/2026-09-14-qa-causas.md`.

## Sessão manual

- Execução encerrada: `qa-20260914T144623037910Z`, privada em `dados-locais/qa-runs/`.
- Browser: Chromium QA, `observe_only`, sem conclusão/envio/assinatura/tramitação.
- Foram registrados 83 eventos estruturais, incluindo `ProcessonoSetor.asp` e `ComplementarAto.asp`; não houve `submit_attempt`.
- A sessão teve 6 falhas de rede/console, portanto permanece observacional `BLOCKED`; não há `PASS_REAL`.
- O HAR mostrou o `401` apenas no bootstrap sem sessão e `200` após login; o novo diagnóstico não reclassifica essa execução antiga retroativamente.

## Pendência imediata

1. Repetir preflight real em uma sessão humana autenticada; o probe automático foi bloqueado por `net::ERR_NETWORK_ACCESS_DENIED`.
2. Confirmar três preflights consecutivos, releitura exata dos sete campos e ausência de submit antes de qualquer classificação `PASS_REAL`.
3. Tentar commit/push das correções do gravador; se `.git` continuar somente leitura, registrar os comandos para execução manual.

## Segurança e retomada

- Nunca abrir o perfil pessoal `Matheus`.
- Não usar `--ignore-certificate-errors`.
- Não expor ou versionar `dados-locais`, cookies, tokens, senhas, HAR, screenshots ou trace.
- Para retomar: usar `dados-locais/chrome-qa-profile`, passar `--private-root C:\Users\slvma\Downloads\Github\Atos-TCE` e usar `--browser chromium` se o Chrome instalado continuar gerenciado.

## GitHub

- Branch: `main`.
- Commit: `508a506 feat: add integral QA workflow and validated fixes`.
- Push: realizado para `origin/main`.
- Commits do bloco: `b21762e fix: classify isolated QA browser diagnostics` e `a6427a4 docs: refresh final QA matrix`.
- Push mais recente: `a6427a4` realizado para `origin/main`.
