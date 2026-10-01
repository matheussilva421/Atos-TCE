# Handoff — Área Restrita Reliability Reset, Phase 1

Data: 2026-09-30
Branch: `codex/area-restrita-reliability-reset`
AR1_BUILD (build congelado para a sequência AR-1): `c3933536a2b60f73b2cee71542bec9740b8303dd`
Builds congelados anteriores: `5e9c277` → `4cd848a` → `af8c1f2` → `f1cf5b4` → `1d90b8d` → `e059793` (substituído: a semântica de AR-1 mudou) → **`c393353` (AR1_BUILD em uso)**. Builds anteriores não devem ser usados para novos runs.
Base da reconciliação: `9fa3465` (`origin/codex/area-restrita-reliability-reset-spec`)

## 1. Reconciliação das branches

| Branch | SHA | Situação |
|---|---|---|
| `origin/main` | `cf89cd9` | ancestral do HEAD |
| `origin/codex/atos-tce-unified` | `397553f` | 18 commits à frente do main, 0 atrás; ancestral do HEAD |
| `origin/codex/area-restrita-reliability-reset-spec` | `9fa3465` | unified + 4 commits só de documentação (spec + plano) |
| `codex/area-restrita-reliability-reset` | HEAD | = spec + trabalho local preservado + Tasks 0–4 |

- O único trabalho local não commitado (`docs/notes/2026-09-28-v1.0.1-bugfix-handoff.md`) foi preservado em `47c2e18`.
- Nenhum commit relevante ficou para trás: os 4 commits da branch de spec são descendentes diretos da unified.
- `main` não foi tocada e não foi feito force push.

## 2. Runtime source-of-truth (Task 0)

Comprovado por entrada executável, não por documentação antiga:

```text
START.cmd               -> python -m app.main
packaging/build-portable.ps1 -> copia app/ + extension/ + START.cmd + README.md + LEIA-ME-OUTRO-PC.txt + scripts/scan-area-cdp.ps1
packaging/verify-package.ps1 -> valida o ZIP contra esse mesmo contrato
```

```text
Production source for Reliability Reset: root app/, extension/, tests/, packaging/, scripts/
work/tce-extractor: verifier/legacy compatibility tree for this goal
No dual implementation of the same fix
```

Nota: `docs/notes/2026-09-30-area-restrita-runtime-source.md`.

## 3. Baseline inicial (antes de qualquer mudança)

```text
python -m unittest discover -s tests -p "test_*.py" -q  -> 677 OK
npm test --prefix extension                             -> 208/208
node --test app/web/tests/*.test.mjs                     -> 33/33
work\tce-extractor\verify-project.ps1                   -> 1260 executados, 1258 pass, 0 fail, 2 skip
git diff --check                                         -> limpo
```

## 4. Tasks 0–4: concluídas (offline)

| Task | Commit | Conteúdo |
|---|---|---|
| 0 | `31645b4` | fonte de runtime travada + baseline verde |
| 1 | `d8fc257` | ledger de confiabilidade + avaliador de qualificação |
| 1 (fix de review) | `b0c043b` | gate de 20/20 não rebaixável, terminal único por run, códigos restritos |
| 2 | `a1dcf1e` | status de capability exposto + gating da UI |
| 3 | `7bdbcfc` | AR-1 independente de navegação + telemetria sanitizada |
| 2 (fix de review) | `f9b4315` | leitura pura não cria estado local |
| 4 | `3eca37e` | tooling de qualificação/relatório + fronteiras de pacote |
| 3 (fix de review) | `bf438f9` | snapshot sanitizado na criação, rota/refs/screen validados, membership de AR-1 durável |
| 4 (fix de review) | `b7a9f2f` | CLI só aceita ambientes reais; relatório colapsa códigos desconhecidos e valida `--build` |
| revisão final (fix) | `848ce38` | Mesa sem `Próximo processo` na Phase 1, recusa de AR-1 contada como falha, ledger com terminal único sob concorrência, bootstrap de `EXPERIMENTAL` |
| gate AR-1 (fix) | `3f1f1ef` | tentativa que falha na detecção também vira execução falha e zera a sequência |
| re-revisão (fix) | `dd46fd4` | terminal malformado não pode ser substituído por um duplicado válido; falha de detecção não alega `current_form_detected` |
| re-revisão 2 (fix) | `bf75503` | o leitor do relatório também fecha em falha: terminal duplicado é recusado e `passed` não-booleano conta como não comprovado |

### O que ficou implementado

