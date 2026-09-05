# Complementação de Atos — TCE/RN

Ferramentas locais para coletar eventos do e-Contas, identificar Resolução Administrativa e Guia Financeira/Taxação de Proventos, gerar uma mesa HTML de conferência e exportar os dados para a extensão da Área Restrita.

## Usar o pacote pronto

O ZIP atual está em `outputs/TCE-Acervo-Atualizado-227-2026-09-05.zip`. Extraia-o inteiro em uma pasta nova e abra `GUIA-RAPIDO.html`. O HTML fica em `acervo-tce/complementar-ato.html`; importe `acervo-tce/dados-complementar-ato.json` uma vez na extensão.

O lote contém 227 processos, 5.236 eventos e 4.532 PDFs. Um Termo de Apensamento do processo100093/2022 não foi disponibilizado pelo portal. Capas indisponíveis foram dispensadas. Valores ausentes e conflitantes exigem revisão humana.

## Estrutura

| Pasta | Finalidade | Git |
|---|---|---|
| `work/tce-extractor/` | Código Python/PowerShell e testes | Código permitido explicitamente |
| `work/tce-extractor/portable/` | Fontes do pacote e extensão Chrome | Sem runtime nem dados |
| `outputs/` | Entregas, PDFs, HTMLs e ZIPs privados | Ignorado |
| `tmp/` | QA, extrações descartáveis e perfis locais | Ignorado |
| `portable/` | Materiais de uma montagem anterior | Ignorado |
| `.codex-remote-attachments/` | Anexos de referência recebidos | Ignorado |
| `docs/` | Estrutura e handoff da reorganização | Versionado |

O layout relativo foi preservado para não quebrar empacotadores. Os diretórios `staging*` e `.package-staging-*` são montagens locais, não fontes. `staging-task5-verified` é dependência do empacotador do runtime e não deve ser removido indiscriminadamente.

## Desenvolvimento e testes

Na raiz, execute:

```powershell
Set-Location work/tce-extractor/portable/extensao-complementar-ato
npm test
```

Os testes Python ficam em `work/tce-extractor/test_*.py` e os testes PowerShell em `work/tce-extractor/tests/`. A suíte completa requer Python com PyMuPDF, Playwright e dependências de QA; o usuário do ZIP não precisa instalar esse ambiente de desenvolvimento. Alguns helpers de QA históricos contêm caminhos do workspace original: consulte o handoff antes de reutilizá-los.

## Segurança

- Repositório local: nenhum upload ao GitHub é feito automaticamente.
- `.gitignore` usa lista de permissão; dados pessoais, PDFs, ZIPs, backups, caches e perfis de navegador não são versionados.
- O coletor não envia atos. A extensão somente auxilia o preenchimento autorizado; conclusão e envio são manuais.
- A regra operacional solicitada para DOE usa a data da Resolução Administrativa; não equivale a comprovação independente da publicação no Diário Oficial.
- Preserve backups até conferir o novo lote. Nunca publique `outputs`, `tmp` ou perfis autenticados.

Veja `docs/notes/2026-09-05-organizacao-handoff.md` para o estado da migração.
