# Contrato do DOM observado

- Observação: 03/11/2026, somente leitura, sem dados pessoais persistidos.
- Versões: Angular 10.0.14; e-Contas 2.6.17.
- Este contrato descreve o que foi observado e o que é suposição. Seletores não comprovados estão marcados.

## Rotas

| Rota | Forma observada | Uso |
|---|---|---|
| Autos | /#/dashboard/processos/:idProcesso/autos | Aba fonte; idProcesso numérico. Aceita parâmetro de header na hash. |
| Complementar Ato | /#/dashboard/complementar-ato/:idProcesso | Aba de destino; mesmo idProcesso. |

O produto exige a mesma origem https://processos.tce.rn.gov.br e rejeita origem externa, id malformado, usuário ou senha na URL.

## Visualizador de autos

| Elemento | Seletor observado | Observação |
|---|---|---|
| Iframe do documento | iframe#ifrm ou iframe[title="iframe de anexo"] | Cross-origin; src no host novaarearestrita.tce.rn.gov.br. |
| Caminho do PDF | /as/consultaprocessotemp/AAAA/M/D/GUID/GUID.pdf | Sem query; GUIDs canônicos. |
| Texto do PDF no DOM pai | ausente | Não há textLayer nem PDFViewerApplication acessível. |
| Página atual | indicador textual do visualizador | 1/1 no documento observado. |

O adaptador do produto não tenta ler o DOM interno do iframe. Ele valida o src, solicita os bytes ao service worker e extrai o texto com PDF.js fixado. O acesso real permanece REAL_VIEWER_UNVERIFIED.

## Formulário Complementar Ato

| Elemento | Seletor observado | Atributos relevantes | Uso |
|---|---|---|---|
| Modalidade | tce-select-field.modalidade-campo | label=Modalidade, bindlabelselect=descricao, bindvalueselect=idModalidade | Processo; uma única modalidade. |
| Dropdown | ng-select .ng-dropdown-panel .ng-option | 11 opções no catálogo observado; ids gerados | Correspondência por rótulo exato e único. |
| Valor selecionado | ng-select .ng-value | texto do rótulo | Readback da modalidade. |
| Data DOE | tce-input-field[formcontrolname="dataDoeEstado"] input | type text, bsdatepicker | Data da resolução administrativa em DD/MM/AAAA. |
| Cargo | tce-input-field[formcontrolname="cargo"] input | maxlength 50 | Texto do interessado. |
| Matrícula | tce-input-field[formcontrolname="matricula"] input | maxlength 20 | Preserva zeros, barra e hífen. |
| Nascimento | tce-input-field[formcontrolname="dataNascimento"] input | type text, bsdatepicker | Somente se expresso no documento. |
| Pessoas | button.cartao-item | classe selecionada no cartão ativo | Um cartão observado; múltiplos não verificados. |
| Botão final | button "Complementar ato" | type=button | Nunca clicar. |
| Voltar | button "Voltar" | type=button | Não usado. |

## Catálogo observado de modalidade

1. Aposentadoria compulsória
2. Aposentadoria Especial com fundamento na LC nº 51/1985
3. Aposentadoria Especial com fundamento no art. 57 da Lei nº 8.213/91
4. Aposentadoria por invalidez
5. Aposentadoria proporcional ao tempo de contribuição
6. Aposentadoria proporcional ao tempo de serviço
7. Aposentadoria voluntária por tempo de contribuição com proventos integrais
8. Aposentadoria voluntária por tempo de serviço com proventos integrais
9. Reforma
10. Revisão de Benefício
11. Transferência a pedido para a reserva remunerada

## Vínculo independente de processo

| Tela | Elemento observado | Forma do texto | Uso |
|---|---|---|---|
| Complementar Ato | h3.mb-0.ng-star-inserted | COMPLEMENTAR ATO - PROCESSO NNNNNN/AAAA | Extrai processLabel e envia no snapshot. |
| Autos | h4 | AUTOS DO PROCESSO NNNNNN / AAAA | Extrai processLabel do documento atual. |

O produto normaliza o par número/ano e compara os dois rótulos antes de qualquer preenchimento ou diagnóstico. Divergência gera PROCESS_LABEL_MISMATCH; ausência gera PROCESS_BINDING_UNVERIFIED.

## Identidade e revisão

- processId vem da rota hash e é comparado entre as abas.
- interestedKey é um hash do nome normalizado do cartão selecionado, sem CPF.
- documentKey é um hash do pathname do PDF atual; o evento não é identidade.
- revisionMarker combina processo, interessado, valores dos quatro campos, modalidade e catálogo. É recalculado antes de cada escrita.
- Se houver zero ou mais de uma aba de autos do mesmo processo, a extensão recusa.
- Se o documento, processo, interessado ou rota mudar durante a leitura, nada é escrito.

## Não comprovado

- Processo com dois ou mais interessados no portal real.
- Comportamento de autosave.
- Leitura dos bytes do PDF real.
- Escrita L2 em qualquer campo real.
- Estabilidade dos seletores em versões futuras do e-Contas.