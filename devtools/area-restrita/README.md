# Portal Lab — Área Restrita

Este laboratório conecta ferramentas de desenvolvimento a uma instância de
Chrome isolada. Ele não integra o runtime portátil do extrator.

## Chrome QA dedicado com a extensão

O launcher usa o Chromium gerenciado pelo Playwright para carregar a extensão
unpacked e verifica o manifesto da service worker antes de declarar sucesso.
O Google Chrome estável atual ignora os flags de sideload usados pelo launcher
antigo, então uma janela aberta sozinha não prova que a extensão foi carregada.
O runtime portátil do Atos-TCE não depende de Node nem Playwright.

Confira o plano sem abrir o navegador:

```powershell
.\scripts\portal-lab\Start-AtosChrome.ps1 -PlanOnly
```

Para abrir o QA com a extensão da fonte `extension/` e CDP em loopback:

```powershell
.\work\tce-extractor\Abrir-Chrome-QA.bat
```

Para abrir diretamente a Área Restrita:

```powershell
.\work\tce-extractor\Abrir-Chrome-QA.bat `
  -Url https://novaarearestrita.tce.rn.gov.br/telaPrincipalMenu.asp
```

O launcher mantém o perfil em
`%LOCALAPPDATA%\Atos-TCE\Chrome-QA-Playwright`, fora do repositório. No
primeiro uso, autentique-se manualmente nessa janela; a sessão fica no perfil
para usos seguintes. Perfis anteriores não são reutilizados nem alterados. A
extensão e o CDP são confirmados antes de navegar para a URL solicitada. A
saída `QA_EXTENSION_READY` inclui ID, nome e versão; `CDP_READY` confirma
`127.0.0.1:<porta>`.

O launcher precisa do Node.js, do pacote Playwright e do Chromium instalado.
Ele detecta a distribuição agrupada pelo Codex nesta máquina. Em outra
instalação, informe `-NodePath`, `-PlaywrightEntry` e `-BrowserCachePath`, ou
use os equivalentes `ATOS_TCE_NODE_EXE`, `ATOS_TCE_PLAYWRIGHT_ENTRY` e
`PLAYWRIGHT_BROWSERS_PATH`. O launcher não fecha o Chrome pessoal. Se a porta
`9222` estiver ocupada, ele para sem alterar o processo que a está usando; use
`-Port` para selecionar uma porta livre.

Verifique o endpoint local de versão do CDP:

```powershell
.\scripts\portal-lab\Test-CdpEndpoint.ps1 -Port 9222
```

O verificador não imprime nem salva a URL WebSocket retornada pelo Chrome.
Capturas brutas também ficam fora do Git; somente fixtures revisadas e
sanitizadas podem ser versionadas.

## Abrir a Mesa no mesmo Chrome QA

Quando a Área Restrita já estiver autenticada no Chrome QA e a Mesa estiver
respondendo em `127.0.0.1:18743`, use o launcher de desenvolvimento abaixo. Ele
substitui somente a chamada de abertura do navegador no processo da Mesa e
encaminha a URL de bootstrap de uso único ao CDP local do Chrome QA. O token
permanece no fragmento da URL, não aparece no terminal e não é enviado ao
portal. O runtime e o pacote portátil não dependem deste launcher.

Se outra instância da Mesa estiver usando a mesma pasta `data`, encerre-a
primeiro com `Ctrl+C` na janela em que foi iniciada. Depois, na raiz do
repositório, inicie:

```powershell
python .\scripts\portal-lab\launch_mesa_in_qa_chrome.py `
  --cdp-url http://127.0.0.1:9222 -- `
  --data-root data --host 127.0.0.1 --port 18743
