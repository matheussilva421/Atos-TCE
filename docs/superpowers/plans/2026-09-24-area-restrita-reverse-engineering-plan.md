# Atos-TCE — Laboratório da Área Restrita Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar uma infraestrutura de engenharia reversa e QA da Área Restrita que permita ao Codex observar e compreender o portal legado com Chrome DevTools MCP e Playwright CLI, converter observações em contratos/fixtures/testes e melhorar a extensão, sem adicionar qualquer dependência dessas ferramentas ao runtime portátil.

**Architecture:** O laboratório fica isolado em `devtools/`, `.agents/skills/`, `scripts/portal-lab/` e `tmp/portal-lab/`. O Chrome DevTools MCP é a ferramenta primária de diagnóstico; Playwright CLI reproduz transições e gera evidência/testes; o runtime continua usando a Mesa + extensão MV3. Todo conhecimento operacional promovido pelo laboratório deve terminar em `extension/lib/area-snapshot.js`, `extension/content/navigate.js`, `extension/content/detect-form.js` ou `extension/background/router.js`, acompanhado de teste.

**Tech Stack:** Chrome DevTools Protocol, Chrome DevTools MCP, Playwright CLI, PowerShell 5.1+, Python 3, Node `node:test`, Chrome/Edge MV3, JSON Schema-like validation local, SQLite/runtime existente.

**Spec:** `docs/superpowers/specs/2026-09-24-area-restrita-lab-design.md`

## Global Constraints

- Ferramentas agentic/MCP/Playwright CLI são **somente de desenvolvimento**.
- O runtime distribuído não pode depender de Node.js, npm, MCP, Playwright CLI, Codex, ChatGPT ou API de LLM.
- `extension/lib/area-snapshot.js` permanece o dono único do conhecimento de seletores/assinaturas usado em runtime.
- Chrome de investigação deve usar perfil dedicado do Atos-TCE e CDP apenas em loopback.
- Chrome DevTools MCP deve executar com `--no-usage-statistics` e `--no-performance-crux`.
- Nenhuma captura raw contendo dados reais pode ser versionada.
- O laboratório não implementa nem executa conclusão/envio final de ato.
- Toda alteração de runtime derivada de observação real exige fixture sanitizada + teste RED antes da correção.
- O ZIP final deve permanecer funcional em extração limpa sem Node, MCP, Playwright ou IA.

## Review Focus

1. **Vazamento de dados reais:** fixture ou log versionado contendo processo, nome, CPF, cookie, token ou URL temporária deve ser rejeitado por teste.
2. **Dependência acidental de desenvolvimento no produto:** build com `.agents`, `devtools`, `playwright`, `chrome-devtools-mcp`, `node_modules` ou `tmp/portal-lab` deve falhar.
3. **Frame transitório confundido com tela desconhecida:** navegação deve distinguir `TRANSITIONING`/frame ainda carregando de uma tela estruturalmente inválida quando houver evidência suficiente.
4. **Dois frames candidatos:** ambiguidade nunca pode ser resolvida pela ordem de enumeração; deve bloquear com erro específico.
5. **Mudança do portal:** contrato/fixture divergente deve falhar nos testes antes que o runtime faça cliques com heurística antiga.

---

## Mapa de arquivos

### Criar

- `docs/superpowers/specs/2026-09-24-area-restrita-lab-design.md` — design aprovado.
- `devtools/area-restrita/README.md` — uso do laboratório.
- `devtools/area-restrita/chrome-devtools-mcp.example.json` — configuração segura de exemplo.
- `devtools/area-restrita/portal-contract.schema.json` — estrutura permitida do contrato.
- `devtools/area-restrita/portal-contract.json` — conhecimento estrutural sanitizado.
- `devtools/area-restrita/fixtures/*.json` — fixtures sanitizadas.
- `.agents/skills/area-restrita/SKILL.md` — workflow obrigatório do agente.
- `.agents/skills/area-restrita/references/safety.md`
- `.agents/skills/area-restrita/references/workflow.md`
- `.agents/skills/area-restrita/references/portal-states.md`
- `scripts/portal-lab/Start-AtosChrome.ps1`
- `scripts/portal-lab/Test-CdpEndpoint.ps1`
- `scripts/portal-lab/capture-structure.js`
- `scripts/portal-lab/sanitize-capture.py`
- `scripts/portal-lab/compare-captures.py`
- `tests/test_portal_lab_contract.py`
- `tests/test_devtools_runtime_boundary.py`
- `extension/tests/portal-contract.test.mjs`