- `app/area_restrita/reliability.py`: estados `UNQUALIFIED | EXPERIMENTAL | QUALIFIED | PRODUCTION`, ledger append-only sanitizado em `<data-root>/reliability/`, identidade só em HMAC-SHA256 local, promoção que recusa tudo abaixo de 20/20 no ambiente correto.
- `GET /api/v1/portal/reliability`: somente leitura, autenticado como extensão registrada, devolve apenas estado + streaks; não cria estado local.
- `extension/`: mensagem `RELIABILITY_STATUS`, rótulos `Indisponível — não qualificado | Experimental | Qualificado | Produção`, preenchimento manual gated pelo estado real e `Próximo processo` desabilitado na UI normal durante a Phase 1.
- AR-1: `FillService.request_manual_fill` nunca enfileira `OPEN_ACT`/`OPEN_NEXT_ACT`; a execução usa `run_id = manual-fill:<request_id>` e registra `current_form_detected → manual_fill_requested → preflight_completed → fill_command_completed → reread_completed → run_finished`.
- `scripts/portal-reliability/qualification.py`: leitor que sai 0 apenas com a sequência consecutiva válida no build pedido; nunca promove.
- `scripts/portal-reliability/report.py`: agrega tentativas/sucesso/falhas/intervenções, mediana, p95 e contagens de códigos; nunca copia identidade.
- Fronteira de pacote: `packaging/verify-package.ps1` passa a recusar `profiles/`, `tmp/portal-reliability/` e `scripts/portal-reliability/`.

## 5. Gates offline executados no HEAD congelado

Executados em `e059793a412f3fe4c8b403fb3a58cfa02e26553c` (AR1_BUILD), com árvore de trabalho limpa e igual a `origin/codex/area-restrita-reliability-reset`.

| Gate | Comando | Resultado |
|---|---|---|
| HEAD | `git rev-parse HEAD` | `e059793a412f3fe4c8b403fb3a58cfa02e26553c`, igual a `origin/...` |
| Python | `python -m unittest discover -s tests -p "test_*.py" -q` | 773 testes, OK (0 falhas) |
| extension | `npm test --prefix extension` | 225/225, 0 falhas |
| web | `node --test app/web/tests/*.test.mjs` | 34/34, 0 falhas |
| verify-project | `powershell -File .\work\tce-extractor\verify-project.ps1` | 1260 executados / 1258 pass / 0 fail / 2 skip, exit 0 |
| diff | `git diff --check` | limpo |

Revisões independentes por Task (subagentes isolados) foram executadas; os achados reproduzíveis foram corrigidos (ver seções 4 e 8).

Instabilidade honesta de um gate legado: na primeira execução desta sessão o estágio `automation` falhou em `work/tce-extractor/test_automation_browser.py::test_simulated_pages_frames_and_send_block` com `Page.evaluate: Could not establish connection. Receiving end does not exist`. A reexecução do estágio e a execução completa seguinte passaram (0 falhas). O teste é do harness Playwright legado, carrega `work/tce-extractor/portable/extensao-complementar-ato` (uma cópia separada da extensão, que este Goal não altera) e o erro é de prontidão do canal de mensagens, não de comportamento. Nenhuma mudança deste Goal toca aquela árvore. Se esse estágio voltar a falhar de forma reproduzível, é regressão e precisa ser investigado antes de qualquer promoção.

## 5b. Proveniência do pacote portátil (hardening)

O ZIP antigo em `dist/` podia estar funcionalmente desatualizado e ainda passar no verifier: ele ressuscitou o gate de falha de detecção e o guarda de terminal que já estavam corrigidos na fonte. O hardening fecha essa classe:

- o builder grava `package-manifest.json` com o SHA do Git e o sha256 de cada arquivo de produto copiado (schema 1, ordenação ordinal, bytes exatamente como entram no ZIP);
- o builder recusa release sem SHA resolvível e com árvore suja; `-AllowDirtySource` existe apenas para fixtures `-SkipRuntime`;
- o verifier exige o manifesto, valida schema/build_id/tamanhos/hashes/unicidade, recusa source fora do manifesto (inclusive com caixa ou `./` disfarçados e colisões de caixa) e recusa `source_dirty` em pacote com runtime embutido;
- para pacote de release, exige `-ExpectedBuildId` e confere cada arquivo declarado contra o blob do commit nomeado, então um manifesto reescrito não autentica bytes que o commit não tem;
- o runtime expõe `build_id` sanitizado em `GET /api/v1/health` e o smoke confere que o runtime extraído deriva o build do próprio manifesto, sem injeção de variável de ambiente.

| Fato | Valor |
|---|---|
| AR1_BUILD | `e059793a412f3fe4c8b403fb3a58cfa02e26553c` |
| ZIP | `dist/Atos-TCE-portable.zip`, 520 entradas, 96.186.074 bytes |
| SHA-256 do ZIP | `77bcc873b3fa4e9d3743f9fe5171336bfbf0de7bc5b1cd4a92b22ef72594897c` |
| schema do manifesto | 1 (88 arquivos de produto) |
| verificação `-ExpectedBuildId` + smoke | PASS; `health.build_id` = build do manifesto |
| probe portátil `FORM_NOT_AVAILABLE` | `{"recorded": true}`; ledger com `build_id` = AR1_BUILD, `environment` = portable-normal-chrome, `passed` = false |

