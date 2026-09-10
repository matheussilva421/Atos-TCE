# Baseline da suíte Python ampla — 10/09/2026

Status desta tarefa: **BLOQUEADO POR ESCOPO**. A lentidão foi reproduzida e a
causa foi localizada, mas o arquivo que contém a correção mínima é JavaScript;
a tarefa autorizou escrita somente em documentação e testes/harness Python.
Nenhum teste foi pulado para esconder a falha.

## Comando canônico

O comando foi localizado no README e nos handoffs versionados. Foi executado a
partir de `C:\Users\slvma\Downloads\Github\Complementação de Atos\work\tce-extractor`:

```powershell
C:\Python314\python.exe -m unittest discover -s . -p 'test_*.py' -v
```

Os logs brutos foram gravados fora do repositório, em:

- `C:\Users\slvma\AppData\Local\Temp\codex-task-1-1-python-suite\wide-verbose.stdout.log`
- `C:\Users\slvma\AppData\Local\Temp\codex-task-1-1-python-suite\wide-verbose.stderr.log`
- `C:\Users\slvma\AppData\Local\Temp\codex-task-1-1-python-suite\wide-run-2.stdout.log`
- `C:\Users\slvma\AppData\Local\Temp\codex-task-1-1-python-suite\wide-run-2.stderr.log`

## Descoberta ampla

Na primeira observação, o caso que reteve o progresso da suíte foi:

```text
test_simulated_pages_frames_and_send_block (test_automation_browser.AutomationBrowserTests.test_simulated_pages_frames_and_send_block)
```

O log continuou até o encerramento da execução. Resultado da primeira rodada:

| total | aprovados | falhas | erros | skips | duração |
|---:|---:|---:|---:|---:|---:|
| 406 | 392 | 5 | 1 | 8 | 212,053 s |

O erro de browser foi o caso acima. As cinco falhas restantes foram
`test_portable_bat_launcher_delegates_to_cmd`, três casos de
`test_prepare_transfer` e `test_second_instance_is_rejected_until_first_is_closed`;
elas não foram alteradas porque estão fora do escopo desta tarefa e variaram
com o estado concorrente do checkout.

Segunda rodada do mesmo comando:

| total | aprovados | falhas | erros | skips | duração |
|---:|---:|---:|---:|---:|---:|
| 406 | 396 | 1 | 1 | 8 | 179,477 s |

O erro de browser permaneceu. A única falha adicional foi o teste de EOL de
`INICIAR.bat`; não foi tocada.

Avisos observados nas rodadas:

- 1 aviso de API `fitz` depreciada;
- 16 `ResourceWarning` deliberados ao testar respostas HTTP de erro (`409`,
  `413`, `401`, `403`, `404`, `500` e semelhantes).

## Reexecução focal com timeout externo de 60 s

Comando executado em cada rodada, a partir do mesmo diretório:

```powershell
C:\Python314\python.exe -u -m unittest test_automation_browser -v
```

Cada processo foi iniciado por `Start-Process`, aguardado no máximo 60 s e
encerrado pela árvore de processos se ultrapassasse o limite. Logs:

- `C:\Users\slvma\AppData\Local\Temp\codex-task-1-1-python-suite\focused-run-1.stdout.log`
- `C:\Users\slvma\AppData\Local\Temp\codex-task-1-1-python-suite\focused-run-1.stderr.log`
- `C:\Users\slvma\AppData\Local\Temp\codex-task-1-1-python-suite\focused-run-2.stdout.log`
- `C:\Users\slvma\AppData\Local\Temp\codex-task-1-1-python-suite\focused-run-2.stderr.log`
- `C:\Users\slvma\AppData\Local\Temp\codex-task-1-1-python-suite\focused-run-3.stdout.log`
- `C:\Users\slvma\AppData\Local\Temp\codex-task-1-1-python-suite\focused-run-3.stderr.log`

| rodada | total | aprovados | falhas | erros | skips | duração | timeout externo |
|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 1 | 0 | 0 | 1 | 0 | 33,894 s | não atingido |
| 2 | 1 | 0 | 0 | 1 | 0 | 34,244 s | não atingido |
| 3 | 1 | 0 | 0 | 1 | 0 | 33,836 s | não atingido |

Mensagem comum:

```text
Page.evaluate: Error: A listener indicated an asynchronous response by returning true, but the message channel closed before a response was received
```

Após cada rodada, os PIDs iniciados (`29744`, `20804`, `30904`) estavam
ausentes e não havia diretórios temporários `tce-automation-browser-*` ou
`tce-extension-fixture-*` sobrando.

## Causa identificada

O teste cria um portal local HTTPS com um iframe de formulário e envia
`PORTAL_NAVIGATE` para o content script. No caminho `return_list`, o script
`portable/extensao-complementar-ato/content/portal-navigation.js` percorre
`window.frames` com `for...of`. A sondagem direta no Chrome produziu:

```text
{'framesType': 'object', 'frameCount': 1, 'iterator': 'undefined', 'frameUrls': ['https://novaarearestrita.tce.rn.gov.br/form.html']}
```

Logo, `window.frames` é array-like, mas não iterável. O `TypeError` ocorre no
callback assíncrono de verificação da navegação. Como o listener retorna
`true`, mas a Promise não chega a `sendResponse`, o Playwright aguarda o
timeout padrão e reporta canal fechado. A classificação é **espera de
navegador causada por Promise de navegação não liquidada**.

Não foi observada espera de rede externa, processo filho órfão, lock, fixture
grande ou cleanup ausente. O servidor da fixture é local, daemon e é encerrado
no `finally`; os processos e diretórios temporários iniciados nesta tarefa
foram verificados após as execuções.

## RED, correção mínima e limite de escopo

O RED já existente em `test_automation_browser.py` é a asserção
`self.assertTrue(back["ok"])`, alcançada após a chamada `PORTAL_NAVIGATE` de
retorno. Ela foi reproduzida quatro vezes no total, incluindo as três rodadas
focais com o mesmo erro.

A correção mínima real é substituir a iteração direta de `window.frames` por
uma enumeração indexada/`Array.from` no content script e adicionar uma
regressão JavaScript para o objeto array-like. Esses arquivos estão fora do
escopo explícito desta tarefa, que proíbe tocar arquivos que não sejam
documentação ou teste/harness Python. Não foi aplicada uma alteração de
timeout que apenas transformaria o erro em falha rápida, nem um shim no
fixture que mascararia o defeito e reduziria a cobertura.

Consequentemente, não há GREEN focal nem GREEN amplo após correção. A decisão
necessária para retomar é autorizar a correção/teste do content script, ou
atribuir essa alteração a outra tarefa/agente.

## Git e pendências

- Branch permaneceu `main`.
- Nenhum `git add`, stage, commit ou troca de branch foi executado.
- Os arquivos de Fase 0 e as alterações concorrentes do controlador foram
  preservados sem edição nesta tarefa.
- Pendência principal: correção JavaScript de `window.frames` e sua regressão;
  depois disso, repetir o focal três vezes e a ampla duas vezes.
