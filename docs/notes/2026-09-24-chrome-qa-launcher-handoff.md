# Handoff — launcher do Chrome QA

Data: 2026-09-24
Status: implementação, gates, commit e push concluídos.

## Objetivo e decisão

Criar um atalho reutilizável para abrir o Chrome de QA com DevTools visível e
CDP local, usando o perfil privado padrão do gravador em
`dados-locais/chrome-qa-profile`. O Chrome pessoal não é reutilizado. O atalho
carrega somente a extensão local do extrator e começa em `about:blank`, aceitando
uma URL opcional.

## Arquivos alterados

- `work/tce-extractor/Abrir-Chrome-QA.bat` — entrada de duplo clique e repasse
  de argumentos.
- `work/tce-extractor/Abrir-Chrome-QA.ps1` — resolve Chrome, prepara o perfil,
  carrega a extensão, ativa DevTools/CDP em `127.0.0.1:9222` e evita colisões
  com outro perfil ou processo na porta.
- `work/tce-extractor/tests/Test-QAChromeLauncher.ps1` — verifica o plano
  chamando o próprio `.bat`, sem abrir Chrome.
- `work/tce-extractor/verify-project.ps1` — inclui o novo teste PowerShell no
  gate normal.
- `.gitignore` — allowlist para o `.bat` na raiz do extrator.

## Validações

- RED: o teste falhou antes da implementação porque o launcher ainda não
  existia.
- GREEN: `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy
  Bypass -File .\tests\Test-QAChromeLauncher.ps1` — 11 checks aprovados, 0
  falhas.
- Os dois arquivos PowerShell usam UTF-8 com BOM; o teste focado foi repetido
  depois do ajuste de codificação e continuou verde.
- `git diff --check` — passou.
- `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass
  -File .\work\tce-extractor\verify-project.ps1` — 1.259 verificações,
  1.257 aprovadas, 0 falhas, 2 skips.
- `python -m unittest discover -s . -p 'test_*.py' -q` — 528 testes, 519
  aprovados, 0 falhas, 9 skips.
- A descoberta Python emitiu avisos de API `fitz` depreciada, limpeza de
  respostas HTTP simuladas e um erro esperado de argumento inválido; o comando
  terminou com código 0.
- O teste usou `-PlanOnly`; o Chrome não foi iniciado e o perfil QA não foi
  criado durante a validação. A sessão real do navegador continua não testada.

## GitHub

Checkout `codex/atos-tce-unified`, alinhado com `origin/codex/atos-tce-unified`
após o push. Commit da implementação e testes: `dd46dec`
(`feat(qa): add Chrome QA launcher`), publicado na branch.

## Uso

Para uso manual, dê duplo clique em
`work/tce-extractor/Abrir-Chrome-QA.bat`. Para começar em outra página, passe a
URL como primeiro argumento. Se a porta 9222 estiver ocupada, feche o processo
que a usa e tente novamente.

## Correção operacional — Chrome 137 ou mais recente

- O launcher histórico acima foi criado antes da remoção das flags de carga de
  extensões. `Abrir-Chrome-QA.ps1 -PortalLab` seleciona corretamente a fonte
  `extension/`, mas `--load-extension` e `--disable-extensions-except` não
  carregam a extensão em versões atuais do Google Chrome.
- Em Chrome 154, uma inicialização isolada reproduziu as mensagens
  `--disable-extensions-except is not allowed in Google Chrome, ignoring` e
  `--load-extension is not allowed in Google Chrome, ignoring`; o perfil ficou
  sem a extensão apesar do launcher sair com código 0. O teste usou perfil
  temporário, `about:blank` e não acessou dados autenticados.
