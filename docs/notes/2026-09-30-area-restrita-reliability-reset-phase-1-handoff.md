# Handoff — Área Restrita Reliability Reset, Phase 1

Data: 2026-09-30
Atualizado: 2026-10-02
Branch: `codex/area-restrita-reliability-reset`
AR1_BUILD atual (pacote offline verificado; nenhum run real ainda): `db73386f4d99a7ba713e605e9439f2dd90e28a74`
Builds anteriores: `5e9c277` → `4cd848a` → `af8c1f2` → `f1cf5b4` → `1d90b8d` → `e059793` (semântica antiga) → `c393353` (superseded; failed real validation) → `88bc4ad` (superseded) → `3b05f06` (intermediate provenance build, superseded) → **`db73386` (AR1_BUILD atual, somente offline qualificado)**. Não iniciar runs reais em builds anteriores.
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

Quando o operador decidir fazer a validação humana, executar a seção 7 (Task 5) usando exclusivamente o build `88bc4ad...` e o pacote da seção 14.1. A Mesa acompanha o formulário aberto; login e o clique em "Preencher dados encontrados" permanecem manuais. Nenhuma Task 6–10 pode começar, e nenhum plano de Phase 2 deve ser escrito antes do benchmark AR-2/AR-3.

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

### 13.4 Build anterior c393353 (histórico; superseded em 2026-10-02)

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

Este era o AR1_BUILD antes do primeiro teste humano. O relato do operador mostrou falha de detecção e estado `UNQUALIFIED`; não reutilizar esse ZIP. A build que o substitui está documentada na seção 14.1.

### 13.5 Roteiro histórico do primeiro run (superseded)

O primeiro run abaixo usava c393353 e falhou na validação humana; não repetir esse build. Para uma tentativa futura, seguir os mesmos limites manuais somente com o AR1_BUILD atual da seção 14.1.

