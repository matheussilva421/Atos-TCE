# Complementação de Atos — TCE/RN

Ferramentas locais para coletar eventos do e-Contas, identificar Resolução Administrativa e Guia Financeira/Taxação de Proventos, gerar uma mesa HTML de conferência e exportar os dados para a extensão da Área Restrita.

## Usar o pacote pronto

O pacote de runtime mais novo desta rodada é o `fase11k`, preservado em
`outputs/tce-processos-completo-portatil-fase11k.zip` e auditado em extração
limpa. Extraia-o inteiro em uma pasta nova e abra `GUIA-RAPIDO.html`; não
versione nem compartilhe esse ZIP.

O acervo privado de 05/09 é uma entrega diferente: contém 227 processos, 5.236
eventos e 4.532 PDFs e permanece fora do Git. O runtime `fase11k` é o pacote de
ferramentas, extensão e serviço para operar sobre dados autorizados; ele não é
uma publicação do acervo privado. Valores ausentes e conflitantes exigem
revisão humana.

O lote real 1/50 foi baixado e fechado com 50 processos e 1.037 PDFs completos;
essa evidência permanece privada. Um Termo de Apensamento não foi disponibilizado
pelo portal; capas indisponíveis foram dispensadas.

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

### Verificação única offline

Para executar os gates locais em um checkout limpo, rode:

```powershell
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1
```

O comando executa os testes da extensão e da web, a suíte Python de `portable`,
os testes PowerShell, os testes de empacotamento/auditoria e `git diff --check`.
`-TimeoutSeconds N` define o limite de cada etapa; o resumo final informa o
comando, executados, aprovados, falhos e skips. Logs brutos ficam em uma pasta
temporária fora do repositório. O verificador é somente offline: não abre
Chrome autenticado, não coleta dados e não envia atos.

## Segurança

- Repositório local: nenhum upload ao GitHub é feito automaticamente.
- `.gitignore` usa lista de permissão; dados pessoais, PDFs, ZIPs, backups, caches e perfis de navegador não são versionados.
- O envio automático ainda não está qualificado: `real_send_enabled=false` e
  `pilot_enabled=false`. Nenhum ato foi enviado; conclusão, confirmação e envio
  permanecem manuais e sujeitos aos gates portal-real.
- A regra operacional solicitada para DOE usa a data da Resolução Administrativa; não equivale a comprovação independente da publicação no Diário Oficial.
- Preserve backups até conferir o novo lote. Nunca publique `outputs`, `tmp` ou perfis autenticados.

Veja `docs/notes/2026-09-05-organizacao-handoff.md` para o estado da migração.