Limite conhecido: o manifesto não é assinado. A comparação com o blob do commit nomeado protege contra pacote desatualizado, manifesto reescrito e arquivo não versionado, mas não substitui assinatura de release, que exigiria chave fora do escopo deste Goal.

## 6. Estado da execução real (AR-1)

Os gates offline passaram no HEAD congelado (seção 5) e `manual_form_fill` foi marcado `EXPERIMENTAL` nessa mesma build (seção 7, passo 0). A sequência real ainda não começou: ela exige o operador autenticado no portal.

```text
AR-1 real-dev 20/20 ......... AGUARDANDO O OPERADOR (preparado, streak 0)
AR-1 portable 20/20 ......... NÃO INICIADO (depende de QUALIFIED)
AR-1 QUALIFIED/PRODUCTION ... não promovida
AR-2 MV3 / Controller ....... NÃO INICIADO (hard gate: Task 6 só após AR-1 PRODUCTION)
AR-3 MV3 / Controller ....... NÃO INICIADO
arquitetura de navegação .... NÃO DECIDIDA
Phase 2 ..................... NÃO ESCRITO (depende da decisão arquitetural por evidência)
```

Semântica da contagem: **cada clique em `Preencher formulário atual` é uma tentativa**, mesmo quando nenhum formulário é detectado. Qualquer falha real zera a sequência; `19 PASS + 1 FAIL` não é 19/20, é `streak = 0`.

Login, seleção do marcador e o clique final **Complementar Ato** continuam humanos. Nenhum banco real foi alterado, nenhum estado real foi fabricado e nenhuma capability foi promovida.

## 7. Runbook para destravar a Task 5

Use sempre `AR1_BUILD = e059793a412f3fe4c8b403fb3a58cfa02e26553c` nos passos abaixo (`<HEAD>` nos comandos).

0. Em uma raiz de dados limpa a capability nasce `UNQUALIFIED`, então habilite o AR-1 para a sequência supervisionada (isso declara EXPERIMENTAL, não qualifica):

```powershell
python scripts/portal-reliability/capability-state.py --data-root data --capability manual_form_fill --experimental --build <HEAD>
```

1. Congelar o build (não alterar código durante a sequência):

```powershell
git rev-parse HEAD
git status --short
```

2. Iniciar o runtime de desenvolvimento e autenticar no portal manualmente (sem DevTools, sem correção técnica durante a sequência).

2b. Pré-condições antes do primeiro clique (conferir na ordem):

```text
1) o painel mostra "Mesa conectada" e "Área Restrita detectada"
2) o botão mostra "Preencher formulário atual — Experimental"
3) o contador está em runs = 0 / streak = 0 para o build congelado
4) o ato correto está aberto e com o interessado selecionado
```

Se qualquer item falhar, corrigir o ambiente antes de clicar. Um clique feito com a Mesa fora do ar **não pode ser registrado** (o ledger vive na Mesa), então ele não conta como tentativa e não zera a sequência: conferir o item 1 antes de cada clique é o que impede uma sequência "limpa" conviver com tentativas perdidas.

3. Para cada uma das 20 repetições: o operador abre manualmente o ato correto e o interessado e usa **Experimental — Preencher formulário atual**. O clique É a tentativa: se o painel não achar exatamente um formulário, a falha é registrada e a sequência reinicia. Não clicar em **Complementar Ato**.

3b. Conferir o resultado terminal de cada tentativa. O painel responde imediatamente com o estado do **pedido** (normalmente `FILLING`), o que não é o desfecho: o desfecho chega quando a extensão executa o `FILL_FORM` e reporta o resultado. Conferir no ledger (somente leitura):

```powershell
Get-Content data/reliability/events.jsonl -Tail 6 | Select-String 'run_finished'
```

Um `run_finished` com `"passed":true` é um sucesso contado; `"passed":false` zera a sequência e exige parada imediata. Se o painel disser que não há formulário, mas a linha "Mesa conectada" estiver ok, tratar como falha de detecção (registrada) e parar.

4. Avaliar a sequência (o build precisa bater com o gravado):

```powershell
python scripts/portal-reliability/qualification.py --data-root data --capability manual_form_fill --environment real-dev --required 20 --build <HEAD>
```

5. Se sair 0, promover (a própria API reavalia e recusa se o gate não estiver comprovado):

