# Organização e manutenção

O código suportado vive na raiz do repositório:

| Caminho | Papel |
|---|---|
| `app/` | Mesa Local: serviço loopback, API, análise, e-Contas, arquivo híbrido e web |
| `extension/` | Extensão fina (Manifest V3), sem superfície de envio |
| `packaging/` | Builder do ZIP, verificador, manifesto do runtime e licenças |
| `scripts/` | Migração, auditoria de armazenamento, limpeza, backup e retenção de builds |
| `tests/` | Suíte Python da Mesa |
| `START.cmd` | Launcher único (Python embutido do pacote ou o do sistema) |

Dados de runtime ficam fora do Git: `data/` (banco, blobs canônicos nomeados
pelo SHA-256, visão por processo e recibos em `data/logs/`), `dist/` (ZIP atual e
anterior) e `tmp/` (extrações descartáveis). Nunca versione PDFs, ZIPs, perfis de
navegador, tokens, HAR ou trace.

`work/tce-extractor` é a extração legada: permanece como referência e fallback, e
`work/tce-extractor/acervo-tce` é o acervo de origem, preservado até o gate
destrutivo de M6. Nenhum caminho de runtime suportado depende dele — essa
fronteira é verificada por `tests/test_no_legacy_paths.py`. `outputs/` e
`Versions/` guardam entregas e extrações antigas, também fora do Git.

Antes de apagar qualquer árvore histórica, rode `scripts/storage-audit.py`
(somente leitura) e depois `scripts/cleanup-storage.py` em dry-run. A remoção só
acontece com `--apply` sobre candidatos que o recibo provou seguros, re-medidos
na hora; a retirada do legado ainda exige tag de segurança, execução real
supervisionada e autorização explícita. O estado de cada marco fica em
`docs/notes/2026-09-18-mesa-refactor-handoff.md`.

Para publicar futuramente: revisar `git diff --cached`, configurar um remoto
privado explicitamente e somente então fazer push. A pasta chamada Github não
cria, por si só, um repositório remoto.
