# Guia de reexecução dos testes da Mesa Local

**Data:** 2026-09-21  
**Branch:** `codex/mesa-local-refactor`  
**Diretório:** `C:\Users\slvma\Downloads\Github\Atos-TCE`

Este guia substitui as instruções antigas de pareamento por código. A extensão
atual é confiável automaticamente: não digite código, não clique em Parear e não
use a extensão antiga de `work/tce-extractor`. A extensão suportada é a pasta
`extension/`, cujo ID esperado é
`nhpklhieopdbomkojifcengjaklabjng`.

O Chrome pode omitir `Origin` na requisição GET real do service worker. A
extensão atual envia `X-TCE-Extension-ID` automaticamente; não é necessário
adicionar cabeçalhos manualmente no DevTools. O preflight continua sendo feito
com a origem da extensão e a Mesa exige o ID confiável, o bearer e o cliente
registrado para aceitar o fallback.

## 1. Preparar a branch

Abra uma janela PowerShell para os comandos do repositório:

```powershell
Set-Location 'C:\Users\slvma\Downloads\Github\Atos-TCE'
git switch codex/mesa-local-refactor
git pull --ff-only origin codex/mesa-local-refactor
git status --short --branch
```

O arquivo local `work/tce-extractor/.codex-live-pilot.py`, se aparecer como
`??`, deve ser preservado e não precisa ser adicionado ao Git.

## 2. Rodar os testes automatizados

Execute estes comandos na raiz do repositório:

```powershell
npm test --prefix extension
node --test app/web/tests/*.test.mjs
python -m unittest discover -s tests -p 'test_*.py' -q
```

Resultados esperados no estado atual:

- extensão: `123` testes, `123` aprovados;
- web: `16` testes, `16` aprovados;
- Python: `559` testes, `559` aprovados.

Feche o servidor e o Chrome antes do teste de pacote:

```powershell
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\packaging\build-portable.ps1
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\packaging\verify-package.ps1 -ZipPath .\dist\Atos-TCE-portable.zip
```

Execute o gate oficial:

```powershell
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1
```

O gate oficial deve terminar sem falhas. Os skips ambientais já documentados
podem permanecer como skips.

## 3. Iniciar a Mesa depois de fechar tudo

Confirme que não há Chrome aberto, sem encerrá-lo à força:

```powershell
Get-Process chrome -ErrorAction SilentlyContinue | Select-Object Id,Path
```

Abra uma segunda janela PowerShell, mantenha-a aberta e inicie a Mesa sem
abrir o perfil pessoal automaticamente:

```powershell
Set-Location 'C:\Users\slvma\Downloads\Github\Atos-TCE'
.\START.cmd --data-root data --port 18743 --no-browser
```

O terminal deve mostrar `Mesa Local em http://127.0.0.1:18743/` e uma linha
`URL de sessão da Mesa` terminando em `/bootstrap#token=...`. Copie a URL inteira
somente para a próxima etapa; nunca copie apenas a raiz
`http://127.0.0.1:18743/`.

## 4. Abrir o Chrome QA

Use um perfil separado. Se o perfil abaixo já existir, ele preserva o login
manual do QA; se for novo, o login no portal será feito manualmente:

```powershell
$chromeCandidates = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)
$chrome = $chromeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $chrome) { throw 'chrome.exe não encontrado' }
$qaProfile = "$env:LOCALAPPDATA\AtosTCE\perfil-qa-20260921"
if (Test-Path -LiteralPath (Join-Path $qaProfile 'SingletonLock')) {
    throw "Feche a janela Chrome QA que usa este perfil antes de iniciá-la com CDP: $qaProfile"
}
Start-Process -FilePath $chrome -ArgumentList @(
    '--remote-debugging-port=9222',
    "--user-data-dir=$qaProfile",
    '--no-first-run',
    '--no-default-browser-check'
)
$portFile = Join-Path $qaProfile 'DevToolsActivePort'
$deadline = (Get-Date).AddSeconds(15)
while ((-not (Test-Path -LiteralPath $portFile)) -and ((Get-Date) -lt $deadline)) {
    Start-Sleep -Milliseconds 250
}
if (-not (Test-Path -LiteralPath $portFile)) {
    throw "Chrome QA não iniciou CDP. Confirme se a janela abriu: $qaProfile"
}
$port = Get-Content -LiteralPath $portFile -TotalCount 1
Invoke-RestMethod -Uri "http://127.0.0.1:$port/json/version" -TimeoutSec 5 |
    Select-Object Browser, 'Protocol-Version'
```

O Chrome QA abre sem URL para que você cole nela a URL da Mesa/START.cmd na
própria barra de endereço. Se o e-Contas pedir autenticação, faça login
manualmente nessa janela. Para os gates M2/M3/M5, abra a Área Restrita e
confirme manualmente o marcador antes de continuar. Não coloque senha, código
ou token no terminal, script ou log.

O comando acima deve mostrar `Browser` e `Protocol-Version`. Se a pasta de perfil
estiver aberta sem CDP, feche apenas a janela que usa esse perfil e execute o
bloco novamente; não rode o scanner antes de o teste responder.

## 5. Carregar a extensão atual

No Chrome QA:

