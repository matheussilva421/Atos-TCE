# Candidato seguro de rollback — 0.1.1

Data: 06/11/2026
Estado: `ROLLBACK_CANDIDATE` / salvamento desligado

Este pacote preserva a versão 0.1.1 com o motor de lote desligado, para rollback do release 2.0.0. O release funcional homologado está em `docs/evidence/batch-final-release.md`.

## ZIP

| Item | Valor |
| --- | --- |
| Arquivo | `release/Complementador-eContas-0.1.1-batch-safe.zip` |
| Bytes | 645.040 |
| SHA-256 | `D820E4A9E32FB66F99C27D5B8B2E777E65E901153BC9076DE05EE154A8319E0C` |
| Manifesto | 0.1.1 |
| Flags | execução, salvamento e fill-only desligados |

## Uso

- Rollback: remover/desativar a 2.0.0 e carregar este pacote ou o backup `work/batch-final-baseline-2026-11-05`.
- Reverter código não desfaz ato já gravado no e-Contas.
- Não instalar no Chrome profissional sem autorização institucional.
