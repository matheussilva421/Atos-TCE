# Complementação de Atos — TCE/RN

Ferramentas locais para coletar eventos do e-Contas, identificar Resolução Administrativa e Guia Financeira/Taxação de Proventos, gerar uma mesa HTML de conferência e exportar os dados para a extensão da Área Restrita.

## Mesa Local (nova arquitetura — em construção)

A Mesa Local é o centro de workflow e estado que está substituindo gradualmente
o menu PowerShell, o serviço local e o sidepanel. A migração segue os marcos M1
a M6 de `docs/superpowers/plans/2026-09-18-atos-tce-plano-completo.md`; o fluxo
antigo continua operacional e é o fallback até o último marco.

Rodar a Mesa (M1 = somente leitura: consulta, não coleta nem preenche):

```powershell
python -m app.main --data-root data --port 18743
```

O mesmo comando está em `START.cmd`. Os dados de runtime ficam fora do Git, em
`data/` (banco `atos-tce.db`, `archive/` com blobs canônicos SHA-256 e a árvore
`archive/processos`, `logs/` com os recibos de migração).

Migrar o acervo legado (`work/tce-extractor/acervo-tce`) para o acervo canônico:

```powershell
# ensaio: apenas lê, calcula hashes e relata; não escreve blobs nem linhas
python scripts/migrate-legacy.py --archive-root work\tce-extractor\acervo-tce --data-root data
# efetivar somente depois de conferir o relatório e o espaço livre
python scripts/migrate-legacy.py --archive-root work\tce-extractor\acervo-tce --data-root data --apply
```

O importador nunca altera o acervo de origem. O ZIP portátil padrão não contém o
acervo de processos; backup completo é uma operação explícita e separada.

Testes da Mesa (raiz do repositório):

```powershell
python -m unittest tests.test_store tests.test_legacy_import tests.test_api_server -v
```

Fronteiras que a Mesa preserva: `autoSubmit=false` e `real_send_enabled=false`.
O clique final de conclusão do ato permanece humano em todos os marcos.

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

No Windows, o runner preserva a semântica de liveness de PID necessária aos
testes de transferência e mantém stdout/stderr nos logs; isso evita interpretar
um runtime local vivo como encerrado.

## Segurança

- Repositório local: nenhum upload ao GitHub é feito automaticamente.
- `.gitignore` usa lista de permissão; dados pessoais, PDFs, ZIPs, backups, caches e perfis de navegador não são versionados.
- O envio automático é um opt-in explícito do operador: fica desabilitado por
  padrão (`real_send_enabled=false`) e só é liberado quando a mesa local é
  iniciada com `INICIAR.cmd envio-real`. Cada execução automática processa no
  máximo 100 atos elegíveis, exige intenção persistida e comando único por ato e
  pausa em resultado incerto. Sem o comando de envio real, o checkbox do painel
  permanece desabilitado.
- A regra operacional solicitada para DOE usa a data da Resolução Administrativa; não equivale a comprovação independente da publicação no Diário Oficial.
- Preserve backups até conferir o novo lote. Nunca publique `outputs`, `tmp` ou perfis autenticados.

Veja `docs/notes/2026-09-05-organizacao-handoff.md` para o estado da migração.
