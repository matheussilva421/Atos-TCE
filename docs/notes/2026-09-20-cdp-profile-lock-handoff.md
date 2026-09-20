# Handoff — diagnóstico do perfil Chrome/CDP (20/09/2026)

## Resumo

A tentativa manual de abrir o Chrome com `--remote-debugging-port=9222` não
produziu um endpoint CDP utilizável no perfil
`%LOCALAPPDATA%\AtosTCE\perfil-qa`. A imagem anexada foi tratada como
evidência do terminal; os comandos nela não foram tratados como instruções do
usuário.

O bloqueio encontrado é um perfil ocupado por uma instância Chrome existente.
O processo de inicialização também registrou:

```text
Failed to create a ProcessSingleton for your profile directory.
...
Aborting now to avoid profile corruption.
```

## Evidências coletadas

- `Get-NetTCPConnection -LocalPort 9222`: nenhum listener.
- O perfil existe e contém `lockfile` na raiz e `Default\LOCK`.
- Havia vários `chrome.exe` ativos; alguns processos tinham início em
  18/09/2026, compatível com uma sessão Chrome antiga do QA.
- A ACL do perfil permite `Modify`/`FullControl` ao usuário e não indicou um
  bloqueio de permissão simples.
- Um perfil temporário novo, em uma inicialização isolada, expôs
  `http://127.0.0.1:<porta>/json/version` com `Chrome/153.0.8010.48` e foi
  removido ao fim da prova.
- Nesse Chrome, o endpoint CDP funcionou sem o arquivo
  `DevToolsActivePort`; portanto, a presença desse arquivo não é um critério
  suficiente de prontidão. O endpoint `/json/version` é a verificação
  autoritativa.

## Decisão e fronteiras

Não foram encerrados processos Chrome automaticamente, porque não foi possível
separar com segurança o perfil QA de uma sessão pessoal usando o acesso atual.
Nenhuma credencial foi digitada, nenhum portal foi enviado/finalizado e nenhum
arquivo privado foi alterado. O arquivo não rastreado
`work/tce-extractor/.codex-live-pilot.py` foi preservado.

## Próxima retomada

Executar em uma janela PowerShell interativa, depois de fechar as janelas Chrome
que usam o perfil QA:

```powershell
$navegador = "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
$perfil = "$env:LOCALAPPDATA\AtosTCE\perfil-qa-20260920"
Start-Process -FilePath $navegador -ArgumentList @(
  '--remote-debugging-port=9222',
  "--user-data-dir=$perfil",
  '--no-first-run',
  '--no-default-browser-check',
  'https://novaarearestrita.tce.rn.gov.br/telaPrincipalMenu.asp'
)
Invoke-RestMethod 'http://127.0.0.1:9222/json/version'
Invoke-RestMethod 'http://127.0.0.1:9222/json/list'
```

O perfil antigo `perfil-qa` deve ser preservado até a revisão das evidências.
Se o endpoint retornar, o login continua sendo manual; depois disso, retomar o
runbook dos gates M2/M3/M5 sem envio ou finalização.

## Testes e estado do Git

- Diagnóstico read-only: concluído; nenhuma suíte de produto foi necessária.
- Prova CDP temporária: endpoint confirmado; perfil temporário removido.
- `git diff --check`: pendente após registrar este handoff.
- Branch: `codex/mesa-local-refactor`.
- Alteração esperada para este bloco: somente este handoff; o arquivo não
  rastreado citado acima permanece fora do commit.