- Procedimento manual suportado neste projeto: iniciar o perfil QA que contém
  a sessão necessária; abrir `chrome://extensions` nessa mesma janela; ativar
  modo do desenvolvedor; clicar **Carregar sem compactação**; selecionar a
  pasta `C:\Users\slvma\Downloads\Github\Atos-TCE\extension` (a pasta que
  contém `manifest.json`, não um nível acima/abaixo); confirmar que o cartão
  `ATOS TCE — Ponte da Mesa` aparece. O ID estável esperado é
  `nhpklhieopdbomkojifcengjaklabjng`.
- Um toast de “Extensão carregada” sem cartão não é prova de instalação. Os
  perfis `dados-locais/chrome-qa-profile` e
  `%LOCALAPPDATA%/AtosTCE/perfil-qa-20260926` são distintos; confirme estar
  carregando na janela/perfil que mantém o login. Não apague nem recrie esses
  perfis durante a depuração.
- Para automação de testes que precisa carregar a extensão pela linha de
  comando, usar Chrome for Testing e uma integração de teste suportada; não
  tratar flags legadas no Google Chrome estável como instalação bem-sucedida.
- Em 2026-09-26 foram inspecionados `README.md`, este handoff, o handoff da Área
  Restrita, `Abrir-Chrome-QA.ps1`, `Start-AtosChrome.ps1` e os planos de Portal
  Lab. O README ainda descreve corretamente a instalação manual. A mensagem de
  sucesso do launcher continua imprecisa e precisa de correção TDD separada.
- Nenhuma sessão/processo foi encerrado, nenhum perfil QA autenticado foi
  alterado e nenhum ato/processo do portal foi aberto ou editado. As provas
  isoladas temporárias foram removidas. Testes de código não foram executados;
  `git diff --check` passou após o registro. Git permanece sem commit/push neste
  contexto.

## 2026-09-26 — launcher Playwright, extensão e sessão confirmadas

- Corrigi o falso sucesso do launcher: agora abre Chromium gerenciado pelo
  Playwright, mantém um perfil persistente novo fora do repositório, restringe
  CDP a loopback e aguarda a service worker da extensão antes de abrir a URL.
  A verificação compara nome e versão carregados com `manifest.json`.
- Fonte carregada: `extension/`. A inicialização real confirmou
  `ATOS TCE — Ponte da Mesa`, ID
  `nhpklhieopdbomkojifcengjaklabjng`, versão `0.1.0`, service worker ativo e
  `http://127.0.0.1:9222` disponível. Chrome DevTools MCP listou a extensão
  como Enabled.
- A ação da extensão abriu o side panel. Ele reportou “Mesa conectada”,
  “Área Restrita detectada” e “Nenhum formulário de ato aberto”. O usuário
  confirmou que a sessão está funcionando e autenticada. Nenhum processo ou
  ato foi aberto, selecionado ou alterado.
- A fila SQLite foi consultada em modo somente leitura e agregada por tipo e
  estado; todos os comandos encontrados estavam terminais. A inspeção não leu
  payloads, identidades ou resultados individuais.
- TDD: teste RED falhou pela ausência do runner Playwright. GREEN:
  `Test-QAChromeLauncher.ps1` aprovou 11/11 checks; `node --check
  scripts/portal-lab/launch-qa-chromium.mjs` passou. O teste confirma perfil
  novo externo, fonte correta, CDP loopback, Chromium Playwright, verificação
  da extensão e ausência de dependência dos flags removidos do Chrome estável.
- O launcher foi executado de verdade e reportou a extensão e CDP prontos. A
  tentativa de navegação teve uma resposta transitória
  `ERR_INVALID_AUTH_CREDENTIALS`; a enumeração seguinte mostrou a aba da Área
  Restrita aberta, e o side panel detectou a sessão autenticada, também
  confirmada pelo usuário.
- A aprovação automática rejeitou gravar em `tmp/portal-lab/.../raw` uma
  captura recursiva de frames/controles da sessão autenticada, pois IDs e nomes
  estruturais podem revelar detalhes privados. Não repeti a ação nem tentei
  outro canal para persistir o mesmo payload. A pasta criada para a captura
  permaneceu vazia.