### Modificar somente quando os gates de observação provarem necessidade

- `.gitignore`
- `extension/lib/area-snapshot.js`
- `extension/content/navigate.js`
- `extension/content/detect-form.js`
- `extension/background/router.js`
- `extension/lib/protocol.js`
- `extension/tests/*.test.mjs`
- `tests/test_packaging_contract.py`
- `packaging/verify-package.ps1`
- `README.md`
- `docs/ESTRUTURA.md`

---

### Task 1: Travar a fronteira “laboratório != runtime”

**Files:**
- Create: `tests/test_devtools_runtime_boundary.py`
- Modify: `tests/test_packaging_contract.py`
- Modify: `.gitignore`
- Modify: `packaging/verify-package.ps1` somente se o verificador atual não recusar genericamente as entradas novas.

**Interfaces:**
- Consumes: allowlist atual do packaging.
- Produces: contrato automatizado de que ferramentas de desenvolvimento nunca entram no ZIP.

- [ ] **Step 1: escrever teste RED da árvore de runtime**

Criar `tests/test_devtools_runtime_boundary.py` com verificação textual sobre `app/`, `extension/`, `packaging/` e `START.cmd`.

```python
DEV_ONLY_TOKENS = (
    "chrome-devtools-mcp",
    "playwright-cli",
    ".agents/skills/area-restrita",
    "devtools/area-restrita",
)

def test_supported_runtime_does_not_depend_on_portal_lab():
    roots = [REPO_ROOT / "app", REPO_ROOT / "extension", REPO_ROOT / "packaging"]
    offenders = []
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".py", ".js", ".ps1", ".psm1", ".json"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            if any(token.lower() in text for token in DEV_ONLY_TOKENS):
                offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == []
```

- [ ] **Step 2: rodar e registrar RED se existir dependência acidental**

Run:

```powershell
python -m unittest tests.test_devtools_runtime_boundary -v
```

Expected: PASS no baseline; se falhar, remover a dependência antes de continuar.

- [ ] **Step 3: ampliar contrato do ZIP**

Adicionar aos casos proibidos do `tests/test_packaging_contract.py`:

```python
{
    "devtools/area-restrita/portal-contract.json": b"{}",
    ".agents/skills/area-restrita/SKILL.md": b"# skill",
    "node_modules/chrome-devtools-mcp/package.json": b"{}",
    "tmp/portal-lab/raw/capture.json": b"{}",
}
```

O pacote artificial deve ser recusado.

- [ ] **Step 4: ignorar capturas privadas**

Garantir no `.gitignore`:

```gitignore
/tmp/portal-lab/
/.playwright-cli/
```

Não ignorar `devtools/area-restrita/fixtures/` nem `.agents/skills/area-restrita/`, porque são sanitizados/versionados.

- [ ] **Step 5: rodar os gates**

```powershell
python -m unittest tests.test_devtools_runtime_boundary tests.test_packaging_contract -v
```

Expected: todos verdes.

- [ ] **Step 6: commit**

```powershell
git add .gitignore tests/test_devtools_runtime_boundary.py tests/test_packaging_contract.py packaging/verify-package.ps1
git commit -m "test: isolate portal lab from portable runtime"
```

---

### Task 2: Criar Chrome dedicado e diagnóstico CDP reproduzível

**Files:**
- Create: `scripts/portal-lab/Start-AtosChrome.ps1`
- Create: `scripts/portal-lab/Test-CdpEndpoint.ps1`
- Create: `devtools/area-restrita/README.md`
- Test: `tests/test_portal_lab_contract.py`

**Interfaces:**
- Produces: Chrome dedicado com `--remote-debugging-port=9222` e endpoint verificável em loopback.
- Does not produce: cookies, sessão ou perfil dentro do repositório.

- [ ] **Step 1: escrever teste estático RED**