1. Abra `chrome://extensions`.
2. Ative **Modo do desenvolvedor**.
3. Clique em **Carregar sem compactação**.
4. Selecione `C:\Users\slvma\Downloads\Github\Atos-TCE\extension`.
5. Confirme que o ID exibido é `nhpklhieopdbomkojifcengjaklabjng`.
6. Abra o painel lateral da extensão.

O painel deve chegar a **Mesa conectada** sem código. Se aparecer **Parear**,
**Reparear** ou código de seis dígitos, a pasta antiga foi carregada: atualize a
extensão apontando para a pasta raiz `extension/` e abra o painel novamente.

Para testar a recuperação automática, no DevTools do service worker execute
somente:

```javascript
chrome.storage.local.remove(["tce.bridge.token"])
```

Depois aguarde o próximo ciclo do painel. A extensão deve se registrar de novo
sem intervenção. Para testar token inválido, altere temporariamente apenas
`tce.bridge.token`; a API deve fazer uma recuperação e uma nova tentativa, sem
entrar em loop.

## 6. Gate M2 — Área Restrita real

Com o portal autenticado no Chrome QA:

1. Na Mesa, clique em **Analisar Área Restrita**.
2. Aguarde a varredura terminar.
3. Rode o fallback CDP contra o mesmo perfil QA:

```powershell
$qaProfile = "$env:LOCALAPPDATA\AtosTCE\perfil-qa-20260921"
if (-not (Test-Path -LiteralPath (Join-Path $qaProfile 'DevToolsActivePort'))) {
    throw "Chrome QA não está ativo com depuração remota neste perfil: $qaProfile"
}
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\scripts\scan-area-cdp.ps1 -ChromeUserData $qaProfile 1> data\logs\area-cdp.json 2> data\logs\area-cdp-diagnostics.log
if ($LASTEXITCODE -ne 0) {
    Get-Content -LiteralPath data\logs\area-cdp-diagnostics.log
    throw 'A varredura CDP falhou; não compare um arquivo de saída incompleto.'
}
Get-Content data\logs\area-cdp-diagnostics.log
```

O JSON do scanner fica em `area-cdp.json` e o diagnóstico em
`area-cdp-diagnostics.log`; o script exige `DevToolsActivePort` no perfil
informado.
Depois compare com a última varredura persistida:

O PowerShell 5.1 pode gravar a saída redirecionada como UTF-16LE; o comparador
detecta o BOM e também aceita JSON UTF-8.

```powershell
python scripts/compare-area-scans.py --cdp-json data\logs\area-cdp.json --db data\atos-tce.db --json data\logs\area-compare.json
if ($LASTEXITCODE -ne 0) { throw 'M2 não passou; confira area-compare.json.' }
Get-Content data\logs\area-compare.json
```

M2 passa somente com código de saída `0` e `"equal": true`, no mesmo marcador,
escopo e conjunto de processos. Divergência bloqueia o avanço.

## 7. Gate M3 — aquisição real limitada

Na Mesa, monte o plano e dispare somente o lote solicitado. Anote o ID do job
mostrado pela Mesa e substitua `<JOB_ID>`:

```powershell
python scripts/verify-acquisition.py --db data\atos-tce.db --job <JOB_ID> --json data\logs\acquisition-<JOB_ID>-check.json
Get-Content data\logs\acquisition-<JOB_ID>-check.json
```

M3 passa somente se as chaves pedidas forem as únicas baixadas, o job fechar
todos os itens, falha de autenticação pausar o job e não houver PDF duplicado.

## 8. Gate M5 — formulário real sem envio

Primeiro use o caminho manual: abra um ato no portal, deixe o painel ler o
formulário atual e acompanhe a solicitação na Mesa. Depois, se autorizado,
teste o caminho automático em um processo `PRONTO`.

Critérios obrigatórios:

- a releitura confirma exatamente os valores propostos;
- divergência resulta em `BLOQUEADO`;
- falha do portal resulta em `ERRO`;
- `autoSubmit=false` e `real_send_enabled=false` continuam ativos;
- nenhum botão final de envio/conclusão é clicado pela automação.

O clique final, se for realizado, é manual e fica fora deste teste automatizado.

## 9. M6 — pacote, auditoria e limpeza

Somente depois de M2, M3 e M5 reais aprovados, faça a auditoria de armazenamento
em modo somente leitura:

```powershell
python scripts/storage-audit.py --repo-root . --data-root data --json data\logs\storage-audit.json
python scripts/cleanup-storage.py --audit data\logs\storage-audit.json --json data\logs\storage-cleanup-plan.json
Get-Content data\logs\storage-cleanup-plan.json
```

Não use `--apply` nesta reexecução. A retirada do legado e a limpeza destrutiva
exigem recibo canônico, suíte verde, tag `pre-legacy-retirement`, gates reais
aprovados e autorização explícita do operador.

## 10. Encerrar e registrar

Quando terminar a rodada:

```powershell
git status --short --branch
git diff --check
git rev-parse HEAD
git ls-remote origin refs/heads/codex/mesa-local-refactor
```

Registre os resultados M2/M3/M5 sem tokens, cookies, senhas, HAR ou trace. Se
algum gate real não for executado, marque-o como `BLOCKED_HUMAN_PORTAL`; fixture,
teste automatizado ou pacote não substitui a execução real.
