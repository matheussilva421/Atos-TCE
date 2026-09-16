# Handoff — fundamentação de professores v2 — Task 7

## Implementado

- Serviço local Python atualizado para `RULES_VERSION = "legal-foundation-v2"`.
- Qualification Python atualizado para exigir `rules: legal-foundation-v2` sem alterar schemas independentes.
- Fallback do painel passou a importar `LEGAL_FOUNDATION_RULES_VERSION`, eliminando a string v1 duplicada.
- Fixtures e testes operacionais JS/Python que fixavam `legal-foundation-v1` foram atualizados para v2.
- A constante JS `LEGAL_FOUNDATION_RULES_VERSION` já estava em `legal-foundation-v2` desde a integração da Task 4 e foi verificada nesta task.
- Busca operacional em `work/tce-extractor` não encontrou ocorrências remanescentes de `legal-foundation-v1` em arquivos `.mjs` ou `.py`.

## Testes

- `node --test tests/*.test.mjs`: 405 testes, 405 aprovados, 0 falhas.
- `python -m unittest -q test_legal_context.py test_local_service.py test_automation_api.py`: 69 testes, 69 aprovados, 0 falhas, 1 skip ambiental.
- `python -m unittest -q test_automation_recovery.py test_automation_integration.py` em `portable`: 6 testes, 6 aprovados, 0 falhas.
- RED confirmado antes dos fixtures: contratos Python falhavam com `RULES_VERSION_UNSUPPORTED` enquanto ainda enviavam v1.

## Arquivos alterados

- `work/tce-extractor/portable/app/local_service.py`
- `work/tce-extractor/portable/app/qualification.py`
- `work/tce-extractor/portable/extensao-complementar-ato/sidepanel/panel.js`
- testes JS/Python operacionais sob `work/tce-extractor` que fixavam a versão v1.

## Pendências / retomada

- Implementar Task 8: auditar allowlists e empacotamento dos três módulos v2 novos.
- Implementar Task 9: ampliar matriz de validação jurídica para pelo menos 12 casos e produzir relatório.
- Executar QA do pacote distribuído, suíte final e revisão de segurança/qualidade.

## GitHub

- Branch: `codex/fundamentacao-professores-crosswalk-v2`.
- Este handoff deve ser commitado e enviado junto com a atualização de versão.