```python
def test_chrome_launcher_is_loopback_only_and_uses_external_profile():
    text = (REPO_ROOT / "scripts/portal-lab/Start-AtosChrome.ps1").read_text(encoding="utf-8")
    self.assertIn("--remote-debugging-port=9222", text)
    self.assertIn("--remote-debugging-address=127.0.0.1", text)
    self.assertNotIn("data\\\\", text.lower())
    self.assertNotIn("repoRoot", text)
```

- [ ] **Step 2: implementar launcher**

`Start-AtosChrome.ps1` deve:

- aceitar `-Port 9222`;
- aceitar `-ProfileRoot`, default em `%LOCALAPPDATA%\Atos-TCE\Chrome-Debug`;
- detectar Chrome estável;
- iniciar com loopback;
- nunca fechar Chrome pessoal;
- não apagar perfil;
- imprimir apenas porta/profile path, nunca cookies.

Exemplo de argumentos:

```powershell
$arguments = @(
  "--remote-debugging-address=127.0.0.1",
  "--remote-debugging-port=$Port",
  "--user-data-dir=$ProfileRoot",
  "--no-first-run",
  "--no-default-browser-check"
)
```

- [ ] **Step 3: implementar `Test-CdpEndpoint.ps1`**

Consultar:

```text
http://127.0.0.1:<porta>/json/version
```

Validar:

- HTTP 200;
- `webSocketDebuggerUrl` inicia por `ws://127.0.0.1:` ou `ws://localhost:`;
- resposta não é persistida.

- [ ] **Step 4: rodar testes estáticos**

```powershell
python -m unittest tests.test_portal_lab_contract -v
```

- [ ] **Step 5: gate manual de desenvolvimento**

```powershell
.\scripts\portal-lab\Start-AtosChrome.ps1
.\scripts\portal-lab\Test-CdpEndpoint.ps1
```

Expected: endpoint CDP detectado.

- [ ] **Step 6: commit**

```powershell
git add scripts/portal-lab devtools/area-restrita/README.md tests/test_portal_lab_contract.py
git commit -m "dev: add isolated Chrome portal lab"
```

---

### Task 3: Configurar Chrome DevTools MCP com segurança

**Files:**
- Create: `devtools/area-restrita/chrome-devtools-mcp.example.json`
- Modify: `devtools/area-restrita/README.md`
- Modify: `.agents/skills/area-restrita/references/safety.md`

**Interfaces:**
- Consumes: `http://127.0.0.1:9222`.
- Produces: configuração copiável para o MCP client do desenvolvedor.
- Runtime dependency: zero.

- [ ] **Step 1: criar configuração versionada de exemplo**

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": [
        "-y",
        "chrome-devtools-mcp@latest",
        "--browser-url=http://127.0.0.1:9222",
        "--no-usage-statistics",
        "--no-performance-crux"
      ]
    }
  }
}
```

- [ ] **Step 2: documentar a política de acesso**

`safety.md` deve conter explicitamente:

```text
PERMITIDO POR PADRÃO:
- listar páginas/frames
- snapshot
- console
- network
- evaluate de leitura
- screenshot estrutural

EXIGE GATE L1:
- paginação
- abrir Complementar Ato

EXIGE GATE L2:
- selecionar interessado
- preencher campos

PROIBIDO:
- clicar conclusão
- submit final
- assinatura
- tramitação
```

- [ ] **Step 3: teste do arquivo de configuração**

Em `tests/test_portal_lab_contract.py`, parsear JSON e exigir:

```python
args = config["mcpServers"]["chrome-devtools"]["args"]
self.assertIn("--browser-url=http://127.0.0.1:9222", args)
self.assertIn("--no-usage-statistics", args)
self.assertIn("--no-performance-crux", args)
```

- [ ] **Step 4: gate real de conexão**

Com Chrome dedicado aberto, usar o MCP e executar somente:

1. listar páginas;
2. selecionar aba da Área Restrita;
3. tirar snapshot;
4. listar requisições existentes;
5. não clicar.

Registrar em `tmp/portal-lab/<sessao>/raw/`, nunca no Git.

- [ ] **Step 5: commit**

```powershell
git add devtools/area-restrita/chrome-devtools-mcp.example.json devtools/area-restrita/README.md .agents/skills/area-restrita/references/safety.md tests/test_portal_lab_contract.py
git commit -m "dev: configure safe Chrome DevTools MCP"
```

---

### Task 4: Instalar e encapsular Playwright CLI como ferramenta de desenvolvimento

**Files:**
- Create: `.agents/skills/area-restrita/references/workflow.md`
- Modify: `devtools/area-restrita/README.md`
- No runtime files modified.

**Interfaces:**
- Consumes: Chrome CDP em `http://localhost:9222`.
- Produces: snapshots/trace de desenvolvimento.
- Runtime dependency: zero.