```powershell
python -c "from app.area_restrita.reliability import ReliabilityRecorder, CapabilityState as C; r=ReliabilityRecorder('data','<HEAD>'); r.promote('manual_form_fill', C.QUALIFIED, environment='real-dev', required=20, reason='20/20 real-dev <HEAD>'); print(r.capabilities()['manual_form_fill'])"
```

6. Artefato portátil + segunda amostra:

```powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\packaging\build-portable.ps1 -Force
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\packaging\verify-package.ps1
```

Extrair o ZIP em local limpo e iniciar pelo `START.cmd` com o ambiente de gravação correto, para que os runs caiam em `portable-normal-chrome`:

```powershell
$env:ATOS_TCE_RELIABILITY_ENVIRONMENT = 'portable-normal-chrome'
$env:ATOS_TCE_BUILD_ID = '<HEAD>'
# .\START.cmd
```

7. Repetir 20/20 no Chrome normal (sem Codex, sem MCP, sem DevTools, sem scripts de laboratório, sem edição manual de banco) e avaliar:

```powershell
python scripts/portal-reliability/qualification.py --data-root <portable-data-root> --capability manual_form_fill --environment portable-normal-chrome --required 20 --build <HEAD>
```

8. Promover para PRODUCTION com `environment='portable-normal-chrome'` e escrever `docs/notes/YYYY-MM-DD-area-restrita-ar1-qualification.md` com apenas: SHA do build, SHA-256 do pacote, 20/20 + 20/20, tempos agregados, códigos agregados, zero formulário errado, zero intervenção técnica e a confirmação de que a ação final seguiu manual.

9. Só então Tasks 6–10 do plano (controlador experimental, adapters de benchmark, AR-2/AR-3 e decisão arquitetural).

### Estado do ambiente preparado para o operador

- Mesa de desenvolvimento já em execução, fixada no build novo: PID `34924`, `127.0.0.1:18743`, data root `data`, `ATOS_TCE_RELIABILITY_ENVIRONMENT=real-dev`, `health.build_id = e059793a412f3fe4c8b403fb3a58cfa02e26553c`.
- `data/reliability/capabilities.json`: `manual_form_fill = EXPERIMENTAL` no build `e059793`; `real_dev_streak = 0`, `portable_streak = 0`.
- `data/reliability/events.jsonl`: nenhum evento (denominador limpo; nenhuma tentativa AR-1 registrada).
- ZIP congelado: `dist/Atos-TCE-portable.zip`, 520 entradas, 96.186.074 bytes, SHA-256 `77bcc873b3fa4e9d3743f9fe5171336bfbf0de7bc5b1cd4a92b22ef72594897c`, verificado com `-ExpectedBuildId e059793...` + smoke (`health.build_id` = build do manifesto).
- Commits: código `e059793a412f3fe4c8b403fb3a58cfa02e26553c` (AR1_BUILD); documentação `3634fba`, `adebf67`; teste `df2bbcc`. Nenhum deles toca os bytes de produto (`app/`, `extension/`, launchers, `scripts/scan-area-cdp.ps1`). `main` intacta, sem force push.
- Re-verificação depois dos commits de teste/documentação: `verify-package.ps1 -ZipPath .\dist\Atos-TCE-portable.zip -ExpectedBuildId e059793...` → PASS com smoke, `runtime_build_id = e059793...`. Como cada arquivo declarado é comparado com o blob do commit `e059793`, isso prova que o produto congelado continua sendo exatamente o do AR1_BUILD, mesmo com o HEAD já à frente em commits que não empacotam.
- Cobertura nova do caso "runtime reporta build diferente do manifesto": `tests/test_package_provenance.py` monta um runtime de mentira que responde `/api/v1/health` com outro build id e prova que o smoke recusa (`Runtime build_id = ...`).
- Uma instância antiga da Mesa fixada em `1d90b8d` foi encontrada ainda escutando na 18743 e precisou ser encerrada antes de subir a nova (no Windows dois sockets podem dividir a mesma porta). Se o painel voltar a mostrar o build antigo, conferir `health.build_id` antes de clicar.
- Falta apenas o que é humano: recarregar a extensão descompactada de `extension/`, conferir no painel "Mesa conectada" e "Preencher formulário atual — Experimental", abrir o ato e clicar uma vez por tentativa (seção 7).

## 8. Falhas encontradas e causas-raiz

