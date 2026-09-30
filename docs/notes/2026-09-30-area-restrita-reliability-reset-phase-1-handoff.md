# Handoff — Área Restrita Reliability Reset, Phase 1

Data: 2026-09-30
Branch: `codex/area-restrita-reliability-reset`
HEAD: `3eca37e` (ver abaixo as atualizações de revisão)
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

### O que ficou implementado

- `app/area_restrita/reliability.py`: estados `UNQUALIFIED | EXPERIMENTAL | QUALIFIED | PRODUCTION`, ledger append-only sanitizado em `<data-root>/reliability/`, identidade só em HMAC-SHA256 local, promoção que recusa tudo abaixo de 20/20 no ambiente correto.
- `GET /api/v1/portal/reliability`: somente leitura, autenticado como extensão registrada, devolve apenas estado + streaks; não cria estado local.
- `extension/`: mensagem `RELIABILITY_STATUS`, rótulos `Indisponível — não qualificado | Experimental | Qualificado | Produção`, preenchimento manual gated pelo estado real e `Próximo processo` desabilitado na UI normal durante a Phase 1.
- AR-1: `FillService.request_manual_fill` nunca enfileira `OPEN_ACT`/`OPEN_NEXT_ACT`; a execução usa `run_id = manual-fill:<request_id>` e registra `current_form_detected → manual_fill_requested → preflight_completed → fill_command_completed → reread_completed → run_finished`.
- `scripts/portal-reliability/qualification.py`: leitor que sai 0 apenas com a sequência consecutiva válida no build pedido; nunca promove.
- `scripts/portal-reliability/report.py`: agrega tentativas/sucesso/falhas/intervenções, mediana, p95 e contagens de códigos; nunca copia identidade.
- Fronteira de pacote: `packaging/verify-package.ps1` passa a recusar `profiles/`, `tmp/portal-reliability/` e `scripts/portal-reliability/`.

## 5. Testes executados (estado atual, HEAD `3eca37e`)

```text
python -m unittest discover -s tests -p "test_*.py" -q  -> 719 OK
npm test --prefix extension                             -> 221/221
node --test app/web/tests/*.test.mjs                     -> 33/33
work\tce-extractor\verify-project.ps1                   -> 1260 executados, 1258 pass, 0 fail, 2 skip
git diff --check                                         -> limpo
```

Revisões independentes por Task (subagentes isolados) foram executadas; os achados reproduzíveis foram corrigidos (ver seções 4 e 8).

## 6. Blocker atual — Task 5 não executada

A Task 5 exige **qualificação real**: 20/20 consecutivos em `real-dev` e depois 20/20 no portátil/Chrome normal, com o operador abrindo manualmente o ato correto no portal autenticado.

```text
AR-1 real-dev 20/20 ......... NÃO EXECUTADO (requer operador + login no portal)
AR-1 portable 20/20 ......... NÃO EXECUTADO
AR-1 QUALIFIED/PRODUCTION ... não promovida
AR-2 MV3 / Controller ....... NÃO INICIADO (hard gate: Task 6 só após AR-1 PRODUCTION)
AR-3 MV3 / Controller ....... NÃO INICIADO
arquitetura de navegação .... NÃO DECIDIDA
Phase 2 ..................... NÃO ESCRITO (depende da decisão arquitetural por evidência)
```

Login, seleção do marcador e o clique final **Complementar Ato** continuam humanos. Nenhum banco real foi alterado, nenhum estado real foi fabricado e nenhuma capability foi promovida.

Estado local de capability (`data/reliability/capabilities.json`): `manual_form_fill = EXPERIMENTAL` (streaks 0/0), marcado quando o contrato offline AR-1 ficou verde, com o SHA do build na razão. Isso **não** é qualificação.

## 7. Runbook para destravar a Task 5

1. Congelar o build (não alterar código durante a sequência):

```powershell
git rev-parse HEAD
git status --short
```

2. Iniciar o runtime de desenvolvimento e autenticar no portal manualmente (sem DevTools, sem correção técnica durante a sequência).

3. Para cada uma das 20 repetições: o operador abre manualmente o ato correto e o interessado; o painel deve detectar exatamente um formulário; usar **Experimental — Preencher formulário atual**; esperar o resultado terminal; conferir identidade e releitura na Mesa. Não clicar em **Complementar Ato**.

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

## 8. Falhas encontradas e causas-raiz

- Revisão da Task 1: `promote()` aceitava `required` arbitrário (um `required=1` burlava o gate). Corrigido: promoção recusa qualquer valor abaixo de 20.
- Revisão da Task 1: `finish()` aceitava múltiplos eventos terminais, permitindo que uma falha virasse sucesso. Corrigido: terminal único, e o leitor do ledger recusa duplicata.
- Revisão da Task 1: texto livre era persistido em `result_code`/`boundary`/`kind`. Corrigido: apenas códigos `[A-Za-z0-9_-]{1,64}`; run/session ids opacos; `reason` limitada.
- Revisão da Task 2: a rota `GET` criava estado local na primeira leitura. Corrigido: raiz do ledger e chave HMAC só na primeira escrita.
- Achado próprio (Task 4): o guard de fronteira do produto reprovava o nome legítimo `handle_portal_reliability`; corrigido para checar apenas os caminhos de ferramenta.
- Achado próprio (Task 4): `/scripts/*` do `.gitignore` deixava `scripts/portal-reliability/*.py` fora do versionamento; allowlist adicionada.

## 9. Limitações conhecidas

- O ambiente da execução é um rótulo gravado pelo runtime (`ATOS_TCE_RELIABILITY_ENVIRONMENT`), não algo não-forjável; um `real-dev` mal rotulado poderia, em tese, contar para o gate. É o modelo que o spec define e o ledger é local de operador único.
- `docker`/`zip` não participam; o pacote portátil NÃO deve incluir o controlador experimental durante a Phase 1 (garantido pelo builder e agora também pelo verifier).
- `git diff --check` pega fim de linha; uma escrita via PowerShell com `WriteAllLines` já introduziu CRLF uma vez e foi corrigida.

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

Executar a seção 7 (Task 5) com o operador no portal. Enquanto isso, nenhuma Task 6–10 pode começar, e nenhum plano de Phase 2 deve ser escrito: a Phase 2 depende da decisão arquitetural que só o benchmark AR-2/AR-3 pode produzir.