- [ ] **Step 1: documentar bootstrap**

Comandos oficiais esperados:

```powershell
playwright-cli install --skills=agents
playwright-cli attach --cdp=http://localhost:9222
playwright-cli snapshot
playwright-cli detach
```

A instalação da skill oficial pode ocorrer no workspace de desenvolvimento; o packaging nunca a copia.

- [ ] **Step 2: documentar regra de sessão**

`workflow.md`:

```text
1. attach
2. snapshot before
3. executar uma única transição autorizada
4. snapshot after
5. registrar diff
6. detach
```

Nunca encadear múltiplas ações desconhecidas em um único `run-code`.

- [ ] **Step 3: teste de fronteira**

Reexecutar:

```powershell
python -m unittest tests.test_devtools_runtime_boundary tests.test_packaging_contract -v
```

Expected: Playwright não aparece no runtime/ZIP.

- [ ] **Step 4: commit**

```powershell
git add .agents/skills/area-restrita/references/workflow.md devtools/area-restrita/README.md
git commit -m "docs: define Playwright portal investigation workflow"
```

---

### Task 5: Criar capturador estrutural e sanitizador

**Files:**
- Create: `scripts/portal-lab/capture-structure.js`
- Create: `scripts/portal-lab/sanitize-capture.py`
- Create: `scripts/portal-lab/compare-captures.py`
- Modify: `tests/test_portal_lab_contract.py`

**Interfaces:**
- Raw capture schema: páginas/frames/rotas/controles/metadata estrutural.
- Sanitized schema: sem valores sensíveis.
- Produces: JSON apto a virar fixture somente após sanitização.

- [ ] **Step 1: escrever RED para sanitização**

```python
def test_sanitizer_removes_private_values():
    raw = {
        "url": "https://portal/ComplementarAto.asp?cpf=12345678900",
        "cookies": [{"name": "ASPSESSIONID", "value": "secret"}],
        "fields": [{"id": "txtMatricula", "value": "12345"}],
        "text": "MARIA DA SILVA 012.345.678-90 processo 123456/2026",
    }
    clean = sanitize_capture(raw)
    blob = json.dumps(clean, ensure_ascii=False)
    for forbidden in ("12345678900", "secret", "12345", "MARIA DA SILVA", "012.345.678-90", "123456/2026"):
        self.assertNotIn(forbidden, blob)
```

- [ ] **Step 2: implementar sanitizador fail-closed**

O sanitizador deve:

- descartar cookies/headers/storage;
- remover query string de URLs, preservando path;
- nunca copiar `.value` de inputs;
- substituir texto livre por hashes/classificações quando não estiver em allowlist;
- preservar IDs, names, tagName, type, disabled, readOnly, option count;
- rejeitar saída se regex de CPF/processo/token continuar presente.

- [ ] **Step 3: implementar capturador estrutural**

`capture-structure.js` deve coletar somente:

```javascript
{
  route,
  readyState,
  framePath,
  controls: [{tag, id, name, type, disabled, readOnly, optionCount}],
  sentinels: [],
  childFrameCount
}
```

Nunca coletar valores digitados.

- [ ] **Step 4: implementar comparador**

`compare-captures.py before.json after.json` produz:

- frames adicionados/removidos;
- rotas alteradas;
- sentinelas adicionadas/removidas;
- controles adicionados/removidos;
- mudança de `readyState`.

- [ ] **Step 5: rodar testes**

```powershell
python -m unittest tests.test_portal_lab_contract -v
```

- [ ] **Step 6: commit**