- Revisão da Task 1: `promote()` aceitava `required` arbitrário (um `required=1` burlava o gate). Corrigido: promoção recusa qualquer valor abaixo de 20.
- Revisão da Task 1: `finish()` aceitava múltiplos eventos terminais, permitindo que uma falha virasse sucesso. Corrigido: terminal único, e o leitor do ledger recusa duplicata.
- Revisão da Task 1: texto livre era persistido em `result_code`/`boundary`/`kind`. Corrigido: apenas códigos `[A-Za-z0-9_-]{1,64}`; run/session ids opacos; `reason` limitada.
- Revisão da Task 2: a rota `GET` criava estado local na primeira leitura. Corrigido: raiz do ledger e chave HMAC só na primeira escrita.
- Achado próprio (Task 4): o guard de fronteira do produto reprovava o nome legítimo `handle_portal_reliability`; corrigido para checar apenas os caminhos de ferramenta.
- Achado próprio (Task 4): `/scripts/*` do `.gitignore` deixava `scripts/portal-reliability/*.py` fora do versionamento; allowlist adicionada.
- Revisão da Task 3: o snapshot bruto (com diagnostics não confiáveis) era persistido na criação do pedido antes da sanitização; um preflight que falhasse deixava query string e chave desconhecida no banco. Corrigido: a cópia persistida já sai sanitizada.
- Revisão da Task 3: `route` era apenas "sem query", aceitando `https://host/path`. Corrigido: `route` precisa ser um caminho `/...`; `screen` restrito ao vocabulário estrutural; `tab_ref`/`frame_ref` no formato sintético; `browser_session_id` opaco.
- Revisão da Task 3: a participação em AR-1 vivia só em memória, então um restart do serviço perdia o `run_finished`. Corrigido: a membership e a fase vêm do pedido persistido, e `has_finished()` evita terminal duplicado.
- Revisão da Task 4: a CLI aceitava `offline` e podia sair 0 com 20 execuções offline. Corrigido: só `real-dev` e `portable-normal-chrome` são aceitos.
- Revisão da Task 4: o relatório ecoava códigos do ledger e o filtro `--build` sem validação, podendo reproduzir identidade. Corrigido: código fora do vocabulário vira `OTHER` e `--build` é validado antes de aparecer na saída.

## 9. Limitações conhecidas

- O ambiente da execução é um rótulo gravado pelo runtime (`ATOS_TCE_RELIABILITY_ENVIRONMENT`), não algo não-forjável; um `real-dev` mal rotulado poderia, em tese, contar para o gate. É o modelo que o spec define e o ledger é local de operador único.
- O pacote portátil não inclui o controlador experimental durante a Phase 1 (garantido pelo builder e agora também pelo `verify-package.ps1`); `scripts/portal-reliability/` também fica fora do ZIP por desenho.
- `git diff --check` pega fim de linha; uma escrita via PowerShell com `WriteAllLines` já introduziu CRLF uma vez e foi corrigida.
- A sequência conta **toda** tentativa do operador. Como o plano deriva o `run_id` de uma tentativa que virou pedido (`manual-fill:<request_id>`), uma tentativa que nunca virou pedido — nenhum formulário, dois formulários visíveis, aba não autenticada, processo desconhecido — usa `manual-fill-attempt:<uuid>` e é gravada como execução falha, zerando a sequência do mesmo jeito. A extensão só reporta os códigos que honestamente observa antes de existir um pedido (FORM_NOT_AVAILABLE, FORM_AMBIGUOUS, PORTAL_TAB_NOT_ACTIVE).
- A UI da Mesa também deixou de oferecer `Próximo processo` durante a Phase 1; o endpoint continua existindo para o tooling supervisionado de benchmark (Task 7), como o plano prevê.
- Revisão adversarial do hardening: colisão de caixa em nome de entrada do ZIP escapava da cobertura (hashtable do PowerShell é case-insensitive e o predicado era case-sensitive) e ainda podia sobrescrever código na extração. Corrigido: nome canônico com minúsculas, remoção de `./`, recusa de duplicata/variação de caixa e cobertura sobre a lista completa de entradas.
- Revisão adversarial do hardening: o smoke injetava o build id esperado em `ATOS_TCE_BUILD_ID` e comparava o health com o próprio valor injetado, o que era tautológico. Corrigido: o smoke limpa a variável e exige que o runtime extraído derive o build do manifesto empacotado (que passou a ter precedência sobre um checkout acima da extração).
- Revisão adversarial do hardening: um manifesto reescrito dentro do ZIP autenticava bytes modificados e arquivos ignorados/não versionados entravam com identidade limpa. Corrigido: pacote de release exige `-ExpectedBuildId`, o commit precisa existir localmente e cada arquivo declarado precisa estar no commit com o mesmo blob git dos bytes do ZIP.
- Revisão adversarial do hardening: `-ExpectedBuildId` era opcional, então um release antigo e autoconsistente passava. Corrigido: obrigatório para pacote com runtime embutido.
- Re-revisão do hardening: a forma de release era inferida só da presença de `runtime-manifest.json`, então um ZIP podia carregar `runtime/` sem o manifesto e escapar de `-ExpectedBuildId` e da comparação de commit. Corrigido: árvore `runtime/` sem manifesto é artefato irregular e qualquer árvore `runtime/` torna o pacote release-shaped.
- Re-revisão do hardening: a cobertura só olhava `app/`, `extension/` e quatro arquivos nomeados, então um source extra fora dessas raízes passava. Corrigido: todo arquivo fora do contrato do runtime (`runtime/**`, `licenses/**`, `runtime-manifest.json`, `package-manifest.json`) precisa estar declarado no manifesto.
- Re-revisão do hardening (introduzido por mim): o caminho declarado era interpolado sem escape em `cmd.exe /c`, permitindo execução de comando durante a verificação. Corrigido: os bytes empacotados são lidos do próprio ZIP e enviados ao stdin do git sem shell, e caminho com aspas é recusado.
- Re-revisão do hardening: a detecção de duplicata não normalizava `./` nem `//`. Corrigido: nome canônico compartilhado entre duplicata e cobertura.
- Um clique feito com a Mesa fora do ar não gera evento, porque o ledger vive na Mesa: por construção, nenhuma tentativa é registrada quando o serviço de registro está indisponível. O runbook exige conferir "Mesa conectada" e `runs = 0` antes de começar, e o painel mostra a linha da Mesa separadamente do resultado do preenchimento.
- Terceira revisão adversarial do hardening: um ZIP podia disfarçar a árvore de runtime (`./runtime/...`, `RUNTIME/...`, `runtime//...`) e escapar da detecção de release-shape, que testava o nome bruto contra `runtime/` sem canonicalizar nem baixar a caixa. Corrigido: o nome de cada entrada é canonicalizado uma única vez e a árvore `runtime/` é detectada sobre a forma minúscula; qualquer `runtime/` sem manifesto é artefato irregular (commit `e059793`).
- Terceira revisão adversarial do hardening: `licenses/<algo>` sem `runtime-manifest.json` era tratado como pertencente ao runtime e podia ficar fora do `package-manifest.json`. Corrigido: a isenção de `runtime/**` e `licenses/**` só vale quando o contrato de runtime está presente; sem ele, esses arquivos são source de produto e precisam ser declarados. O builder acompanha: em build `-SkipRuntime` (fixture de contrato, sem runtime) ele passa a declarar as licenças no manifesto.
- Terceira revisão adversarial do hardening: uma entrada de ZIP como `///` normalizava para vazio e era silenciosamente ignorada, driblando a cobertura. Corrigido: nome bruto não vazio que canonicaliza para vazio é recusado como entrada irregular.
- Cobertura de regressão do hardening acima: quatro testes novos em `tests/test_package_provenance.py` (alias de runtime, licença não declarada, licença declarada aceita, nome que normaliza para vazio) mantêm o pacote real e a fixture de contrato verdes.

