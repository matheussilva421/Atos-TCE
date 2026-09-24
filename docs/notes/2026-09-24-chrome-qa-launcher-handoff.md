# Handoff — launcher do Chrome QA

Data: 2026-09-24
Status: implementação e gates concluídos; commit e push pendentes.

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
antes desta alteração. Commit e push serão registrados no fechamento final.

## Retomada

1. Revisar `git diff --check`, `git status` e o diff final.
2. Fazer commit e push na branch atual; verificar SHA e sincronização com o
   remoto e registrar esses dados neste handoff.

Para uso manual: dê duplo clique em
`work/tce-extractor/Abrir-Chrome-QA.bat`. Para começar em outra página, passe a
URL como primeiro argumento. Se a porta 9222 estiver ocupada, feche o processo
que a usa e tente novamente.