```

O launcher valida que o CDP e seu WebSocket estão em loopback antes de iniciar
a Mesa. A aba nova do mesmo perfil recebe o bootstrap oficial e retorna ao
dashboard local. Confirme “Mesa conectada” no painel da extensão. Para analisar,
deixe a aba autenticada da Área Restrita ativa no Chrome QA; a extensão precisa
encontrar essa aba quando recebe o comando da Mesa. O launcher recusa host fora
de `127.0.0.1` e porta da Mesa já ocupada. Não copie a URL de bootstrap para o
portal ou para outro perfil.

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

## Playwright CLI

O CLI é uma ferramenta somente de desenvolvimento. Instale a skill oficial no
workspace com `playwright-cli install --skills=agents` quando necessário e use
o workflow restrito em
`.agents/skills/area-restrita/references/workflow.md` para anexar ao Chrome
dedicado, observar snapshots e encerrar com `detach`. O CLI e seus artefatos
locais não entram no runtime nem no pacote portátil.

## Capturas estruturais

`scripts/portal-lab/capture-structure.js` é uma expressão para executar no
contexto da página. Ela coleta somente rota sem query, estado do documento,
caminho do frame, atributos estruturais dos controles, sentinelas vazias e
quantidade de frames filhos; nunca lê valores dos controles.

Guarde a captura bruta em `tmp/portal-lab/<sessao>/raw/` e crie também a pasta
`sanitized/` da sessão. Para criar uma cópia sanitizada e comparar duas
observações:

```powershell
python .\scripts\portal-lab\sanitize-capture.py `
  .\tmp\portal-lab\<sessao>\raw\before.json `
  .\tmp\portal-lab\<sessao>\sanitized\before.json

python .\scripts\portal-lab\sanitize-capture.py `
  .\tmp\portal-lab\<sessao>\raw\after.json `
  .\tmp\portal-lab\<sessao>\sanitized\after.json

python .\scripts\portal-lab\compare-captures.py `
  .\tmp\portal-lab\<sessao>\sanitized\before.json `
  .\tmp\portal-lab\<sessao>\sanitized\after.json
```

O sanitizador recusa sobrescrever uma saída existente sem `--force`, elimina
cookies/headers/storage e valores, remove query strings e rejeita saída com
padrões residuais de identificador ou token. Arquivos brutos, sanitizados e
diffs continuam fora do Git.

## Contrato e fixtures

`portal-contract.json` é o contrato documental e oráculo dos testes; o runtime
continua usando os leitores em `extension/lib/area-snapshot.js` e
`extension/content/detect-form.js`. `transitioning` e `ambiguous` fazem parte do
vocabulário permitido, mas o scanner atual não os emite. Fixtures de teste usam
identidades fictícias; fixtures `live-*` guardam somente estrutura sanitizada.

`fixtures/live-frame-tree.json` registra uma observação L0 de 2026-09-25: um
frame de lista e três documentos de formulário coexistiam no tab; somente um
formulário tinha área visível, enquanto dois irmãos antigos tinham largura e
altura zero. A captura não contém valores, nomes ou identidades. Ela documenta
a visibilidade observada e não prova uma transição de navegação.

`fixtures/live-pagination.json` registra a lista viva do marcador PROFESSOR -
IPERN: 1.197 itens em 40 páginas, com 30 linhas canônicas por página. A leitura
dos primeiros 60 itens, comparada por hashes apenas em memória, corresponde à
mesma ordem do scan salvo id 8. A leitura direta de `SCAN_PAGE` reportou
100.249 páginas, um item canônico e quatro linhas ignoradas antes de falhar por
repetição da página 1. Links numéricos dos resultados parecem contaminar a
leitura de paginação; essa é uma hipótese para investigar por captura → fixture
→ teste, sem aumentar retries.

`fixtures/live-modality-error.json` registra duas tentativas isoladas em atos
pendentes. A página do portal substituiu as opções de modalidade por um erro
VBScript `800a005e` na linha 773 e omitiu seis sentinelas obrigatórias. A
extensão permaneceu desabilitada e nenhum campo foi escrito. O fixture não
contém número de processo, interessado ou valores de campos.

Execute a verificação de paridade com:

```powershell
node --test extension/tests/portal-contract.test.mjs
```

As rotas e o vínculo de frame irmão registrados no contrato são limitados ao
código e aos testes legados existentes; uma mudança real do portal exige nova
captura sanitizada antes de alterar este contrato ou o runtime.