## 10. Confirmação de segurança

```text
identity fail-closed ......... preservado
ambiguity fail-closed ........ preservado
generation fail-closed ....... preservado
select catalog validation .... preservado
session-expiry detection ..... preservado
access-denied terminal ....... preservado
Complementar Ato ............. manual, nunca automatizado
SUBMIT/SEND/AUTO_SUBMIT ...... inexistentes no protocolo
dados pessoais em artefatos .. nenhum
```

## 11. Próximo passo

Executar a seção 7 (Task 5) com o operador no portal, agora pelo fluxo **Portal atual** descrito na seção 13.5: a Mesa acompanha o formulário aberto e o operador clica uma única vez em "Preencher dados encontrados". Enquanto isso, nenhuma Task 6–10 pode começar, e nenhum plano de Phase 2 deve ser escrito: a Phase 2 depende da decisão arquitetural que só o benchmark AR-2/AR-3 pode produzir.

## 12. ZIP portátil limpo para uso em outro PC

Gerado com o builder oficial a partir de um checkout temporário limpo no commit congelado `e059793`. Usei um clone local na pasta temporária do sistema em vez de `git worktree add` porque o `.git` do repositório é somente leitura neste ambiente e o git não consegue registrar em `.git/worktrees`; o HEAD do clone foi destacado em `e059793`, então o `build_id` saiu correto. O destino foi escrito direto em `dist/` do repositório principal para o artefato sobreviver à limpeza do checkout temporário. Nenhum commit de código, nenhuma mudança de branch, `main` intacta.

