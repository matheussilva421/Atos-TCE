# Handoff — reconciliação Git do Atos-TCE — 2026-09-24

## Objetivo e limite desta sessão

Parar novas features e reconciliar o trabalho já existente em uma única branch
de desenvolvimento, comparando as versões com a SPEC e os planos canônicos.
Nenhuma feature de Próximo Processo foi implementada. Nenhum envio ou botão
final do portal foi acionado.

## Base e preservação

- `git fetch origin` passou. `origin/main` atual no início: `b1d41e848c39cb61947b011501925c40f86793fb`.
- A branch local `main` foi avançada de `ffa208f` para `b1d41e8` por fast-forward.
- `codex/atos-tce-unified` foi criada a partir de `origin/main` e integra as
  sequências best-effort, discovery e o snapshot seguro M2.
- Snapshot integral do estado sujo original, incluindo 17 alterações tracked e
  o piloto local: `refs/codex/preservation/atos-tce-pre-unification-2026-09-24`
  em `1fea9c77b1e2d521e8ff2c289ca5e7cf3c6c970f`.
- Blob preservado do piloto local: `refs/codex/preservation/atos-tce-live-pilot-2026-09-24`
  em `a3c89803fb9858a2300773664c3cc27ca2e45d26`. O arquivo
  `work/tce-extractor/.codex-live-pilot.py` permanece local e fora do Git.
- Snapshot isolado das seis alterações seguras M2:
  `refs/codex/preservation/atos-tce-m2-safe-2026-09-24` em
  `709cef509c20a603a7c48a9db4747237261479bc`; esse conteúdo foi incorporado.
- A parte experimental restante do snapshot integral relaxava identidade do
  formulário, permitia alvo ambíguo, sobrescrevia valores divergentes ou
  permitia preencher processo fora de `PRONTO`. Ela contradiz a SPEC e foi
  preservada somente na ref de segurança, sem entrar na branch final.

## Inventário inicial de branches e commits exclusivos

Todos os commits exclusivos abaixo foram encontrados em relação à base
`origin/main` (`b1d41e8`):

| Branch/ref | HEAD inicial | Exclusivos | Reconciliação |
|---|---:|---:|---|
| `main` | `ffa208f` local; `b1d41e8` remoto | 0; a local estava 160 atrás | fast-forward da branch local para `b1d41e8` |
| `codex/mesa-local-refactor` | `75eb2b0` | 0, ancestral da base; 9 atrás | código/histórico já estavam em `origin/main`; sem cherry-pick |
| `origin/codex/mesa-local-refactor` | `b1d41e8` | 0 | mesmo commit de `origin/main` |
| `codex/atos-tce-best-effort-v4` | `15a34f7` | 11: `5e2ecd1`, `e86bc08`, `2d77a01`, `04f2317`, `66d29ff`, `f726012`, `2d79308`, `905e8ce`, `8076cdd`, `16c7608`, `15a34f7` | merge preservando os 11 commits; seleção semântica descrita abaixo |
| `origin/codex/best-effort-form-filling` | `e7ff1dd` | 20: `707bd30`, `f9ac44e`, `b056a26`, `f41eb33`, `60a55c7`, `84d1946`, `9e33cc1`, `ab38966`, `0cc808b`, `f7a9342`, `c7c8edc`, `258fb23`, `ddbc957`, `1e7cb2b`, `02e4a31`, `576904d`, `c136778`, `cc903c6`, `dd39d80`, `e7ff1dd` | merge preservando os 20 commits |
| `codex/next-process-navigation-discovery` | `0b69926` | 2: `5c4f4a2`, `0b69926` | merge somente do discovery/handoff; feature continua parada |
| `origin/main` | `b1d41e8` | 0 | base canônica, mantida |

Branches locais, preservações e worktrees devem ser rechecados antes da limpeza;
este inventário não autoriza excluir `main`.

## Decisões dos merges e conflitos

- Merge best-effort `b37b8bd` reuniu `e7ff1dd` e `15a34f7`; foram resolvidos
  17 conflitos. O ranking legal v4 e seus fixtures/testes vieram da v4, pois
  desempata scores pela evidência estrutural sem perder o índice do catálogo
  como desempate final. O filler/extensão e o resumo parcial vieram da branch
  remota, incluindo a verificação de identidade após cada escrita.
- Foram restauradas as guardas backend de identidade e `generation_after` no
  resultado final do preenchimento. O preflight usa a mesma função canônica de
  opções legais selecionáveis e ignora campos marcados como ilegíveis.
- Foram preservados testes específicos dos dois lados: desempate estrutural,
  opções desabilitadas, resultados sem identidade/geração, pessoa divergente,
  campo ilegível, resumo parcial, retry e proteções de escrita.
- `extension/content/detect-form.js` agora isola erro de leitura em um único
  controle como `readable: false`; os demais campos e a identidade seguem
  legíveis. O preflight não coloca esse controle no plano de escrita.
