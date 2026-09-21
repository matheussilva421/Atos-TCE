# Complementação de Atos — TCE/RN

A Mesa Local é o centro de workflow e estado do sistema: varredura da Área
Restrita, coleta no e-Contas, análise com OCR/evidências, revisão e
preenchimento assistido do ato. O acervo canônico de PDFs fica em `data/`, fora
do Git, e é independente da versão do programa.

## Começar

```powershell
.\START.cmd --data-root data --port 18743
```

`START.cmd` é o launcher único: usa o Python embutido do pacote quando ele
existe (`runtime\python\python.exe`) e, fora do pacote, o Python do sistema. O
mesmo comando direto é:

```powershell
python -m app.main --data-root data --port 18743
```

O launcher imprime a **URL inicial de sessão**, com `/bootstrap#token=...`. Esse
token é de uso único e é consumido pelo primeiro perfil que abrir a URL. Para
transferir uma Mesa já aberta para outro perfil, como o Chrome QA, clique em
**Copiar sessão para outro Chrome** na seção Área Restrita e cole a URL gerada
no outro perfil em até cinco minutos. Copiar somente
`http://127.0.0.1:18743/` não transfere a sessão, porque o cookie fica preso ao
perfil do navegador.

O servidor só aceita loopback. `data/` guarda `atos-tce.db` (SQLite, schema 5),
`archive/blobs` com os PDFs canônicos nomeados pelo SHA-256, `archive/processos`
com a visão por processo (hardlinks para os blobs) e `logs/` com os recibos de
migração, auditoria e limpeza.

## Fluxo da Mesa

1. **Área Restrita** — a extensão varre a página e envia o retrato; a Mesa cruza
   com o acervo e marca o que precisa de complementação (`PRECISA_COMPLEMENTAR`).
2. **e-Contas** — a aquisição de processos é disparada pela Mesa, em lote
   limitado e fail-closed.
3. **Análise** — PDFs, OCR/texto nativo, fundamento legal, classificação e
   evidências alimentam a revisão.
4. **Revisão** — a Mesa mostra processos, documentos, campos e evidência.
5. **Preenchimento** — a Mesa monta o plano, a extensão fina navega, lê, preenche
   e relê o formulário; qualquer divergência bloqueia.

O clique final de complementação do ato **continua humano** em todos os fluxos.
Se a navegação automática falhar, o caminho manual preenche o formulário que já
está aberto usando o mesmo plano e o mesmo preflight.

## Extensão

A extensão suportada é a da raiz, `extension/` (Manifest V3 fina). Depois de
carregada no Chrome/Edge, ela reconhece a Mesa local automaticamente; não há
senha, código de pareamento ou etapa de reparo. Se a credencial local ficar
ausente ou inválida, o service worker registra novamente a extensão confiável e
refaz a chamada uma única vez. Instalação: em `chrome://extensions` (ou o
equivalente no Edge) ative o modo de desenvolvedor, escolha *Carregar sem
compactação* e aponte para `extension/`.

`extension/lib/protocol.js` mantém `FORBIDDEN_COMMAND_TYPES` justamente para que
um teste possa provar que não existe comando de SUBMIT, SEND, AUTO_SUBMIT,
COMPLEMENT_ACT ou FINALIZE.

## Pacote portátil

O ZIP padrão contém aplicação, extensão, runtime fixo e licenças — **nunca** o
acervo de processos. Ele é construído e verificado por:

```powershell
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\packaging\build-portable.ps1
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\packaging\verify-package.ps1 -ZipPath .\dist\Atos-TCE-portable.zip
python scripts/rotate-builds.py --dist dist
python scripts/rotate-builds.py --dist dist --apply --verified-hash <sha256 do pacote verificado>
```

- `build-portable.ps1` monta o pacote a partir de `app/`, `extension/`,
  `START.cmd`, `README.md`, do runtime verificado e das licenças; o construtor de
  runtime baixa as versões fixas por HTTPS e confere cada SHA-256 antes de usar.
- `verify-package.ps1` recusa PDFs, bancos, perfis de navegador, `data/`,
  `acervo-tce/`, bytecode e arquivos de build; confere cada arquivo de runtime
  contra o `runtime-manifest.json` e roda o smoke de extração limpa (o pacote
  sobe numa raiz de dados isolada, responde `/api/v1/health` e a extração é
  apagada no PASS).
- `rotate-builds.py` mantém apenas o build atual e o anterior em `dist/`; o modo
  `--apply` exige o hash do pacote que passou na verificação.

O ZIP antigo (com acervo) continua no histórico e nas entregas privadas, mas não
é mais o artefato padrão: atualizar o programa não copia PDFs.

## Backup e limpeza de armazenamento

Backup completo é uma ação explícita e separada do release:

```powershell
python scripts/backup.py --data-root data --output D:\backups\atos-tce-2026-09-18.zip
```

