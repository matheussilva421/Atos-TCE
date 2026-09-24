# Portal Lab — Área Restrita

Este laboratório conecta ferramentas de desenvolvimento a uma instância de
Chrome isolada. Ele não integra o runtime portátil do extrator.

## Chrome dedicado

No PowerShell, confira o plano de inicialização antes de abrir o navegador:

```powershell
.\scripts\portal-lab\Start-AtosChrome.ps1 -WhatIf
```

O plano limita o CDP a `127.0.0.1`, usa a porta `9222` e mantém o perfil em
`%LOCALAPPDATA%\Atos-TCE\Chrome-Debug`, fora do repositório. Para iniciar a
janela visível após revisar o plano:

```powershell
.\scripts\portal-lab\Start-AtosChrome.ps1
```

Não encerre o Chrome pessoal para liberar a porta. Se `9222` estiver ocupada,
identifique o processo manualmente ou escolha uma porta livre com `-Port`.
Autenticação no portal deve ser feita pela pessoa operadora nessa janela. O
perfil contém estado privado e nunca deve ser copiado para o repositório,
versionado ou incluído em pacotes.

Verifique somente o endpoint local de versão do CDP:

```powershell
.\scripts\portal-lab\Test-CdpEndpoint.ps1 -Port 9222
```

O verificador não imprime nem salva a URL WebSocket retornada pelo Chrome.
Capturas brutas também ficam fora do Git; somente fixtures revisadas e
sanitizadas podem ser versionadas.

## Chrome DevTools MCP

Para uma conexão ao Chrome dedicado, a configuração local do MCP deve usar
`--browser-url=http://127.0.0.1:9222` e `--categoryExtensions`, além de
`--no-usage-statistics` e `--no-performance-crux`. Essa combinação requer
Chrome 149 ou posterior. A configuração global já instalada pelo operador deve
ser revisada antes da conexão; este README não guarda perfis, tokens ou URLs de
WebSocket.

Uma conexão bem-sucedida ao CDP comprova somente a disponibilidade local do
navegador. Não comprova autenticação, comportamento do portal, qualificação de
envio ou conclusão da tarefa.