```powershell
git add scripts/portal-lab tests/test_portal_lab_contract.py
git commit -m "dev: add sanitized portal structure capture"
```

---

### Task 6: Formalizar `portal-contract.json` e fixtures canônicas

**Files:**
- Create: `devtools/area-restrita/portal-contract.schema.json`
- Create: `devtools/area-restrita/portal-contract.json`
- Create: `devtools/area-restrita/fixtures/list-page.json`
- Create: `devtools/area-restrita/fixtures/interested.json`
- Create: `devtools/area-restrita/fixtures/form.json`
- Create: `devtools/area-restrita/fixtures/buttons.json`
- Create: `extension/tests/portal-contract.test.mjs`

**Interfaces:**
- Contract version: integer >= 1.
- States: `list`, `interested`, `form`, `buttons`, `transitioning`, `unknown`, `ambiguous`.
- Runtime continues consuming selectors through `area-snapshot.js`; contract is test oracle/documentation, not runtime config.

- [ ] **Step 1: schema mínimo**

```json
{
  "schema_version": 1,
  "states": {},
  "routes": {},
  "transitions": {},
  "forbidden_actions": ["finalize", "submit", "sign", "tramitate"]
}
```

- [ ] **Step 2: preencher contrato somente com fatos já comprovados**

Incluir:

- `ProcessonoSetor.asp`;
- `ComplementarAto.asp`;
- `botoesNOVO.asp`;
- `input[name=escolha]`;
- sentinelas de formulário;
- `NumeroPagina`;
- relação conhecida de frame irmão.

Não adicionar seletor apenas inferido.

- [ ] **Step 3: fixtures sanitizadas**

Cada fixture deve usar identidades fictícias:

```json
{
  "process_key": "000001/2099",
  "interested_normalized": "pessoa teste"
}
```

- [ ] **Step 4: teste JS de paridade**

`portal-contract.test.mjs` carrega contrato e `area-snapshot.js` e exige que:

- todos os estados de runtime estejam no vocabulário permitido;
- sentinelas FORM do contrato estejam cobertas pelo reader/scanner;
- fixture LIST seja classificada como LIST;
- fixture INTERESTED seja classificada como INTERESTED;
- fixture FORM seja reconhecida pelo form reader;
- BUTTONS não seja confundido com FORM.

- [ ] **Step 5: rodar testes**

```powershell
Push-Location extension
node --test tests/portal-contract.test.mjs
Pop-Location
python -m unittest tests.test_portal_lab_contract -v
```

- [ ] **Step 6: commit**

```powershell
git add devtools/area-restrita extension/tests/portal-contract.test.mjs
git commit -m "test: codify Area Restrita portal contract"
```

---

### Task 7: Criar Skill `area-restrita` para impedir patch por adivinhação

**Files:**
- Create: `.agents/skills/area-restrita/SKILL.md`
- Create: `.agents/skills/area-restrita/references/portal-states.md`
- Modify: `.agents/skills/area-restrita/references/safety.md`
- Modify: `.agents/skills/area-restrita/references/workflow.md`

**Interfaces:**
- Trigger conceptual: tarefas que alteram navegação/detecção/paginação/preenchimento da Área Restrita.
- Produces: processo obrigatório de investigação antes de alteração de runtime.

- [ ] **Step 1: escrever Skill**

A Skill deve obrigar a sequência:

```text
A. Ler portal-contract + código atual.
B. Classificar ação L0/L1/L2/L3.
C. L3 -> recusar.
D. Capturar BEFORE.
E. Executar no máximo uma transição.
F. Capturar AFTER.
G. Sanitizar.
H. Comparar.
I. Criar fixture.
J. Escrever teste RED.
K. Só então alterar runtime.
L. Rodar GREEN + suíte.
M. Verificar packaging boundary.
```

- [ ] **Step 2: regra contra timeout-first**

Incluir literalmente:

```text
Não corrija uma divergência real apenas aumentando RETRY/DELAY/TIMEOUT.
Primeiro identifique qual evidência estrutural distingue o estado observado.
Um ajuste de tempo só é permitido como limite superior depois de existir
um predicado estrutural testado.
```

- [ ] **Step 3: regra contra duplicação de seletor**

