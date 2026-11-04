# F0 — Reconhecimento sanitizado do e-Contas

- Data da observação: 03/11/2026
- Escopo: duas abas já abertas pelo operador, no mesmo perfil, uma de autos e uma de Complementar Ato do mesmo processo.
- Privacidade: nenhum nome, CPF, matrícula, número de processo, conteúdo de PDF, cookie, token, HAR ou screenshot foi registrado neste documento ou no repositório.

## Ferramenta e acesso

- O REA oficial (morluto/rea) **não** foi utilizável: não havia endpoint CDP loopback disponível e a listagem de alvos do navegador não pôde ser executada. Registro: **REA_CDP_UNAVAILABLE**.
- A observação foi feita com o controlador de navegador do Codex (CUA/Playwright) em modo somente leitura de DOM e árvore de acessibilidade. Não foi REA; não houve clique em controles do portal, não houve escrita e não houve captura persistente.
- O Chrome desta estação é gerenciado e bloqueia extensões unpacked carregadas por linha de comando. A validação de navegador foi feita no Edge instalado, com fixtures sintéticas.

## Matriz de evidência

| Pergunta | Evidência observada | Hipótese | Limite | Decisão |
|---|---|---|---|---|
| As duas abas existem e são do mesmo processo? | Sim. As rotas de autos e de complementação apresentaram o mesmo idProcesso numérico. O valor não foi registrado. | — | Apenas a sessão fornecida. | Vínculo por idProcesso da rota; nunca por número de evento. |
| Qual a versão do front-end? | Angular 10.0.14 e e-Contas 2.6.17 no rodapé. | A versão pode mudar. | Observação pontual. | Seletores tolerantes e falha fechada; não assumir versão futura. |
| Como o PDF é exibido? | Iframe com id ifrm e título "iframe de anexo", apontando para novaarearestrita.tce.rn.gov.br no caminho /as/consultaprocessotemp/AAAA/M/D/GUID/GUID.pdf. O iframe é cross-origin em relação à página de autos. O DOM pai não expõe textLayer nem PDFViewerApplication. O visualizador é o PDF nativo do Chromium. | O endpoint pode mudar ou exigir cookies. | Não foi possível ler o DOM interno do PDF. | Não usar textLayer. Adaptador escolhido: obter os bytes do mesmo PDF por host permission e extrair com PDF.js local. |
| O PDF tem mais de uma página? | A interface do visualizador indicou 1/1 para o documento aberto. | Outros documentos podem ter várias páginas. | Apenas o documento observado. | O leitor percorre todas as páginas do PDF e falha se alguma não tiver texto. |
| O texto de todas as páginas é acessível? | Não comprovado no portal real. O DOM pai não lê o iframe; não houve download manual nem leitura dos bytes reais. | O fetch do PDF pelo service worker, com host permission e credenciais, pode funcionar. | **REAL_VIEWER_UNVERIFIED**. | Implementar o adaptador de bytes e provar o fluxo com PDF sintético; não declarar leitura real. |
| O documento atual é identificável sem varrer eventos? | O iframe possui src distinto por documento. O cabeçalho mostra o evento, que varia. | O src pode mudar sem mudar o documento lógico em algum caso. | Sem teste de troca real. | documentKey = hash do pathname do PDF; comparar antes/depois da leitura; não percorrer eventos. |
| Como a modalidade é apresentada? | tce-select-field com classe modalidade-campo, bindlabelselect=descricao, bindvalueselect=idModalidade e ng-select interno. O dropdown expôs 11 opções. O id real não aparece no DOM; os ids das opções são gerados. | O catálogo pode mudar. | Apenas o catálogo observado. | Mapear por rótulo exato e único no catálogo; recusar duplicata ou ausência. |
| Quais são os quatro campos por interessado? | tce-input-field com formcontrolname dataDoeEstado, cargo, matricula e dataNascimento. Cargo tem maxlength 50; matrícula, 20. Os dois campos de data têm input type text com atributo bsdatepicker. | O portal pode alterar limites. | Apenas o formulário observado. | Ler o DOM atual, validar limite e readback; não inventar IDs. |
| Qual o comportamento do datepicker? | lang=pt-BR; calendário em português. O input é textual e depende da diretiva bsDatepicker. | A digitação pode disparar eventos diferentes dos testados. | Não houve escrita real (L2). | Setter nativo + input/change/blur + readback; L2 separado. |
| Como o interessado é selecionado? | Cartões button.cartao-item; o selecionado tem a classe selecionada. O texto do cartão inclui nome e CPF. Foi observado um único interessado. | Processos com vários interessados podem ter mais cartões. | **MULTI_PERSON_UNVERIFIED**. | Extrair o nome do cartão selecionado, remover CPF e usar hash em memória; recusar ambiguidade. |
| Há risco de autosave? | Não testado. Nenhuma digitação real foi feita. | O Angular pode ou não salvar automaticamente. | **AUTOSAVE_UNKNOWN**. | L2 exige autorização separada e monitoramento; interromper se houver indício de autosave. |
| Quais botões evitar? | Voltar e Complementar ato são type=button. Há formulários e botões type=submit não relacionados no cabeçalho e na barra lateral. | — | — | Nunca clicar em Complementar ato, Salvar, Confirmar ou submeter formulário. |

## Decisão F0

- **F0_NEEDS_OPERATOR_DECISION** para a leitura real dos bytes do PDF: o adaptador é tecnicamente recomendado, mas não foi provado no portal.
- **F0_SYNTHETIC_GO** para a implementação: fixtures sintéticas e o fluxo completo no Edge foram executados.
- Status reais: **REA_CDP_UNAVAILABLE**, **REAL_VIEWER_UNVERIFIED**, **MULTI_PERSON_UNVERIFIED**, **AUTOSAVE_UNKNOWN**, **L2_NOT_AUTHORIZED**.

## Alternativas descartadas

- textLayer/PDFViewerApplication: não observados no DOM pai; não há prova de acesso.
- Injeção de content script no iframe do PDF: o iframe é cross-origin e o visualizador é o PDF nativo; não é um documento HTML acessível.
- chrome.debugger, webRequest ou interceptação de rede: permissões amplas e desnecessárias para o MVP.
- OCR, LLM, backend, banco ou serviço local: fora do escopo aprovado.