O ZIP leva o snapshot do SQLite (pela API de backup, então as linhas que ainda
estão no WAL entram), todos os blobs canônicos e um `manifest.json` com
`schema_version`, `db_sha256`, contagem, bytes e o SHA-256 de cada arquivo.

Antes de apagar qualquer coisa, audite e planeje:

```powershell
# somente leitura: mede o repositório e prova o que está preservado no acervo canônico
python scripts/storage-audit.py --repo-root . --data-root data --json data\logs\storage-audit.json
# dry-run por padrão; só remove o que o recibo aprovou
python scripts/cleanup-storage.py --audit data\logs\storage-audit.json
```

A limpeza nunca toca em `data/`, `dist/`, `.git` nem nas árvores de código, exige
`safe_to_delete` do recibo, re-mede a árvore antes de remover (mudou? novo
recibo), recusa reparse points e grava `data/logs/storage-cleanup-<UTC>.json`.

## Fronteiras de segurança

- `autoSubmit=false` e `real_send_enabled=false`: a automação para antes do
  clique final, que é humano.
- Login na Área Restrita e no e-Contas é sempre humano; nenhuma automação digita
  credenciais.
- O servidor da Mesa só escuta loopback e o token de bootstrap vai no fragmento
  da URL.
- Nunca versionar PDFs, ZIPs, perfis de navegador, tokens, HAR ou trace.

## Legado (fallback até o gate destrutivo)

`work/tce-extractor` continua no repositório como referência e fallback: o menu
PowerShell, o serviço local e o sidepanel antigos seguem funcionando, e o
acervo de origem (`work/tce-extractor/acervo-tce`) é preservado. Nenhum caminho
de runtime suportado depende dele: `app/`, `extension/`, `packaging/` e
`START.cmd` são verificados por `tests/test_no_legacy_paths.py`.

A retirada dessa superfície exige o gate destrutivo completo — acervo canônico
com todos os SHAs únicos, recibo de migração de M1, suíte verde, tag
`pre-legacy-retirement` e execução real supervisionada do preenchimento — mais a
autorização explícita do operador. O estado de cada marco está em
`docs/notes/2026-09-18-mesa-refactor-handoff.md`.

### Notas históricas preservadas

- O acervo privado de 05/09 é uma entrega diferente do pacote de ferramentas:
  contém 227 processos, 5.236 eventos e 4.532 PDFs, e permanece fora do Git.
- O runtime `fase11k` (`outputs/tce-processos-completo-portatil-fase11k.zip`) foi
  o pacote de ferramentas, extensão e serviço da rodada anterior: extraia-o
  inteiro e abra `GUIA-RAPIDO.html`; não versione nem compartilhe esse ZIP.
- No pacote legado o envio automático fica desabilitado por padrão
  (`real_send_enabled = false`) e o comando explícito de envio real é
  `INICIAR.cmd envio-real` — que a Mesa não usa: aqui o clique final é humano.
- O lote real 1/50 foi baixado com 50 processos e 1.037 PDFs completos; essa
  evidência permanece privada.

## Estrutura

| Pasta | Finalidade | Git |
|---|---|---|
| `app/` | Mesa Local: serviço, API, análise, e-Contas, arquivo híbrido e web | Versionado |
| `extension/` | Extensão fina (MV3) suportada | Versionada |
| `packaging/` | Builder, verificador, manifesto do runtime e licenças | Versionado |
| `scripts/` | Migração, auditoria, limpeza, backup e retenção de builds | Versionado |
| `tests/` | Suíte Python da Mesa | Versionada |
| `data/` | Acervo canônico, banco e recibos (runtime) | Ignorado |
| `dist/` | ZIP atual e anterior | Ignorado |
| `tmp/` | Extrações de QA e rascunhos | Ignorado |
| `work/tce-extractor/` | Extração legada, fallback e acervo de origem | Código permitido |
| `outputs/`, `Versions/` | Entregas e extrações antigas | Ignorado |
| `docs/` | Estrutura, planos e handoffs | Versionado |

## Desenvolvimento e testes

```powershell
# suíte Python da Mesa (raiz)
python -m unittest discover -s tests -p 'test_*.py' -q
# testes da extensão fina
Set-Location extension; npm test; Set-Location ..
# contrato do pacote (inclui o allowlist do ZIP real quando dist/ existe)
python -m unittest tests.test_packaging_contract -v
```

O gate offline do projeto continua sendo:

```powershell
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1
```

Ele roda extensão, web, Python portátil, testes PowerShell, pacote/auditoria,
automação da raiz e `git diff --check`; é somente offline (não abre Chrome
autenticado, não coleta e não envia). Para a suíte Python completa da raiz, rode
também o `unittest discover` acima, que o gate não cobre inteiro.

Se você chamar `powershell.exe` a partir de um host que exporta o `PSModulePath`
do PowerShell 7, o Windows PowerShell 5.1 pode carregar o módulo `Utility` do
pwsh e perder cmdlets como `Get-FileHash`. Rodar a partir de um PowerShell 5.1
normal (ou num `PSModulePath` só com os módulos do 5.1) evita esse desvio.