```text
Qualquer seletor promovido para runtime deve morar em area-snapshot.js
ou no módulo já designado como dono do controle. Não criar um segundo
mapa de seletores no router, Skill, script Python ou portal-contract.
```

- [ ] **Step 4: validar fronteira**

```powershell
python -m unittest tests.test_devtools_runtime_boundary tests.test_packaging_contract -v
```

- [ ] **Step 5: commit**

```powershell
git add .agents/skills/area-restrita
git commit -m "dev: add Area Restrita reverse engineering skill"
```

---

### Task 8: Executar mapeamento real observacional L0

**Files:**
- Modify: `devtools/area-restrita/portal-contract.json`
- Modify: fixtures somente com material sanitizado.
- Raw evidence: `tmp/portal-lab/<session>/` (ignored).

**Interfaces:**
- Input: Chrome dedicado autenticado pelo operador.
- Output: mapa real de frames/rotas/estados sem alteração do portal.

- [ ] **Step 1: preparar sessão**

```powershell
.\scripts\portal-lab\Start-AtosChrome.ps1
.\scripts\portal-lab\Test-CdpEndpoint.ps1
```

Operador faz login manualmente.

- [ ] **Step 2: capturar baseline**

Com DevTools MCP:

- listar páginas;
- selecionar Área Restrita;
- capturar frame tree;
- capturar network atual;
- console atual;
- snapshot;
- nenhuma interação.

- [ ] **Step 3: mapear telas manualmente acessíveis**

Capturar separadamente, sem preencher:

- lista;
- tela de interessado;
- formulário;
- frame de botões.

- [ ] **Step 4: sanitizar imediatamente**

```powershell
python .\scripts\portal-lab\sanitize-capture.py `
  .\tmp\portal-lab\<session>\raw\capture.json `
  .\tmp\portal-lab\<session>\sanitized\capture.json
```

- [ ] **Step 5: atualizar contrato**

Somente fatos repetidos/confirmados entram em `portal-contract.json`.

- [ ] **Step 6: rodar paridade**

```powershell
Push-Location extension
node --test tests/portal-contract.test.mjs
Pop-Location
```

Se RED, não alterar runtime ainda; o RED é evidência de divergência.

- [ ] **Step 7: commit apenas sanitizado**

```powershell
git add devtools/area-restrita/portal-contract.json devtools/area-restrita/fixtures extension/tests/portal-contract.test.mjs
git diff --cached
git commit -m "test: record sanitized Area Restrita observations"
```

---

### Task 9: Mapear transições L1/L2 uma por uma

**Files:**
- Modify: `portal-contract.json`
- Modify/Create: fixtures de transição.
- Modify: testes da extensão.

**Interfaces:**
- Transitions: `LIST -> LIST(next page)`, `LIST -> INTERESTED`, `INTERESTED -> FORM`, `FORM -> FORM_FILLED`.
- `FORM_FILLED -> FINALIZED` não existe no laboratório.

- [ ] **Step 1: paginação L1**

BEFORE → um avanço → AFTER.

Registrar:

- qual frame recebeu o clique;
- qual frame navegou;
- se URL mudou;
- quais frames foram recriados;
- como `NumeroPagina` mudou;
- evento network correlato.

Criar teste específico para a assinatura observada.

- [ ] **Step 2: abrir ato L1**

BEFORE LIST → abrir um ato autorizado → AFTER.

Registrar:

- `addtabsinformacao`;
- novo frame/aba lógica;
- rota;
- tempo apenas como métrica;
- sentinela que prova `INTERESTED`.

- [ ] **Step 3: selecionar interessado L2**

Somente em processo de teste/revisão aprovado.

Registrar transição estrutural para FORM, sem preencher.

- [ ] **Step 4: preencher L2 sem conclusão**

Usar valores propostos pela Mesa em um ato supervisionado; reler DOM; não clicar botão final.

Registrar apenas:

- IDs dos campos alterados;
- quantidade de alterações;
- sucesso da releitura;
- nunca valores reais na fixture.

- [ ] **Step 5: para cada divergência, TDD**

Exemplo:

```text
observação real
  -> fixture nova
  -> teste falha
  -> corrigir mínimo runtime
  -> teste passa
  -> suíte completa
```