| Fato | Valor |
|---|---|
| Arquivo | `dist/Atos-TCE-portable-clean.zip` |
| build_id (AR1_BUILD) | `e059793a412f3fe4c8b403fb3a58cfa02e26553c` |
| Entradas | 520 |
| Tamanho | 96.186.074 bytes |
| SHA-256 | `350b84abfa3b6686527325c65871cf58ce0061e4b08378a4170b500b7b163a51` |
| `verify-package.ps1 -ExpectedBuildId e059793...` | PASS |
| Smoke (`health.build_id`) | `e059793a412f3fe4c8b403fb3a58cfa02e26553c` |
| `package-manifest.json` | schema 1, `source_dirty = false`, 88 arquivos |
| `runtime-manifest.json` | 430 arquivos |
| Conteúdo vs `Atos-TCE-portable.zip` | 520/520 entradas com bytes idênticos; só os timestamps do ZIP diferem (por isso o SHA-256 do arquivo difere) |
| Instalação limpa em raiz descartável | PASS: nada pré-existente, `health = ok`, `schema_version = 7`, `process_count = 0`, data root e banco criados no primeiro START |
| Acervo/processos no pacote | NÃO: nenhuma entrada `data/`, `acervo-tce/`, `dados-locais/`, `*.db`, `*.pdf`, profile, cookie ou token |
| Extensão | `RELIABILITY_STATUS`, `REPORT_AR1_ATTEMPT` e `/api/v1/portal/manual-form-attempt` presentes; rótulo `Preencher formulário atual — Experimental` composto em `extension/sidepanel/panel.js` |
| Ledger real AR-1 | intacto: sem eventos em `data/reliability/`, `manual_form_fill = EXPERIMENTAL`, streaks 0 |
| Limpeza | checkout temporário removido (~278 MB), 0 extrações e 0 processos residuais |

`app/archive/*.py` no pacote é o pacote Python da própria aplicação (3 arquivos versionados em `e059793`), não acervo de processos. Scripts de auditoria reexecutáveis: `tmp/audit_clean_zip.py` e `tmp/clean_install_check.py`.


## 13. Portal Atual + preenchimento manual best-effort (2026-10-01)

Spec e plano autoritativos: `docs/superpowers/specs/2026-10-01-portal-atual-best-effort-design.md` e `docs/superpowers/plans/2026-10-01-portal-atual-best-effort.md`. As 8 Tasks do plano foram executadas com TDD (RED → correção mínima → GREEN), com revisão independente por Task e um review final adversarial da branch inteira.

### 13.1 O que mudou

- `request_manual_fill()` deixou de exigir `PRONTO`/`PREENCHIDO`: a autorização passa a vir do formulário observado. `request_fill(process_id)` continua exatamente como antes (constante renomeada para `AUTOMATIC_FILLABLE_PROCESS_STATUSES`).
- `mandatory_satisfied` (completude documental — ainda a única que promove `process.status → PREENCHIDO`) ficou separada de `best_effort_satisfied` (todos os campos de `plan.fields` escritos/preservados e relidos conforme a proposta autorizada). O AR-1 passa a usar `BEST_EFFORT_OK`/`BEST_EFFORT_FAILED`; plano vazio pode passar, porque a decisão correta foi não inventar valor.
- `app/area_restrita/current_selection.py` (novo): tracker **somente em memória**, TTL de 10 s, resolução exata via `Store.resolve_process_identity()`, snapshot privado nunca gravado em SQLite/log/telemetria e nunca ecoado no GET público.
- Três rotas novas: `GET /api/v1/portal/current-selection` (sessão da Mesa), `POST /api/v1/portal/current-selection` (token da extensão) e `POST /api/v1/portal/current-selection/fill` (sessão da Mesa). Nenhuma cria `OPEN_ACT`/`OPEN_NEXT_ACT`.
- Heartbeat da extensão publica o formulário aberto mesmo com o sidepanel fechado; observação idêntica é deduplicada e renovada a cada 5000 ms; troca A→B é publicada imediatamente.
- Mesa: aba **Portal atual**, acompanhamento com Pausar/Retomar, layout PDF/evidência à esquerda e ficha à direita (uma coluna em tela estreita), ações Copiar valor e Ver evidência reutilizando o viewer existente, e o botão **Preencher dados encontrados** usando exclusivamente a rota transitória.
- Um poll repetido do mesmo processo nunca rouba a subaba escolhida pelo operador; só a mudança de processo observado ou o Retomar explícito abrem Portal atual.
- Nenhum `SUBMIT`/`SEND`/`AUTO_SUBMIT`/`COMPLEMENT_ACT`/`FINALIZE` foi introduzido; `Complementar Ato` continua manual.

### 13.2 Achados de review corrigidos