- Arquivos desta correção: `scripts/portal-lab/Start-AtosChrome.ps1`, novo
  `scripts/portal-lab/launch-qa-chromium.mjs`,
  `work/tce-extractor/Abrir-Chrome-QA.ps1`,
  `work/tce-extractor/tests/Test-QAChromeLauncher.ps1` e este README/handoff.
  Nenhuma dependência de desenvolvimento foi adicionada ao runtime portátil.
- Git segue na branch `codex/atos-tce-unified`; alterações locais não
  commitadas e não publicadas. Verificador integrado e `git diff --check`
  ainda precisam rodar para este bloco.
- Pendências do goal: completar o verificador integrado; retomar Best-Effort
  Task 10 e Next Process Phase 0 com as evidências reais exigidas. A gravação
  da captura L0 para esses gates depende de aprovação explícita ao pedido
  específico, conforme o bloqueio do auto-review. Next Process Tasks 1–8
  continuam sob hard gate; nenhuma ação final foi executada.

## 2026-09-26 — validação final do launcher e das suítes

- Verificador integrado `work/tce-extractor/verify-project.ps1`: exit 0; 1.260 executados, 1.258 aprovados, 0 falhas e 2 skips; os sete estágios passaram.
- Suíte complementar `python -m unittest discover -s . -p 'test_*.py' -q`, executada em `work/tce-extractor`: exit 0; 529 testes, 520 aprovados, 0 falhas e 9 skips.
- `node --check scripts/portal-lab/launch-qa-chromium.mjs`, teste focado do launcher (11/11) e `git diff --check`: passaram.
- Chrome QA segue aberto com Chromium Playwright, extensão oficial Enabled/worker ativo, CDP em loopback; o usuário confirmou que a sessão está funcionando e autenticada. Nenhum processo/ato foi aberto ou editado.
- Git: branch `codex/atos-tce-unified`, HEAD `5f0d544869530e377f5f70d8f8a25fab0aa1f9bb`; alterações locais sem commit/push.
- Task 10 e Phase 0 dependem de evidência estrutural L0 persistida. O auto-review rejeitou a gravação recursiva por possível exposição de IDs/nomes de frames/controles; não houve nova tentativa. Solicitar autorização específica para persistir somente os campos allowlisted no diretório ignored antes dessa medição.

## 2026-09-26 — correção do modo `-File` e suíte raiz

- Baseline raiz tinha dois testes ainda acoplados à interface antiga `-ChromePath`/`-WhatIf`. Atualizei-os para verificar o contrato atual Playwright com `-PlanOnly`, incluindo engine, pasta `extension/`, CDP loopback, argumentos de porta/perfil e ausência de efeitos colaterais no perfil.
- A primeira execução do teste atualizado mostrou que `powershell.exe -File` avalia o default de `ExtensionRoot` com `$PSScriptRoot` vazio. Corrigi a resolução do default para ocorrer após `param`; `ProfileRoot` também é definido nesse bloco de inicialização. O wrapper e a chamada direta agora compartilham os mesmos defaults.
- TDD: RED observado no contrato focado; após correção, 20/20 passaram. Suíte raiz: 647 executados, 646 aprovados, 0 falhas, 1 skip.
- Validação complementar: extensão 160/160; web 29/29; verificador integrado 1.260 executados, 1.258 aprovados, 0 falhas, 2 skips; Python completo de `work/tce-extractor` 529 executados, 520 aprovados, 0 falhas, 9 skips. `git diff --check` verde.
- Limitação: há aviso de módulo ES no web e warnings de dependências/HTTP simulados na suíte Python complementar; não houve falha.
- Browser live: extensão oficial Enabled, service worker correto; Mesa conectada e Área Restrita detectada, sem formulário aberto. Nada foi preenchido ou finalizado.
- Próximo gate: aguardar autorização explícita para gravar apenas a captura estrutural L0 em pasta ignored. Task 10/Phase 0 continuam pendentes; preservar a ordem antes de Próximo processo.
