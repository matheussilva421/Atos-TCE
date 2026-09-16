# Handoff — fixture sanitizada da sessão portal-real (16/09/2026)

## Resumo

Foi concluído o conversor offline da observação JSON produzida por
`real_portal_session.py` para uma fixture estrutural sanitizada. A observação
original é preservada; o derivado recebe somente sinais necessários para
qualificação e o comando retorna o SHA-256 dos bytes exatos gravados.

O conversor é fail-closed. Ele recusa envio realizado pelo runner, perfil não
isolado, extensão ausente, origem inesperada, erro de navegação, ausência de
interface autenticada, controles incompletos, deriva do contrato e qualquer
identidade de processo detectada.

## Arquivos alterados

- `work/tce-extractor/real_portal_session.py`
  - adicionados `build_sanitized_fixture()` e `write_sanitized_fixture()`;
  - adicionado modo CLI offline:
    `--fixture-input <observacao.json> --fixture-output <fixture.json>`;
  - o modo offline não inicializa Playwright nem abre navegador.
- `work/tce-extractor/test_real_portal_session.py`
  - testes de sanitização, recusas fail-closed, hash dos bytes gravados e CLI.
- `docs/notes/2026-09-16-runbook-sessao-portal-real.md`
  - comando de conversão e limites documentados.

## TDD e validação

RED registrado: o teste novo falhou ao importar `write_sanitized_fixture` antes
da implementação (`ImportError`).

GREEN:

- `python -m unittest test_real_portal_session -q`: 24/24, 0 falhas.
- `python -m unittest test_real_portal_session test_automation_qualification test_qa_workflow -q`: 52/52, 0 falhas.
- `python -m unittest discover -s . -p 'test_*.py' -q`: 506/506, 0 falhas, 8 skips.
- `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1 -TimeoutSeconds 900`: 1.174 checks, 1.172 aprovados, 0 falhas, 2 skips.
- `git diff --check`: passou.

## GitHub

Estado final: `main` e `origin/main` estão alinhadas em `19eb141`
(`feat: add sanitized portal fixture converter`). O commit e o push foram
confirmados.

## Pendências e retomada

Ainda não existe observação portal-real autenticada, fixture derivada nem
`acervo-tce/automacao/qualificacao.json`. Nenhum ato foi preenchido, concluído
ou enviado.

Depois de uma sessão humana isolada válida, executar no diretório do extrator:

```powershell
python .\real_portal_session.py `
  --fixture-input "<observacao-privada>.json" `
  --fixture-output "<pacote>\acervo-tce\automacao\fixtures\portal-real-1.json"
```

Copiar o `sha256` retornado para `fixture_hashes` somente junto com o
`real_event_id` produzido por um evento real observado e pelas versões atuais.
Usar `write_qualification()`; não criar o artefato manualmente nem liberar
`real_send_enabled` sem os três preflights, o observador e a autorização
imediata do envio supervisionado.