- Merge discovery `18b6134` preserva os dois commits e a nota
  `docs/notes/2026-09-23-area-restrita-next-navigation-discovery.md`.
- Merge M2 `5f27aa6` incorpora os seis arquivos do snapshot seguro. O scanner
  exige páginas sequenciais, marcador estável, aguarda a página esperada e
  recusa cobertura incompleta. Não foi iniciada nova travessia real do portal.
- `tests/test_api_server.py` e `app/web/tests/ui-wiring.test.mjs` receberam
  ajustes de fixtures/assertions estáticas obsoletas, mantendo os contratos
  verificados e isolando as condições nomeadas pelos testes.

## Testes até este handoff

- `python -m unittest discover -s tests -p 'test_*.py' -q`: 616 executados,
  615 passaram, 0 falharam, 1 ignorado.
- `npm test --prefix extension`: 145 passaram, 0 falharam.
- `node --test` nos arquivos `app/web/tests/*.test.mjs`: 28 passaram, 0 falharam.
- `python -m unittest discover -s tests -p test_cdp_fallback.py -q`: 22 passaram.
- `python -m unittest discover -s tests -p test_compare_area_scans.py -q`: 14 passaram.
- `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass
  -File .\work\tce-extractor\verify-project.ps1` passou em uma execução:
  1.258 executados, 1.256 aprovados, 0 falhas e 2 ignorados. Essa execução
  antecedeu os dois últimos ajustes de assertions/fixture; repetir como gate
  final depois da atualização deste handoff.
- `git diff --check` passou no gate acima; executar também
  `git diff origin/main...HEAD --check` no gate final.

## Estado frente à SPEC e aos planos

| Requisito | Estado | Evidência/limite |
|---|---|---|
| Fundamento legal v4: sempre escolher opção real selecionável com texto documental, desempate semântico estável | Implementado offline | `app/analysis/legal.py`, fixtures e `tests/test_legal_rules.py`; merge `b37b8bd` |
| Preflight/fill best-effort por campo; preservar divergência e continuar independentes | Implementado offline | `app/area_restrita/preflight.py`, `fill_service.py`, extensão e testes |
| Identidade composta e geração como guardas de escrita; validar também o resultado | Implementado e testado | API, serviço e `extension/content/fill-form.js`; sem prova de portal real |
| Resultado parcial, retry e processo documental em `PRONTO` | Implementado offline | API, UI, serviço e testes; sem envio automático |
| Qualificação real do preenchimento no portal (plano Task 10) | Pendente/bloqueada | handoff de validação declara portal real ainda não qualificado; nenhum piloto nesta sessão |
| Próximo Processo, descoberta Phase 0 | Parcial; gate bloqueado | nota registra marcador bruto atual não observado, delta global de um item sem causa, `SCAN_PAGE` vivo ausente, caso multi-interessado e baseline pós-conclusão pendentes |
| Próximo Processo, Tasks 1–8 / código de produção | Não iniciado | 62 caixas do plano permanecem abertas; nenhuma navegação nova foi implementada |
| M2 CDP: cobertura real completa e igualdade com scan Mesa | Incompleto | código e testes locais corrigem scanner/comparador; nota manda não repetir scan de 40 páginas sem solicitação; evidência real completa falta |
| Não submeter/finalizar ato | Preservado | extensões e UI não expõem envio; testes de protocolo continuam cobrindo essa fronteira |

## Worktrees, GitHub e retomada

- `git worktree list` no repositório principal mostrou somente a worktree raiz.
- Foram encontrados dois checkouts reais em `.worktrees/`, ambos limpos e em
  clone Git separado: `atos-tce-baseline` em `e7ff1dd` (branch best-effort,
  mesmos 20 commits já mesclados) e `atos-tce-navigation-discovery` em
  `b1d41e8` (sem commits exclusivos; apesar do nome, não continha os commits de
  discovery). Verificar seus estados novamente antes de removê-los.
- Os diretórios sob `C:\Users\slvma\.codex\worktrees` eram marcadores sem
  checkout Git ativo (um contém uma pasta de outro projeto); não foram tratados
  como worktrees deste repositório nem removidos.
- Ainda não houve push nem exclusão de refs remotas. Antes de excluir refs
  remotas, publicar `codex/atos-tce-unified`, provar que cada commit está
  contido nela e mostrar a lista exata ao usuário. `main` nunca deve ser
  removida.
- Próximos passos: repetir o verify gate final; excluir o script local apenas
  da visibilidade de `git status` por regra privada em `.git/info/exclude`
  (sem mover, apagar ou versionar); confirmar árvore limpa; atualizar este
  handoff; push da branch unificada; provar inclusão; remover branches e os
  dois checkouts temporários; registrar SHA, branches/worktrees restantes e
  resultado final.