- [ ] **Step 6: commit por transição**

Commits separados:

```text
test: capture legacy pagination transition
fix: recognize stable legacy pagination state

test: capture Complementar Ato frame transition
fix: classify interested frame transition

test: capture form materialization transition
fix: wait on form structural evidence
```

Não agrupar todas as transições num único commit.

---

### Task 10: Substituir falhas genéricas por estados/códigos observáveis onde houver evidência

**Files:**
- Modify: `extension/lib/area-snapshot.js`
- Modify: `extension/content/navigate.js`
- Modify: `extension/background/router.js`
- Modify: `extension/lib/protocol.js` se novos códigos forem formalizados.
- Test: `extension/tests/navigate.test.mjs`, `extension/tests/router.test.mjs` ou equivalentes atuais.

**Interfaces:**
- Existing public commands remain: `SCAN_AREA`, `OPEN_ACT`, `READ_FORM`, `FILL_FORM`.
- Result codes may become more specific without introduzir ação final.

- [ ] **Step 1: escrever RED para `TRANSITIONING`**

Somente se a captura real mostrar sinal confiável.

Exemplo de expectativa:

```javascript
assert.deepEqual(result, {
  ok: false,
  code: "FRAME_TRANSITIONING",
  retryable: true
});
```

- [ ] **Step 2: escrever RED para ambiguidade**

Dois frames FORM com a mesma identidade:

```javascript
assert.equal(result.ok, false);
assert.equal(result.code, "FORM_AMBIGUOUS");
```

Nunca escolher o primeiro.

- [ ] **Step 3: manter `SCREEN_NOT_NAVIGABLE` somente para estado estrutural realmente desconhecido**

Não transformar todo erro em retryable.

- [ ] **Step 4: substituir polling cego por predicados estruturais comprovados**

Por exemplo:

```text
wait until:
- frame tree contém candidato;
- candidato tem rota esperada;
- snapshot estável;
- identidade esperada aparece;
```

Timeout permanece apenas como teto.

- [ ] **Step 5: executar suíte**

```powershell
Push-Location extension
node --test
Pop-Location
python -m unittest discover -s tests -p "test_*.py" -q
```

Expected: verde.

- [ ] **Step 6: commit por causa**

Não fazer “refactor portal router” gigante. Cada causa observada recebe teste e commit próprios.

---

### Task 11: Gate standalone — provar uso em outro PC sem IA

**Files:**
- Modify: `tests/test_packaging_contract.py`
- Modify: `packaging/verify-package.ps1` se necessário.
- Modify: `README.md`
- Modify: `docs/ESTRUTURA.md`

**Interfaces:**
- Input: `dist/Atos-TCE-portable.zip`.
- Output: prova de que o pacote não carrega nem exige ferramentas do laboratório.

- [ ] **Step 1: teste de conteúdo do ZIP**

Exigir ausência de prefixes/names:

```python
FORBIDDEN_DEV = (
    "devtools/",
    ".agents/",
    ".playwright-cli/",
    "node_modules/",
    "tmp/portal-lab/",
)
```

E ausência de nomes contendo:

```text
chrome-devtools-mcp
playwright-cli
SKILL.md
```

- [ ] **Step 2: smoke com PATH restrito**

No smoke do pacote, garantir que o `START.cmd` usa apenas runtime embarcado/suportado.

Não adicionar Node ao PATH do teste.

- [ ] **Step 3: build**

```powershell
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass `
  -File .\packaging\build-portable.ps1
```

- [ ] **Step 4: verificar**

```powershell
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass `
  -File .\packaging\verify-package.ps1 `
  -ZipPath .\dist\Atos-TCE-portable.zip
```

Expected: PASS.

- [ ] **Step 5: inspeção do ZIP**

Confirmar:

```text
app/          presente
extension/    presente
runtime/      presente
START.cmd     presente