- **Bloqueador**: `request_manual_fill()` persistia o snapshot bruto da observação em `fill_requests.form_snapshot`. Agora apenas os diagnósticos sanitizados são persistidos antes do plano.
- **Bloqueador** (review final): uma declaração duplicada de `selectProcess` aninhava `init()` e a Mesa simplesmente não inicializava (`ReferenceError: init is not defined`). Corrigido, e agora existe `app/web/tests/app-boot.test.mjs`, que importa o shell real contra um DOM mínimo — os testes de texto não detectavam isso.
- A reserva da seleção para o fill é atômica (`PortalSelectionTracker.fill_window()`): nem uma observação mais nova nem o TTL podem substituir a seleção entre o clique e a criação da fill request.
- `Retomar acompanhamento` volta apenas ao formulário que o portal está mostrando agora (`resumeAction`), nunca a um id expirado.
- Um valor que a análise não confirmou não é mais rotulado ENCONTRADO nos cards (o card e a contagem do cabeçalho agora concordam).
- `{"active": false}` com código fora dos três permitidos é recusado com 400 e não apaga uma seleção válida.
- O preenchimento só conta uma tentativa AR-1 quando a Mesa poderia realmente ter mostrado o botão (atributo `offered`), e a decisão é atômica com a recusa.
- Um campo presente em `plan.fields` cuja proposta não seja o valor autorizado pelo plano agora falha o AR-1.

### 13.3 Gates (contagens reais desta build)

| Gate | Resultado |
|---|---|
| `python -m unittest discover -s tests -p "test_*.py" -q` | 829 testes, 0 falhas |
| `npm test --prefix extension` | 236 testes, 0 falhas |
| `node --test app/web/tests/*.test.mjs` | 65 testes, 0 falhas |
| `work/tce-extractor/verify-project.ps1` | 7/7 estágios, 1260 executados, 1258 passaram, 0 falhas, 2 skips |
| `git diff --check` | limpo |

Os cinco Review Focus têm teste explícito: TTL expirado antes do clique; A→B durante o write; heartbeat duplicado/concorrente; follow não rouba a navegação manual; processo sem campos úteis em estado excepcional.

### 13.4 Novo AR1_BUILD e ZIP limpo

```text
AR1_BUILD: c3933536a2b60f73b2cee71542bec9740b8303dd
Árvore: limpa no momento do congelamento
```

| Fato | Valor |
|---|---|
| Arquivo | `dist/Atos-TCE-portable-clean.zip` |
| Entradas | 524 |
| Tamanho | 96.205.704 bytes |
| SHA-256 | `fbb815d363783cb0f44c955760dd95e3c5cb42abd3aa12f62ed72181e9b4b7e8` |
| `verify-package.ps1 -ExpectedBuildId c393353…` | PASS |
| `package-manifest.json` / `health.build_id` / `runtime_build_id` | todos `c3933536a2b60f73b2cee71542bec9740b8303dd` |
| Instalação limpa | PASS: `health = ok`, `schema_version = 7`, `process_count = 0`, extensão 0.1.0 |
| Acervo no pacote | NÃO: nenhuma entrada `data/`, `acervo-tce/`, `dados-locais/`, `*.db`, profile, cookie, HAR ou trace |
| Smoke do artefato | PASS: 15/15 `PortalCurrentSelectionTests` contra o código extraído do próprio ZIP (NO_ACTIVE_FORM → MATCHED → GET mínimo → current-selection/fill → TTL/clear) |
| Ledger real | histórico preservado; `manual_form_fill = EXPERIMENTAL`, `real_dev_streak = 0`, `portable_streak = 0` |

O ZIP foi construído a partir da árvore limpa em `c393353`. O commit final deste handoff é **docs-only** e deixa a branch à frente desse SHA: os **bytes do pacote correspondem a `c393353`**, não ao topo da branch.

### 13.5 Primeiro run real (ação do operador)

```text
1. iniciar a Mesa com ATOS_TCE_BUILD_ID=c3933536a2b60f73b2cee71542bec9740b8303dd
   e ATOS_TCE_RELIABILITY_ENVIRONMENT=real-dev
2. recarregar a extensão
3. abrir um formulário real na Área Restrita
4. confirmar que a Mesa acompanha automaticamente o processo correto
5. clicar UMA vez em "Preencher dados encontrados"
6. inspecionar um único run_finished
```

Se `passed:true`, a sequência passa a 1/20. Se `passed:false` ou não houver terminal, parar e usar `superpowers:systematic-debugging`.

**Nenhum run real foi executado por este Goal.** `Complementar Ato` permanece manual. AR-2, AR-3 e Tasks 6–10 continuam fechados até AR-1 atingir `PRODUCTION` na nova semântica.

### 13.6 Limitação conhecida

A observação não carrega número de sequência — o contrato congelado é `{active, form}` / `{active, code}`. Dentro de um worker o `poll()` é serializado, então uma publicação antiga nunca chega depois de uma mais nova; com dois publicadores independentes (por exemplo dois perfis de Chrome com a extensão) a última publicação vence, ainda que seja a mais antiga. A identidade continua exata e o AR-1 revalida identidade/geração antes de qualquer escrita.

Este Goal reescreveu o produto e substituiu o AR1_BUILD: a build `e059793` fica aposentada e `c393353` passa a ser a build de qualification. Nenhuma capability foi promovida — `manual_form_fill` segue EXPERIMENTAL em 0/20.