```text
1. iniciar a Mesa com ATOS_TCE_BUILD_ID=88bc4adbb1bf9f0e2762a0cbd330adb88c351d26
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

Em 2026-10-01, `c393353` substituiu `e059793` como build de qualification. O teste humano subsequente invalidou c393353 para novos runs; em 2026-10-02, `88bc4ad` passou a ser o AR1_BUILD offline atual. Nenhuma capability foi promovida: a instalação limpa inicia com `manual_form_fill=EXPERIMENTAL`, streaks 0/20.


## 14. Follow-up offline: detecção de formulário e bootstrap AR-1 (2026-10-02)

O relato do primeiro teste humano da build `c3933536a2b60f73b2cee71542bec9740b8303dd` registra formulário visível não detectado e `manual_form_fill = UNQUALIFIED`; essa build fica SUPERSEDED / FAILED REAL VALIDATION para qualification. Neste Goal não houve novo acesso ao portal nem execução real.

Causas reproduzidas offline: (A) o detector anterior usava IDs globais e rádio marcado em todo o documento, contaminando a leitura por formulário antigo; (B) a ausência de manifesto de capability deixava uma instalação limpa em UNQUALIFIED. Os testes RED de DOM sintético e servidor local confirmaram os dois caminhos antes das correções.

Estado incremental: detector e resolução do interessado agora são escopados a candidatos estruturais visíveis e suas tabelas de interessados; ambiguidades de formulário são preservadas pelo router. O bootstrap aceita somente manifesto schema 1 com build_id correspondente e `manual_form_fill=EXPERIMENTAL`, executa uma vez sem substituir estado existente, e o builder só o inclui com opt-in explícito. O manifesto não cria runs nem chave HMAC. Há também um smoke sintético combinado do detector, heartbeat, API local e `FILL_FORM`/readback usando OLD oculto + CURRENT visível.

Review adversarial encontrou e ajudou a corrigir: bootstrap vinculado diretamente ao build do `package-manifest.json` mesmo quando `ATOS_TCE_BUILD_ID` diverge; seleção limitada à tabela visível única; validação estrita dos tipos JSON do manifesto; exclusão de formulário zero-size; e rádio condicionado à própria linha/tabela visível. Cada achado recebeu teste de regressão RED antes da correção. Também foi corrigido o alvo do `FILL_FORM` para resolver o controle dentro do formulário cuja identidade e geração foram lidas.

Validações da versão final: smoke integrado detector→heartbeat→API local→listener real `FILL_FORM`/readback passou; Node focado 73/73; `npm test --prefix extension` 254/254; `node --test app/web/tests/*.test.mjs` 65/65; `python -m unittest discover -s tests -p "test_*.py" -q` 837/837; bootstrap API 4/4; provenance rejeitou manifesto com tipos JSON incorretos; `git diff --check` limpo. `verify-project.ps1`: 1.260 verificações, 1.258 aprovações, zero falhas e dois skips. Review final sem achados críticos/importantes; o achado menor de callback `flatMap` recebeu RED→GREEN.

### 14.1 Build AR-1 anterior (`88bc4ad`; histórico, superseded por `db73386`) e instalação limpa

```text
Commit-fonte / AR1_BUILD: 88bc4adbb1bf9f0e2762a0cbd330adb88c351d26
Arquivo: dist/Atos-TCE-portable-clean.zip
Tamanho: 96.212.159 bytes
SHA-256: 1b8abc84d8322559856852e88ec6b55b8d2ff1764e9e73b748d80e1e0e71a770
Entradas: 526 (430 arquivos de runtime)
package-manifest.source_dirty: false
```

`verify-package.ps1 -ExpectedBuildId 88bc4ad... -RequireManualFormFillQualificationBootstrap` passou: 526 entradas, build e runtime com o SHA esperado, saúde `ok`, schema 7, zero processos e extensão 0.1.0. O smoke registrou aviso de acesso negado ao encerrar um processo temporário; a porta 58528 não ficou ouvindo, não havia processo com caminho do smoke e a pasta temporária foi removida.

Extraí o ZIP para um diretório temporário limpo e inicializei o servidor usando os módulos daquele ZIP. O ledger resultou em `manual_form_fill=EXPERIMENTAL`, streaks real/portable 0, demais capacidades `UNQUALIFIED`, sem `events.jsonl` nem `identity.key`. A auditoria dos nomes do ZIP encontrou zero entradas de `data`, acervo, PDFs, bancos, profiles, HAR, traces, logs, chave ou eventos. O manifesto presente é exatamente schema 1/build correspondente/`manual_form_fill=EXPERIMENTAL`. O sidecar `.sha256` confere com os bytes do ZIP.

O ZIP anterior foi preservado em `dist/archive/Atos-TCE-portable-clean-c393353-superseded.zip`, SHA-256 `fbb815d363783cb0f44c955760dd95e3c5cb42abd3aa12f62ed72181e9b4b7e8`.

### 14.2 GitHub e limite de validação

O commit-fonte `88bc4ad` contém código e testes verificados. No snapshot antes do fechamento documental, `codex/area-restrita-reliability-reset` estava um commit à frente de `origin`; o handoff final é um commit documental subsequente. Publicar sem force e conferir que `origin/codex/area-restrita-reliability-reset` corresponde ao HEAD final.

Nenhum portal, login, navegador ou formulário real foi aberto. Nenhum run AR-1 real foi criado. O bootstrap do ZIP só prepara a capacidade como `EXPERIMENTAL` 0/20 em instalação limpa; avaliação real continua humana e `Complementar Ato` continua manual.

## 15. Gate de provenance corrigido e build atual (2026-10-02)

O workflow `Offline gates (Windows)` do run `37007534493` falhou no `Root Python suite` (837 testes; 4 falhas), embora o ZIP `88bc4ad...` tivesse passado na verificação local anterior. A reprodução provou que `git hash-object --path=<arquivo> --stdin` aplica clean filters locais aos bytes do ZIP: um filtro externo que acrescenta BOM mudou o blob calculado para `LEIA-ME-OUTRO-PC.txt` de `5e98de6...` para `6fa4f53...` sem mudar o pacote.

Correção em `3b05f0639c9c17c0352cf7bf6dc54c8d08257845`: o verificador agora usa `git hash-object --stdin` sem `--path`, preservando a comparação com bytes brutos e mantendo o caminho fora dos argumentos de hashing. `START.cmd` foi commitado em CRLF byte a byte, com `/START.cmd -text whitespace=cr-at-eol`; antes, o ZIP tinha blob `dafcbdc...` e o commit `5a080db...`. Dois testes novos cobrem filtro externo e equivalência do launcher. A suíte focada de provenance passou **28/28**, depois dos RED reproduzirem as duas divergências.

### 15.1 AR1_BUILD e ZIP limpo

```text
AR1_BUILD: db73386f4d99a7ba713e605e9439f2dd90e28a74
Arquivo: dist/Atos-TCE-portable-clean.zip
Build id do package-manifest: db73386f4d99a7ba713e605e9439f2dd90e28a74
source_dirty: false
Entradas: 526
Arquivos de produto declarados: 94
Arquivos de runtime: 430
Tamanho: 96.212.161 bytes
SHA-256: c803f80c2ad989037570fd5464216af9b4241dba72043d585c2e3734aa197c38
Sidecar: dist/Atos-TCE-portable-clean.zip.sha256 (confere)
Provenance bruta independente: 0 divergências em 93 arquivos de commit; bootstrap validado separadamente
Bootstrap: schema 1, build correspondente, somente manual_form_fill=EXPERIMENTAL
Arquivos privados/proibidos: 0
```

O `verify-package.ps1 -ExpectedBuildId db73386... -RequireManualFormFillQualificationBootstrap` passou com smoke (`health=ok`, schema 7, zero processos, build/runtime id correspondente, extensão 0.1.0). O encerramento do processo temporário emitiu aviso de acesso negado; verificação posterior confirmou pasta de extração removida, porta 49306 fechada e nenhum processo do smoke remanescente. O ZIP contém `current_selection.py`, heartbeat e `portal-current.js`.

Os ZIPs anteriores `88bc4ad`, `e059793` e `3b05f06` foram preservados em `dist/archive/`, junto dos sidecars existentes. Para fazer o contrato local exercitar o pacote atual, `dist/Atos-TCE-portable.zip` é uma cópia byte idêntica do ZIP clean; seu SHA-256 e sidecar são iguais ao clean.

### 15.2 Gates locais e reliability

| Gate | Resultado |
|---|---|
| `python -m unittest discover -s tests -p "test_*.py" -q` | 839 testes, 839 passaram, 0 falharam |
| `npm test --prefix extension` | 254 testes, 254 passaram, 0 falharam |
| `node --test app/web/tests/*.test.mjs` | 65 testes, 65 passaram, 0 falharam |
| `work/tce-extractor/verify-project.ps1` | 1.260 executados, 1.258 aprovados, 0 falhas, 2 skips; 7/7 estágios verdes |
| `git diff --check` | limpo |

`python scripts/portal-reliability/capability-state.py --data-root data --capability manual_form_fill --experimental --build db73386f4d99a7ba713e605e9439f2dd90e28a74` passou. Estado atual: `EXPERIMENTAL`, real-dev `0/20`, portable `0/20`; `events.jsonl` não existia e nenhum histórico foi apagado. `identity.key` foi preservada.

### 15.3 GitHub e retomada

O run `37016795459` para `43deb18` falhou em `Root Python suite`; essa falha foi corrigida em `db73386`. O run seguinte `37019929274`, no SHA `85d912016c68d1933fc827d778f2b350c85dfdcf`, concluiu `SUCCESS`: Root Python 839/839, extensão 254/254, web 65/65, package contract 20/20 e whitespace PASS. O branch estava sincronizado e limpo após esse push. Esta atualização documental registra o resultado; seu push também dispara o workflow do novo HEAD, que deve ser acompanhado.

Nenhum portal, login, DevTools/Playwright no portal ou AR-1 real foi executado. `manual_form_fill` permanece `EXPERIMENTAL`; o primeiro run real segue aguardando o operador humano.

### 15.4 Follow-up do CI (2026-10-02)

O run remoto `37016795459`, commit `43deb18b247ffa8ef87a56e9b06597891b246e51`, ainda falhou em `Root Python suite`: 839 testes, 5 falhas, 4 skips; as cinco falhas reportaram o mesmo blob transformado `6fa4f53...` para `LEIA-ME-OUTRO-PC.txt`, e as etapas posteriores foram puladas. Isso ocorreu mesmo com `hash-object --stdin` sem `--path`; o comportamento só apareceu no runner GitHub/PowerShell, enquanto a mesma suíte local passou.

Para remover essa dependência ambiental, `Get-EntryBlobId` calcula diretamente SHA-1 de `blob <tamanho-em-bytes>\0 + bytes-do-ZIP` em .NET. A consulta do blob de referência continua via `git rev-parse`; nenhum processo Git recebe os bytes do pacote. Os quatro casos que falharam no CI passaram localmente e `python -m unittest tests.test_package_provenance -v` passou 28/28. Depois disso, todos os gates locais foram repetidos: Python 839/839, extensão 254/254, web 65/65 e `verify-project.ps1` 1.260 executados, 1.258 aprovados, 0 falhas e 2 skips. O ZIP `db73386` passou no verificador, smoke e auditoria byte a byte. O run remoto `37019929274` fechou os cinco passos em sucesso; sua suíte Python levou 253,554 s.

Retomada concluída: esta atualização foi commitada e enviada sem force. O CI do HEAD documental `c9d6e8594cc9b9e8ac4329ff5efe07732df48ece` concluiu com sucesso no run `37020907905`. O build `3b05f06` está superseded e arquivado. Nenhum AR-1 real foi repetido ou promovido.

## 16. Auditoria read-only do ZIP e do fluxo Portal Atual (2026-10-02)

### ZIP e sincronização

- Artefato atual: `dist/Atos-TCE-portable-clean.zip`, build `db73386f4d99a7ba713e605e9439f2dd90e28a74`, `source_dirty=false`, 526 entradas, 94 arquivos de produto e 430 de runtime.
- Tamanho: 96.212.161 bytes. SHA-256: `c803f80c2ad989037570fd5464216af9b4241dba72043d585c2e3734aa197c38`; sidecar conferido. O manifesto do ZIP e o build ID coincidem. A entrada `app/area_restrita/reliability.py` está no ZIP.
- O ZIP contém as mudanças de produto até `db73386`. O HEAD local/remoto está em `c9d6e8594cc9b9e8ac4329ff5efe07732df48ece`; os commits depois do build do ZIP são documentais, portanto não alteram os bytes de produto do pacote. CI do HEAD: run `37020907905`, `SUCCESS`.
- Estado Git antes deste registro: branch sincronizada, sem alterações; `git diff --check` limpo. Nenhum portal, login, DevTools/Playwright no portal ou AR-1 real foi usado.

### Verificações desta continuação

| Comando/gate | Resultado |
|---|---|
| `python -m unittest discover -s tests -p 'test_*.py' -q` | 839/839 aprovados |
| `npm test --prefix extension` | 254/254 aprovados |
| `node --test app/web/tests/*.test.mjs` | 65/65 aprovados |
| `verify-project.ps1` | 1.260 executados, 1.258 aprovados, 0 falhas, 2 skips; 7/7 estágios verdes |
| Suíte focada: reliability, current selection, fill service, package provenance, packaging contract e portal lab | 243/243 aprovados |
| Web focado: portal-current e app-boot | 21/21 aprovados; avisos existentes de `MODULE_TYPELESS_PACKAGE_JSON` |
| Extensão focada: router, reliability-state, portal-contract e fill-form | 128/128 aprovados |
| `git diff --check` | limpo |

### Achado P2: o ledger aceita promoção sem evidência de transição

`ReliabilityRecorder.start()` e `finish()` aceitam um run sem qualquer `transition`; `_runs()`/`_streak()` contam `run_finished.passed=true` sem exigir transição. A reprodução isolada em diretório temporário registrou 20 pares `start` + `finish(passed=True)`, recebeu `qualified=true` e promoveu `manual_form_fill` a `QUALIFIED`. Os testes existentes criam transição no helper comum e não cobrem esse caso. Código relevante: `app/area_restrita/reliability.py` (métodos `start`, `finish`, `_streak`, `_runs`); testes: `tests/test_area_restrita_reliability.py`.

Classificação: falha de integridade da evidência de qualificação, P2. A reprodução requer chamada local ao recorder e demonstra promoção indevida do estado do ledger. A revisão não encontrou uma rota HTTP de gravação arbitrária nem bypass de submit/envio real: o gate de envio da automação continua separado (`real_send_enabled`/`qualification.json`), e `Complementar Ato` permanece manual. O achado não foi corrigido nesta auditoria; o ZIP atual contém esse comportamento porque inclui `app/area_restrita/reliability.py`.

O ledger real permaneceu intacto: `manual_form_fill=EXPERIMENTAL`, real-dev `0/20`, portable `0/20`; `events.jsonl` ausente e `identity.key` preservada. A reprodução escreveu apenas no diretório temporário.

### Revisão independente complementar (2026-10-02)

- Um segundo revisor rastreou o achado do ledger até evaluate(), promote(), a CLI de qualificação e o relatório agregado: 20 pares locais start() + finish(passed=True) sem transições podem ser aceitos como qualificados. A revisão anterior o classificou P2; esta revisão o classificou P0 por permitir qualificação falsificada. Não há rubric de severidade no pedido e o caminho demonstrado é local/programático, sem rota HTTP de gravação arbitrária. A divergência P2/P0 fica registrada; por precaução, tratar como bloqueador de qualificação até corrigir e validar o ledger. O ZIP db73386 contém esse código.
- Revisão adicional encontrou P3 em extension/lib/protocol.js: isPortalUrl usa startsWith(PORTAL_ORIGIN) e aceita um host com o domínio legítimo apenas como prefixo. Não foi demonstrado caminho daí para escrita em formulário errado; corrigir com comparação de origin exata e teste para host-sufixo antes de uma próxima build.
- A suspeita de colisão entre /api/v1/portal/current-selection e /api/v1/portal/current-selection/fill não se confirmou: o dispatcher usa pattern.fullmatch(path).
- Nesta continuação não houve alteração de código, execução de testes pelo agente principal, acesso ao portal, AR-1 real ou promoção de capability. O revisor do ledger fez análise estática e não repetiu a reprodução; a reprodução isolada de 20 runs já está registrada acima. O ledger real segue inalterado.
- Estado do pacote confirmado nesta continuação: ZIP de 96.212.161 bytes, SHA-256 c803f80c2ad989037570fd5464216af9b4241dba72043d585c2e3734aa197c38, build db73386f4d99a7ba713e605e9439f2dd90e28a74. As diferenças entre esse build e o HEAD eram documentais; este registro também é documentation-only.

### Próximo passo bloqueante

Corrigir primeiro a integridade de evidência do ledger com teste RED/GREEN e revisar a classificação/ameaça do P0. Depois corrigir o teste de origem exata, executar os gates, reconstruir e verificar um novo ZIP. Não usar o ZIP atual para qualificação; manter manual_form_fill=EXPERIMENTAL e aguardar o operador para qualquer AR-1 real.

### Retomada

1. Corrigir o ledger com teste RED que exija ao menos uma transição válida antes de contar um sucesso; então rodar as suítes focadas e gates completos.
2. Regerar, verificar provenance e smoke do ZIP após a correção; atualizar SHA/build ID e handoff.
3. Não executar o primeiro AR-1 real, não promover capability manualmente e não iniciar AR-2/AR-3. `manual_form_fill` continua experimental até validação humana real.

## 17. Auditoria final independente (2026-10-02)

### Veredito

**NÃO PRONTO para o próximo teste humano AR-1.** Os gates offline e o ZIP físico passam, mas a auditoria encontrou um defeito de integridade no ledger (P0 pela definição de falsificação de qualification do pedido) e uma race P1 capaz de escrever em outro documento quando processo/interessado e geração reiniciada coincidem. Nenhum dos dois foi corrigido nesta auditoria. Não abrir o portal real, não iniciar AR-1, não promover capabilities e não iniciar AR-2/AR-3.

### Findings

1. **P0 — qualification pode ser falsificada sem transições.** `app/area_restrita/reliability.py:249-271,308-325,482-497,559-599`: o recorder aceita `run_start` seguido diretamente por `run_finished(passed=true)` e o avaliador conta esse run como sucesso sem validar boundaries de detecção, identidade, fill e readback. Reprodução anterior, isolada em diretório temporário: 20 pares `start`/`finish` sem transições produziram `qualified=true` e permitiram `promote()`. O helper normal dos testes sempre grava transições; falta o caso negativo. A reprodução usa a API local de código do recorder, sem rota HTTP de gravação arbitrária; ainda assim viola diretamente o critério P0 de evidência de qualificação do pedido. Revisões anteriores divergiram entre P2 e P0; adotar P0 até resolver com RED/GREEN. Ledger real não foi usado.
2. **P0 — o botão stale de A pode enfileirar fill para B.** `app/web/app.js:177-190,1012-1032` habilita o botão usando a observação/renderização atual, mas no clique envia `POST /api/v1/portal/current-selection/fill` com body vazio; `app/api/server.py:1139-1157` não recebe nem compara process_id/identity/generation esperados e `PortalSelectionTracker.fill_window()` reserva qualquer observação MATCHED corrente (`app/area_restrita/current_selection.py:176-195`). Reprodução HTTP inteiramente sintética pelo harness `PortalCurrentSelectionTests`: publicou A (`MATCHED`), publicou B (`MATCHED`) e simulou o clique atrasado da UI que ainda mostrava A; a rota respondeu 201, criou request para o process_id B e enfileirou `FILL_FORM` com seis campos propostos. O comando não foi entregue a navegador/extensão durante a auditoria. Portanto o cartão A pode disparar escrita no processo B sem bloqueio de identidade, porque o backend considera B a seleção autorizada. Isso satisfaz o critério P0 de poder preencher o processo errado. Falta teste que carregue expectativa A no clique e prove recusa depois de B. Antes de qualquer AR-1, enviar process_id/identity/generation ou token de observação e comparar atomicamente dentro da reserva; divergência deve recusar e contar a tentativa como falha.
3. **P1 — READ A / WRITE B ao mudar de documento mantendo a mesma identidade.** `extension/content/detect-form.js:228-232,344-352`, `extension/content/fill-form.js:32-38,121-145` e `extension/background/router.js:935-960`: identidade do form reader contém somente `processKey` e `interestedNormalized`; generation fica em `WeakMap` por `document` e recomeça em 1 no documento novo. A guarda de `findFieldControl`/`sameIdentity` compara identidade e geração, sem nonce estável de documento/formulário; `portalActId` não vem da observação do detector. Reprodução sintética com documentos A/B independentes, mesma identidade e generation 1: um plano produzido em A foi aceito por `applyFill` em B (`ok`, campo `changed`, uma escrita em B). A suíte cobre stale generation no mesmo documento e A→B com outro processo, mas não A→B em novo documento com identidade igual. Antes de AR-1, vincular o plano a um identificador não reutilizável de documento/formulário ou geração monotônica apropriada e adicionar teste RED para esse caso, incluindo readback.
4. **P1 — AR-2/AR-3 não estão bloqueados em todas as rotas.** O `manual_form_fill` permanece `EXPERIMENTAL`, mas a UI principal mostra “Preencher ato” em `PRONTO/PREENCHIDO` (`app/web/app.js:73,886-912`) e chama `POST /api/v1/processes/{id}/fill`; `FillService.request_fill()` valida só o status e enfileira `OPEN_ACT` (`app/area_restrita/fill_service.py:485-506`), cujo adapter pode abrir ato/selecionar interessado (`extension/content/navigate.js:113-146`). Também `POST /api/v1/portal/next-act` cria `OPEN_NEXT_ACT` sem conferir estado da capability (`app/api/server.py:1011-1061`); só os botões de UI “Próximo processo” estão desabilitados. `open_act` e `select_interested` existem como capabilities separadas, mas não são consultadas por esses caminhos. Há guardas de identidade exata, porém isso não equivale à qualification requerida; contradiz o critério do pedido de manter AR-2/AR-3 fechados. A spec do Portal Atual manda preservar o automatic `request_fill`, então há também conflito entre requisitos: resolver a intenção antes da próxima alteração. Não exercitar esses caminhos; propor bloqueio central por capability ou decisão explícita de escopo.
5. **P2 — dois perfis/extensões podem regredir o Portal atual.** O tracker guarda uma seleção global única (`app/area_restrita/current_selection.py:69-97,100-156`); cada worker serializa seu próprio `poll()`, mas publicação não tem publisher ID/sequence para ordenar observações entre perfis. O último POST pode substituir a observação mais nova por uma antiga. Identidades diferentes continuam falhando fechadas no fill, mas a Mesa pode exibir o processo errado; em identidade igual, os findings P0/P1 cobrem as escritas stale. Não há teste de dois publicadores. Mitigação: serialização/versão por instância e política explícita para perfil ativo, com teste de regressão.
6. **P2 — instruções operacionais contraditórias sobre a árvore de runtime.** `AGENTS.md:10,19,27` declara `work/tce-extractor` como fonte, enquanto `START.cmd`, builder e `docs/notes/2026-09-30-area-restrita-runtime-source.md:43-48` demonstram que as fontes de produção deste trabalho são `app/`, `extension/`, `tests/`, `packaging/` e `scripts/`; `work/tce-extractor` é verificador/legacy. Um agente pode aplicar uma correção na cópia que não é empacotada. Propor correção documental; não alterar instruções durante esta auditoria.
7. **P2 — handoff/plano contêm instruções ou estado antigo.** O topo do handoff e a seção 15.1 fixam corretamente `AR1_BUILD=db73386...`, mas a seção 7 ainda diz “Use sempre” `e059793...` e aponta um PID/runtime antigos (linhas 135-219). A seção 13.5 está explicitamente marcada como roteiro histórico/superseded, mas conserva comando com `88bc4ad`; ocorrências de `e059793`, `c393353`, `88bc4ad` e `3b05f06` nas seções históricas são cronologia, não builds atuais. O plano Portal Atual permanece com 99 checkboxes desmarcados e nenhum marcado, apesar da implementação registrada no handoff. Tornar o runbook antigo explicitamente não operacional e reconciliar o status do plano; não reutilizar instrução antiga.
8. **P3 — validação de host por prefixo.** `extension/lib/protocol.js:67-69`: `isPortalUrl()` usa `startsWith(PORTAL_ORIGIN)` e aceita URL cujo host apenas começa pelo host permitido. Manifesto e consultas de tabs limitam a injeção/enumeração, e não foi demonstrado caminho de escrita por esse caso; tratar como hardening de origin exata e adicionar teste de host-sufixo antes da próxima build.

Não foi encontrada rota ativa de submit/finalize, fuzzy match ou seleção first-match. O novo caminho Portal Atual não navega; porém o caminho legado `request_fill()` navega por `OPEN_ACT`, e o endpoint next-act também enfileira navegação sem gate de capability (finding P1 #3). A suspeita de colisão de rotas current-selection foi descartada: o dispatcher usa `pattern.fullmatch(path)`. Os mapas de campo sobrepostos entre detector e scanner servem a responsabilidades diferentes e não divergem nos IDs atuais; não classificados como bug. O botão do fill Portal Atual é desabilitado antes do primeiro `await`; isso protege o duplo clique normal nessa UI. O endpoint não implementa deduplicação de POST independente, aspecto sem teste de concorrência entre janelas.

Revisão independente read-only foi concluída antes da reprodução HTTP stale UI: concordou que o código não vincula geração/identidade ao documento e considerou plausível o stale write P1, mas não repetiu a reprodução. Ela não leu `evaluate()`/`_runs()` integralmente e deixou o ledger inconclusivo; este relatório mantém P0 com base na inspeção direta de `promote()` → `evaluate()` → `_streak()`/`_runs()` e na reprodução temporária de 20 runs sem transição. A revisão não encontrou evidência para elevar o caso cross-profile além de risco de regressão de seleção sem teste e não revisou os gates do `request_fill`/next-act nem a corrida UI A/B.

### Matriz resumida e races

| Requisito | Implementação e teste | Status |
|---|---|---|
| Manual best-effort independente do status; automático preserva gate; `mandatory_satisfied` separado de `best_effort_satisfied`; não inventar campos | `fill_service.py`; testes de status, campos vazios/parciais, preservação e resultados; suíte focada Python 351/351 | IMPLEMENTADO offline |
| Identidade exata, candidatos visíveis, zero/um/múltiplos, IDs duplicados, rádio/linha/tabela ocultos, roots antigos/estruturais, frames | `detect-form.js`, `area-snapshot.js`; testes sintéticos do DOM e router | IMPLEMENTADO nos cenários cobertos |
| Generation stale no mesmo documento, identidade/processo mudando, seleção TTL/clear, observação mínima e snapshot transitório | detector/filler, `current_selection.py`, API; testes Python/Node | IMPLEMENTADO nos cenários cobertos; **PARCIAL** para documento novo com identidade igual (P1) |
| Heartbeat 1500 ms, dedupe/keepalive 5000 ms, publicação com sidepanel fechado, único formulário | `router.js`/`heartbeat.js`; testes de router; serialização por worker | IMPLEMENTADO por worker; **PARCIAL** entre perfis (P2) |
| Follow default, pausa por seleção manual, retomar observação atual, não roubar subaba, fill só do MATCHED atual, cards/evidência/viewer compartilhado | `portal-current.js`, `app.js`, HTML; suites web 65/65 | IMPLEMENTADO offline |
| Bootstrap apenas experimental, build correspondente, sem criar runs | verifier/bootstrap e testes de contrato/API | IMPLEMENTADO; nenhum gate real inferido |
| AR-2/AR-3 bloqueados enquanto UNQUALIFIED | botão “Próximo processo” desabilitado, mas `request_fill` e endpoint next-act ainda iniciam navegação | **PARCIAL / P1 e conflito de requisitos** |
| Qualification 20/20 exige evidência real válida | evaluator e ledger atual; falta validar transições requeridas | **IMPLEMENTADO DIFERENTE DA SPEC / P0** |
| Clique Portal Atual permanece vinculado ao mesmo process_id/identity/generation que habilitou o botão | handler manda `{}`; backend preenche a seleção corrente | **NÃO IMPLEMENTADO / P0** |
| ZIP, allowlist, provenance byte-cru, smoke/health | `verify-package.ps1 -ExpectedBuildId db73386...` PASS; 93 blobs de produto comparados sem divergência e bootstrap separado validado | IMPLEMENTADO para o ZIP local |
| 20/20 real-dev + 20/20 portable; AR-1 humano | não executado por restrição do pedido | NÃO IMPLEMENTADO / gate humano pendente |

| Race | Resultado da auditoria |
|---|---|
| TTL expira antes do clique / backend MATCHED vence | Guard atômico; recusa sem fill e tenta registrar falha AR-1. Protegido offline. |
| A observado, B publicado, fill de A atrasado | Seleção é reservada até criar request; identidade diferente bloqueia no frame. Mesmo processo/interessado em documento novo é o P1 reproduzido. |
| UI mostra A, backend publica B antes do clique em A | O botão envia payload vazio e endpoint seleciona B corrente; harness sintético enfileirou `FILL_FORM` para B. P0. |
| Duas leituras/heartbeats no mesmo worker; observação velha termina depois | `poll()` serializado; teste de tick lento versus novo. Protegido nesse escopo. |
| Dois workers/perfis | Last-writer-wins sem sequência global. P2 residual. |
| Form desaparece durante o write | Resolução de frame atual pode recusar; contexto de navegação diferente é coberto pelo P1 se identity/generation reiniciarem iguais. |
| `processKey` muda sem generation mudar | Comparação exata da identidade bloqueia. Protegido. |
| generation muda sem `processKey` mudar no mesmo documento | Guard de generation bloqueia; novo documento pode reiniciar contador e é o P1. |
| Follow enquanto usuário escolhe subaba/processo | Pause/resume e preservação da subaba cobertos pela suite web. Protegido nos casos testados. |
| Duplo clique manual | UI desabilita botão síncronamente; repetição paralela/replay do endpoint não tem chave idempotente e não foi testada. |

### Gaps por camada e limites

- **Unit:** falta teste de runs sem transitions e teste cross-document same-identity; detector cobre ampla matriz de DOM sintético, sem estes dois casos.
- **Integration:** reprodução manual sintética pelo harness HTTP confirmou A→B stale-click, request de B e `FILL_FORM` com seis campos, mas a suíte não testa a expectativa identity/generation no endpoint; também faltam duas extensões/perfis publicando na mesma Mesa e dedupe/idempotência concorrente.
- **Browser synthetic:** smoke offline do detector→heartbeat→API→listener FILL_FORM/readback e repro sintética A/B; nenhum Chrome normal multiperfil foi usado.
- **Packaging:** o ZIP físico passa independentemente do CI. `93` arquivos de produto conferem com blobs Git crus; bootstrap schema/build/opt-in passou separadamente; divergências: `0`; arquivos privados: `0`.
- **CI:** o workflow valida código, suites e contrato do pacote, não o ZIP ignorado local. O HEAD `13895c3...` passou no run `37046508077`; o commit documental `a847ebb` passou no run `37056874351`; o commit documental `4b68116` passou no run `37057603833` (Root Python, Extension, Mesa web, Package contract e Whitespace). Nenhum desses workflows é verificação do ZIP físico; essa prova foi local.
- **Real-only:** zero execuções. O evaluator read-only retornou `streak=0`, sem build observado, para `real-dev` e `portable-normal-chrome`; capability persistida `EXPERIMENTAL`; `events.jsonl` não existe. Não afirmar PASS_REAL.

### Gates desta auditoria (read-only para produto)

| Comando | Resultado |
|---|---|
| `python -m unittest discover -s tests -p 'test_*.py' -q` | 839 executados, 839 passaram, 0 falharam |
| `npm test --prefix extension` | 254/254 passaram |
| `node --test app/web/tests/*.test.mjs` | 65/65 passaram; aviso não fatal `MODULE_TYPELESS_PACKAGE_JSON` |
| Suíte focada Python (current selection, fill service, API, reliability, provenance, packaging contract) | 351/351 passaram |
| Suíte focada de extensão (router, protocol, fill-form, portal contract) | 131/131 passaram |
| Suíte focada web (Portal Current e UI wiring) | 55/55 passaram |
| `work/tce-extractor/verify-project.ps1` | 7/7 estágios; 1.260 executados, 1.258 passaram, 0 falharam, 2 skips |
| Repro sintética stale UI A→B (harness HTTP, raiz temporária) | A e B publicados; clique que a UI ainda associa a A retornou 201, request/`FILL_FORM` para B com seis campos; sem navegador/portal |
| `git diff --check` | PASS antes deste adendo; repetir após edição |

Nenhum código de produto foi alterado. O ZIP continua sendo o produto até `db73386`; esta auditoria não autoriza usar o ZIP para qualification diante dos findings P0/P1. Próxima sequência: primeiro corrigir com RED/GREEN o vínculo do clique Portal Atual à observação A, a integridade das transições do ledger e o vínculo documento/generation; resolver a contradição de escopo e fechar AR-2/AR-3 por capability; depois cobrir perfis concorrentes e reconciliar documentação; rodar gates e CI; construir/verificar novo ZIP com SHA novo; só então aguardar autorização/ação humana para iniciar AR-1 real em 0/20. Continuam proibidos nesta tarefa: acesso real ao portal, teste AR-1, promoção, AR-2/AR-3 e merge em `main`.

## 18. Execução do Goal 02-10 (2026-10-02)

### Estado retomado

- Branch canônica sincronizada após `git fetch origin --prune` e `git pull --ff-only`: baseline `4146bfbf4327c208875da6635597e07a1e627264`; árvore inicialmente limpa.
- O objetivo deste Goal substitui o ZIP `db73386` para qualification. Nenhum novo `AR1_BUILD` ou ZIP foi criado ainda.
- A Área Restrita real não foi acessada; login, navegador do portal, AR-1, AR-2, AR-3 e promoção de capability não foram executados.

### P0 #1 — ledger de qualification: corrigido localmente

- RED confirmado antes da implementação: `python -m unittest tests.test_area_restrita_reliability.ReliabilityRecorderTestCase` executou 36 testes e falhou em 11 casos novos. O caso de 20 pares `run_start`/`run_finished(passed=true)` sem transições chegou a `qualified=true`; também passaram incorretamente casos com boundary ausente, fora de ordem/duplicado, identidade ou generation incompatível, falha intermediária e transição após terminal.
- A sequência aceita para `manual_form_fill` agora é validada pelo leitor do ledger: `current_form_detected → manual_fill_requested → preflight_completed → fill_command_completed → reread_completed`. O evaluator exige estados e códigos de sucesso esperados, identidade esperada/observada igual em todos os boundaries, generation contínua quando presente e ausência de boundaries extras ou após o terminal. Um terminal positivo sem essa estrutura vira falha para contagem e promoção.
- GREEN: `python -m unittest tests.test_area_restrita_reliability tests.test_api_server.PortalReliabilityRouteTests` — 60 testes, todos aprovados; `python -m unittest tests.test_fill_service.Ar1ManualFillReliabilityTests` — 25/25; `git diff --check` — PASS. O teste do endpoint prova que um ledger parcial com `passed=true` retorna streak 0. Os gates completos e CI ainda estão pendentes.
- Commits locais: `b3799ad test(reliability): require complete qualification evidence`; `68c116f fix(reliability): validate qualification transition sequence`. O handoff atual é este commit documental, ainda a registrar/push junto ao bloco.
- Arquivos de produto/teste tocados neste bloco: `app/area_restrita/reliability.py`, `tests/test_area_restrita_reliability.py`, `tests/test_api_server.py`.

### P0 #2 — clique stale A→B: corrigido localmente

- RED reproduzido antes da implementação: testes HTTP e tracker falharam porque o endpoint aceitava `{}` e reservava a observação corrente; o teste web também mostrou que o botão não exigia nem enviava expectativa da observação renderizada.
- Cada publicação `MATCHED` agora recebe `observation_id` opaco e aleatório, mantido somente em memória e exposto junto ao estado público mínimo. A Mesa captura `process.id` e o token imutáveis no handler do botão e envia o token no POST.
- Dentro do lock do tracker, o backend verifica TTL, estado, formato e igualdade do token, revalida process ID/identidade/portal act/generation/screen e mantém a reserva até a criação da request. A reserva consome o token e muda o estado para `FILL_RESERVED`; replay retorna 409 sem segunda request/comando. Clique stale de observação oferecida é registrado como falha AR-1.
- RED/GREEN HTTP permanente: publicar A, capturar A1, publicar B, clicar com A1 → 409 `STALE_SELECTION`, zero fill requests, zero comandos e um run AR-1 falho; B1 cria exatamente uma request `FILL_FORM` para B; replay de B1 retorna 409 sem duplicar request/comando. Cobertos também token ausente, inválido/desconhecido, geração alterada, TTL, estados sem formulário/ambíguos/inválidos e botão sem token.
- GREEN: `python -m unittest tests.test_current_selection tests.test_api_server.PortalCurrentSelectionTests` — 53 testes, todos passaram; `node --test app/web/tests/portal-current.test.mjs app/web/tests/ui-wiring.test.mjs` — 55/55; `git diff --check` — PASS. CI do P0 #1, run `37065390225`, concluiu SUCCESS em Root Python, Extension, Mesa web, Package contract e Whitespace.
- Commits: `a41ec50 test(portal): reproduce stale observation fill clicks`; `f6de126 fix(portal): bind fill clicks to exact observations`. Arquivos de produto: `app/area_restrita/current_selection.py`, `app/api/server.py`, `app/web/portal-current.js`, `app/web/app.js`; testes em `tests/test_current_selection.py`, `tests/test_api_server.py`, `app/web/tests/portal-current.test.mjs`, `app/web/tests/ui-wiring.test.mjs`.
- Ainda não houve gates globais, novo build/ZIP, provenance nem smoke final; o ZIP `db73386` continua superseded para qualification. Nenhuma Área Restrita real foi acessada.

### P1 #1 — plano vinculado ao documento/formulário: corrigido localmente

- RED reproduzido em testes de filler, router, detector, FillService e API: um plano de A podia escrever em B quando identidade e generation coincidiam; a resposta de sucesso não provava qual documento recebeu a escrita; o nonce também podia chegar a snapshots/resultados persistidos.
- O detector cria nonce criptográfico aleatório de 128 bits por objeto `Document`, guardado em `WeakMap`. Sem `crypto.getRandomValues`, não publica formulário. O filler exige nonce válido antes da primeira escrita, confere-o na resolução dos controles e interrompe o lote se o contexto mudar. O router escolhe somente o frame com identidade e nonce esperados; nonce diferente produz `STALE_FORM` sem envio do comando. A assinatura de seleção inclui nonce para republicar imediatamente numa troca de documento.
- A Mesa mantém o nonce somente em memória, associa-o ao ID do comando sob lock e injeta-o apenas na cópia entregue à extensão. Resultado `ok=true` precisa ecoar o nonce associado; resultado ausente, trocado ou recebido após reinício bloqueia como `STALE_FORM`. Snapshot intermediário, payload de comando, eventos de reliability e resultado SQLite removem o nonce. A resposta HTTP da extensão também não o devolve ao cliente.
- RED/GREEN: testes sintéticos provam 0 campos alterados no documento B, frame exato selecionado, republicação em nova instância e fail-closed após restart. `python -m unittest test_fill_service test_api_server` (com `PYTHONPATH=tests`) — 238 testes passaram na rodada do P1 #1; `npm test --prefix extension` — 260/260; `git diff --check` — PASS.
- Arquivos: `app/area_restrita/fill_service.py`, `app/api/server.py`, `extension/content/detect-form.js`, `extension/content/fill-form.js`, `extension/background/router.js` e respectivos testes em `tests/` e `extension/tests/`.

### P1 #2 — capability central para navegação AR-2/AR-3: corrigido localmente

- RED reproduzido: `request_fill()` criava pedido `OPEN_ACT` e `/portal/next-act` criava `OPEN_NEXT_ACT` mesmo com capabilities `UNQUALIFIED`/`EXPERIMENTAL`.
- `FillService.require_production_capabilities()` é o gate backend compartilhado e fail-closed. `request_fill()` verifica `open_act` e `select_interested` antes de criar pedido/comando. `/portal/next-act` verifica `next_process`, `return_to_list`, `open_act` e `select_interested` antes de resolver ou enfileirar navegação. Só estado `PRODUCTION` permite execução; `QUALIFIED` ainda bloqueia até que a arquitetura permita promoção.
- API responde HTTP 409 com `CAPABILITY_NOT_PRODUCTION`; os testes verificam zero fill requests, zero `OPEN_ACT` e zero `OPEN_NEXT_ACT`. Test fixtures que semeiam `PRODUCTION` são locais/sintéticos e não representam promotion ou evidência real.
- GREEN focado: serviço, rota next-act e cadeia de preenchimento com capabilities de produção passaram. `python -m unittest test_fill_service test_api_server` (com `PYTHONPATH=tests`) — 241/241; `npm test --prefix extension` — 260/260; Node nos testes de `app/web/tests` — 65/65; `git diff --check` — PASS. Uma tentativa inicial de `npm test --prefix app/web` falhou por não haver `package.json`; o comando Node correto para os arquivos web foi executado e passou.
- Arquivos adicionais: `app/area_restrita/fill_service.py`, `app/api/server.py`, `tests/test_fill_service.py`, `tests/test_api_server.py`.

### Estado ao retomar

- Branch `codex/area-restrita-reliability-reset`; último commit rastreado antes destes dois blocos: `e42f38c470168e4160ea1d781aff8917ced3e2fb`. Mudanças P1 #1/#2 estão no working tree; ainda sem commit/push.
- P1 #1 + P1 #2: implementação local concluída. A última suíte Python combinada contou 241 testes e passou; extensão 260/260; web 65/65; `git diff --check` PASS. Repetir o gate combinado após as próximas mudanças.
- O trabalho de capability preserva `request_fill(process_id)`, mas deixa a navegação bloqueada até `PRODUCTION`. O fluxo manual AR-1 continua independente e não recebeu capability de navegação.
- Nenhuma Área Restrita real foi acessada. Não houve login, preenchimento real, AR-1/AR-2/AR-3, promoção nem merge em `main`.
- P2/P3, revisão adversarial/global, reconciliação de `AGENTS.md`/runtime source-of-truth, gates/CI, congelamento de `NEW_AR1_BUILD`, ZIP novo, provenance e smoke sintético ainda pendentes. O ZIP anterior segue `SUPERSEDED FOR REAL QUALIFICATION`.

### Próxima etapa

Tratar P2 #1: concorrência entre publishers/perfis de `current_selection`, com publisher ID efêmero, sequência monotônica e rejeição de replay/stale sem regressão da seleção atual. Depois resolver a fonte de verdade contraditória (P2 #2), atualizar handoff/runbooks e o status superseded (P2 #3), corrigir origin exata (P3 #1), fazer revisão adversarial e os gates/CI/build/ZIP/provenance/smoke do Goal 02-10. Não usar portal real.