devtools/     ausente
.agents/      ausente
node_modules/ ausente
tmp/          ausente
```

- [ ] **Step 6: documentação**

README deve declarar:

> Chrome DevTools MCP, Playwright CLI e Skills são ferramentas opcionais de desenvolvimento. O pacote portátil e o uso diário do Atos-TCE não dependem delas.

- [ ] **Step 7: commit**

```powershell
git add tests/test_packaging_contract.py packaging/verify-package.ps1 README.md docs/ESTRUTURA.md
git commit -m "test: prove portable runtime is agent independent"
```

---

### Task 12: Revisão adversarial final e handoff operacional

**Files:**
- Create: `docs/notes/2026-09-24-area-restrita-lab-handoff.md`
- No new runtime feature.

- [ ] **Step 1: revisão de segurança**

Procurar:

```powershell
git grep -n -I -E "ASPSESSION|Cookie|Authorization|cpf|CPF|playwright-cli|chrome-devtools-mcp" -- app extension packaging
```

Resultados de ferramentas dev em runtime devem ser zero.

- [ ] **Step 2: verificar arquivos privados**

```powershell
git status --short
git ls-files | Select-String -Pattern "tmp/portal-lab|\.har$|trace\.zip$|Cookies$|Login Data$"
```

Expected: nenhum artefato privado rastreado.

- [ ] **Step 3: suites**

```powershell
python -m unittest discover -s tests -p "test_*.py" -q

Push-Location extension
node --test
Pop-Location

powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass `
  -File .\packaging\verify-package.ps1 `
  -ZipPath .\dist\Atos-TCE-portable.zip
```

- [ ] **Step 4: revisão independente**

Usar fresh reviewer para procurar:

- seletor duplicado;
- timeout sem predicado estrutural;
- dados privados;
- dependência do laboratório no runtime;
- possibilidade de ação final;
- ambiguidade resolvida por “primeiro frame”.

- [ ] **Step 5: handoff**
Registrar:

- versão do portal contract;
- transições realmente observadas;
- problemas ainda desconhecidos;
- fixtures adicionadas;
- runtime alterado;
- hashes/gates do pacote;
- confirmação: “runtime standalone sem IA/MCP/Playwright”.

- [ ] **Step 6: commit**

```powershell
git add docs/notes/2026-09-24-area-restrita-lab-handoff.md
git commit -m "docs: close Area Restrita portal lab rollout"
```

---

## Ordem de execução

```text
Task 1  fronteira runtime/dev
  ↓
Task 2  Chrome dedicado/CDP
  ↓
Task 3  Chrome DevTools MCP
  ↓
Task 4  Playwright CLI
  ↓
Task 5  captura + sanitização
  ↓
Task 6  portal contract + fixtures
  ↓
Task 7  Skill do agente
  ↓
Task 8  observação real L0
  ↓
Task 9  transições L1/L2
  ↓
Task 10 correções do runtime guiadas por evidência
  ↓
Task 11 prova standalone
  ↓
Task 12 revisão e handoff
```

## Hard gates

### Gate A — antes de tocar o portal real

- testes de boundary verdes;
- Chrome dedicado;
- porta CDP loopback;
- sanitizador testado;
- política L0/L1/L2/L3 documentada.

### Gate B — antes de alterar runtime

- captura real sanitizada;
- contrato atualizado;
- fixture;
- teste RED reproduzindo a divergência.

### Gate C — antes de L2

- L0 e L1 estáveis;
- processo de teste selecionado;
- operador presente;
- ação final fora do protocolo;
- filler continua sem submit.

### Gate D — antes de considerar concluído

- suíte Python verde;
- suíte extensão verde;
- packaging verde;
- ZIP sem laboratório;
- smoke de extração limpa sem Node/MCP/Playwright;
- execução real supervisionada de preenchimento sem conclusão.

## Critério de parada

Se uma investigação revelar comportamento não compreendido, não adicionar heurística ampla.

Parar no último estado conhecido, salvar evidência privada, sanitizar, criar fixture e atualizar o contrato antes de continuar.

## Estratégia de execução recomendada

**Subagent-driven.**

Motivo: o plano toca segurança, navegador real, extensão e packaging. Cada tarefa possui uma fronteira suficientemente independente para revisão própria, e um erro de integração pode causar comportamento incorreto em um portal institucional autenticado.

A execução deve ocorrer em worktree/branch isolada. Tarefas 8–10 não devem ser paralelizadas porque compartilham estado da sessão do portal e conhecimento do contrato.