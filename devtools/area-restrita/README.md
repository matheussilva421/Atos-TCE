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

Use [`chrome-devtools-mcp.example.json`](chrome-devtools-mcp.example.json) como
exemplo de configuração do cliente MCP. Ele aponta explicitamente para
`http://127.0.0.1:9222`, habilita a categoria de extensões e desabilita
telemetria de uso e Performance CrUX. Essa combinação requer Chrome 149 ou
posterior. O exemplo não instala nem altera a configuração global do cliente.

Antes de usar uma sessão autenticada, confirme que o MCP está ligado ao Chrome
dedicado. A presença das ferramentas MCP, por si só, não identifica o browser
alvo. Siga os limites de acesso em
`.agents/skills/area-restrita/references/safety.md`.
Depois de alterar a entrada MCP, reinicie ou reconecte o cliente para aplicar os
novos argumentos e repita a confirmação do alvo antes de qualquer sessão real.

Uma conexão bem-sucedida ao CDP comprova somente a disponibilidade local do
navegador. Não comprova autenticação, comportamento do portal, qualificação de
envio ou conclusão da tarefa.
