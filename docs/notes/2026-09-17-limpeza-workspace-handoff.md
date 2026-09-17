# Handoff — limpeza do workspace (2026-09-17)

## Resumo

Limpeza pedida pelo operador ("analise a pasta local e exclua o que não for
necessário, lotes de processos antigos, versões do zip desatualizadas"). Foram
removidos **13,7 GB** de artefatos redundantes, desatualizados ou temporários.
Nenhum dado de processo, PDF, perfil em uso, `Versions/` ou artefato publicado
recente foi tocado.

## Removido (com tamanho)

| Caminho | MB | Motivo |
|---|---|---|
| `outputs/Atos-TCE-Professor-IPERN-completo-2026-09-14.zip` | 5574,5 | ZIP superado pelo de 09-16 |
| `work/Atos-TCE-Professor-IPERN-completo-2026-09-14.zip` | 5574,5 | cópia duplicada do ZIP antigo acima |
| `outputs/tce-processos-completo-portatil-2026-09-16.zip` | 91,8 | pacote portátil superado |
| `outputs/tce-processos-completo-portatil-private-2026-09-16-v2/` | 197,6 | extração com runtime podado (incompleto vs. o próprio manifesto) |
| `dados-locais/chrome-qa-profile-backup-20260914/` | 42,8 | backup de perfil de QA |
| `dados-locais/chrome-qa-profile-backup-20260914-2/` | 17,5 | backup redundante |
| `dados-locais/probe-profile/` | 9,2 | perfil de sonda descartável |
| `.worktrees/fundamento-legal-v3-r2/` | 9,3 | worktree R2 já integrada à main |
| `.worktrees/fundamento-legal-v3-r3/outputs/qa-extract-r3{,b,c,d}/` | 1008,8 | extrações de verificação do pacote |
| `.worktrees/fundamento-legal-v3-r3/work/tce-extractor/staging-task5-verified/` | 246,5 | cópia do runtime para empacotar |
| `.worktrees/fundamento-legal-v3-r3/work/tce-extractor/.package-staging-*` | 953,8 | sobras de staging do empacotador |
| `__pycache__` de teste | 1,3 | regenerável |

## Preservado

| Caminho | Tamanho | Situação |
|---|---|---|
| `Versions/TCE-...-2026-09-16-final-professor-ipern/` | 8,88 GB | extração de referência mais recente |
| `Versions/TCE-...-2026-09-14.zip` | 1,22 GB | área de preservação (AGENTS.md) — não removido |
| `outputs/Atos-TCE-Professor-IPERN-completo-2026-09-16.zip` | 5,57 GB | ZIP grande mais recente |
| `outputs/TCE-fixed-2026-09-16/` | 8,88 GB | extração de QA de 09-16; fonte do runtime usado no pacote R3 |
| `work/tce-extractor/acervo-tce/processos/` | 8,5 GB | arquivo local de processos (PDFs) |
| `work/tce-extractor/acervo-tce/*.json` + HTML | ~130 MB | derivados regeneráveis do lote atual |
| `work/tce-extractor/portable/dados-locais/` (perfil + bridge) | 334 MB | estado local do fluxo portátil |
| `dados-locais/chrome-qa-profile/` + `qa-runs/` | 39 MB | perfil e execuções de QA em uso |
| `.worktrees/fundamento-legal-v3-r3/` | ~99 MB | worktree R3 (não integrada) + `outputs/tce-portatil-r3.zip` validado |

## Como refazer o empacotamento depois desta limpeza

O runtime verificado usado no staging continua disponível em
`outputs/TCE-fixed-2026-09-16/`. Para reconstruir o pacote:

```powershell
$ws = 'C:\Users\slvma\Downloads\Github\Atos-TCE'
$staging = "$ws\.worktrees\fundamento-legal-v3-r3\work\tce-extractor\staging-task5-verified"
New-Item -ItemType Directory -Path "$staging\licenses" -Force | Out-Null
Copy-Item -LiteralPath "$ws\outputs\TCE-fixed-2026-09-16\runtime" -Destination "$staging\runtime" -Recurse -Force
Copy-Item -LiteralPath "$ws\outputs\TCE-fixed-2026-09-16\licenses\*" -Destination "$staging\licenses" -Force
Copy-Item -LiteralPath "$ws\outputs\TCE-fixed-2026-09-16\runtime-manifest.json" -Destination "$staging\runtime-manifest.json" -Force
```

## Pendências

- decisão do operador sobre os itens grandes preservados: `outputs/TCE-fixed-2026-09-16/`
  (8,88 GB), `Versions/...-2026-09-14.zip` (1,22 GB), `acervo-tce/processos/` (8,5 GB) e
  `portable/dados-locais/perfil-navegador` (334 MB, exigiria novo login manual);
- integração da worktree R3: **concluída** — merge commit `21df79c` na `main`
  (`--no-ff` a partir de `fa9774a`, porque a `main` já continha este handoff),
  com o gate completo verde no `main` antes do push;
- smoke real supervisionado da R3, pendente de operador no portal.
