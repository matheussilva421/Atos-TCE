# Análise de conclusão da automação de Complementação de Atos — 16/09/2026

## Status

Análise local e reconstrução do pacote concluídas. A ponte local, o launcher
`ABRIR-MESA.bat`, a recuperação de lock stale e a sincronização
extensão↔HTML foram corrigidos e validados no pacote privado com o lote novo.
A qualificação portal-real ainda não foi concluída. Nenhum ato foi preenchido,
concluído ou enviado nesta análise.

## Evidência atual

- `npm test` da extensão passou 406/406.
- Testes web passaram 6/6.
- Testes Python de serviço, empacotamento e browser passaram 40/40 com 1
  teste marcado como skip.
- `tests/Test-PortableMenu.ps1` passou 98/98.
- `git diff --check` passou.
- Pacote privado novo: `package_audit.py --distribution private` sem achados e
  `TESTAR-PACOTE.ps1` passou 7/7 em extração limpa antes do smoke live.
- Smoke live do novo `ABRIR-MESA.bat`: `BAT_EXIT=0`; o serviço foi parado em
  seguida com `INICIAR.cmd parar`.
- Matriz portal QA: 24 `PASS_FIXTURE`, 1 `PASS_PACKAGE`, 5 `BLOCKED`, 0
  `PASS_REAL` (`docs/notes/qa-final-2026-09-14/qa-report.md`).

## Correções aplicadas nesta retomada

- Adicionado `work/tce-extractor/portable/ABRIR-MESA.bat`, delegando ao
  launcher validado `.cmd`; o empacotador agora o inclui.
- Corrigido `portable/app/menu.ps1`: a abertura da mesa não depende mais de
  uma função fora do escopo da closure, retorna código de sucesso corretamente
  e usa fallback pelo Explorer quando o shell padrão devolve `Acesso negado`.
- Corrigido `portable/app/local_service.py`: preflight CORS `OPTIONS` e
  cabeçalhos CORS autenticados para a origem `chrome-extension://...`.
- Corrigido `work/tce-extractor/html_generator.py`: a página autenticada em
  modo manual continua consultando `/api/v1/state`, mesmo sem publicação
  automática; HTML estático continua sem polling.
- Corrigido `portable/app/prepare_transfer.py`: o CLI encontra o packager
  irmão mesmo sob o `._pth` do Python embutido.
- Corrigido `portable/app/menu.ps1`: PID inexistente ou lock de operação
  stale é removido antes de iniciar a mesa; lock com processo vivo continua
  bloqueando a operação.
- Testes correspondentes adicionados/atualizados em `test_local_service.py`,
  `test_prepare_transfer.py`, `test_manual_review_browser.py` e
  `tests/Test-PortableMenu.ps1`.

## Situação da fundamentação jurídica

- A remodelação está presente na versão nova: a regra publicada é
  `legal-foundation-v2`, com `legal-reference-parser-v2.js`,
  `retirement-legal-profile.js` e `portal-legal-crosswalk.js`.
- O lote correto veio de
  `outputs/Atos-TCE-Professor-IPERN-completo-2026-09-14.zip` e o pacote final
  contém 739 registros e 14.179 PDFs. O contexto salvo em
  `acervo-tce/fundamentos-contexto.v1.json` foi extraído com
  `legal-context-v4`; os estados individuais continuam classificados antes
  de qualquer correspondência automática.
- O lote anterior, que não deve mais ser usado, continha 174 registros e
  3.273 PDFs; ele foi removido das extrações de trabalho.
- No lote correto, 735 registros têm texto operativo, páginas e evidência de
  fonte; 679 estão `complete`, 49 `conflict`, 7 `incomplete` e 4 `missing`.
  Os estados não completos não podem ser tratados como correspondência
  automática.
- O nome `fundamentos-contexto.v1.json` identifica o schema de transporte
  compatível; não significa que a regra jurídica ainda seja a versão antiga.
- A remodelação ainda não equivale à qualificação portal-real: não existe
  `automacao/qualificacao.json`, `real_send_enabled` continua `false` e o
  envio permanece bloqueado até os preflights reais.

## O que falta

1. Repetir observação em sessão humana autenticada e isolada, sem erros de
   rede/console posteriores; a sessão anterior teve 83 eventos, mas terminou
   `BLOCKED`.
2. Executar três preflights portal-reais no escopo correto:
   `ProcessonoSetor.asp`, `source_scope=sector_finalistic`, marcador de valor
   `6189`, identidade processo/interessado exata, catálogo atual e seis campos
   obrigatórios. Gênero continua opcional.
3. Para cada preflight, confirmar preparação reversível, releitura pós-escrita
   e igualdade de identidade, frame, geração, campos e catálogo. Divergência,
   frame stale ou resultado incerto interrompe o fluxo.
4. Com os três preflights verdes, executar — somente mediante autorização
   imediata e específica — um único envio supervisionado, observar o resultado,
   reabrir o ato e confirmar persistência. Sem reenvio automático em timeout.
5. Criar fixture sanitizada do resultado real, gerar
   `automacao/qualificacao.json` vinculado às versões/hashes atuais e validar
   `real_send_enabled` fail-closed. O arquivo ainda não existe no checkout.
6. Executar piloto supervisionado de até cinco atos; só depois considerar ondas
   progressivas e release operacional.

## Artefatos de release local

- Público reconstruído:
  `outputs/tce-processos-completo-portatil-2026-09-16.zip`, 96.226.374 bytes,
  SHA-256 `BC83DADD4D4B6682E3C56A461CDB7D56A0962B4D90BFEB21295B703F681BA145`.
- Fonte preservada do lote correto:
  `outputs/Atos-TCE-Professor-IPERN-completo-2026-09-14.zip`,
  5.845.328.927 bytes.
- Privado final do lote correto:
  `outputs/Atos-TCE-Professor-IPERN-completo-2026-09-16.zip`,
  5.845.389.892 bytes, SHA-256
  `62DB7D92A2663698053CA703C1E3674971A5A0511673710B9C102E4A87D44507`.
- Extração validada:
  `Versions/TCE-Meus-Processos-165-e-Setor-156-Extensao-Reorganizada-2026-09-16-final-professor-ipern`.
  Contém o acervo privado (32.548 arquivos, 14.179 PDFs), `ABRIR-MESA.bat`, ponte, HTML,
  runtime completo e os três módulos legais v2. A auditoria foi executada antes
  do smoke live; o smoke criou estado transitório em `dados-locais` e o serviço
  foi parado depois. O ZIP privado não inclui esse estado (`bridge_state_included=false`).
- Extração pública validada por
  `outputs/tce-processos-completo-portatil-2026-09-16.zip`: auditoria `public`
  sem achados e `TESTAR-PACOTE.ps1` 7/7.

## Limpeza local realizada

- Removidas as cinco extrações antigas (`2026-09-14`, `2026-09-16`,
  `final`, `final-v2` e `public-v2`), todas com o lote antigo de 174/3.273.
- Removidos os dois ZIPs privados antigos e os nove diretórios temporários de
  empacotamento, além do staging de runtime e do `__pycache__`/`debug.log`.
- Removido o `.tmp-live-bridge` depois de confirmar PID inexistente, porta
  fechada, progresso idêntico e SQLite já preservado na extração final.
- Preservados: o ZIP-fonte de 14/09, o ZIP privado final de 16/09, o ZIP
  público, a extração final com 739/14.179, o código-fonte, o workbook
  derivado e os perfis locais de QA.
- Restou uma pasta antiga de staging em
  `outputs/tce-processos-completo-portatil-private-2026-09-16-v2` porque o
  Windows manteve `app`/DLLs em uso por outro processo; o conteúdo do acervo
  antigo já foi removido. Ela pode ser excluída após fechar o processo que
  mantém o handle, sem tocar nos artefatos preservados.

## Migração do estado de trabalho entre versões

Comparação realizada entre
`Versions/TCE-Meus-Processos-165-e-Setor-156-Extensao-Reorganizada-2026-09-14`
e a versão privada
`Versions/TCE-Meus-Processos-165-e-Setor-156-Extensao-Reorganizada-2026-09-16`:

- O estado salvo está em `acervo-tce`; a cópia já foi feita e os arquivos de
  trabalho têm os mesmos hashes nas duas versões.
- O conjunto inclui `processos` (3.273 PDFs; 7.194 arquivos),
  `automacao/execucoes.sqlite3`, `automacao/analises/*.json` e os arquivos
  derivados da raiz: `checkpoint-extracao.json`, `checkpoint.json`,
  `dados-complementar-ato.json`, `complementar-ato.html`, `doc.md`,
  `evidencias-visuais.json`, `fundamentos-contexto.v1.json`,
  `indice-classificado.json`, `indice-local.json`, `colecoes-processos.json`,
  `ordem-portal.json`, `pdfs-alvo-manifest.json`, `progresso.json`,
  `cache-ocr*.json` e `falhas.json`.
- `.workflow-state.lock` é lock transitório e não deve ser migrado; deve ser
  recriado pela versão ativa. `automacao/listas` está vazio no estado atual.
- Não copiar `app`, `runtime`, `extensao-complementar-ato` ou os launchers da
  versão antiga: a versão nova contém as correções. Não copiar
  `dados-locais/bridge/service.json` nem códigos de pareamento; são estado
  efêmero e potencialmente sensível.
- A extração pública não contém `acervo-tce` por desenho. Para preservar o
  trabalho, usar a extração/ZIP privado final do lote correto.
- A cópia do lote correto foi feita a partir do ZIP fornecido pelo usuário;
  a fonte original foi preservada para recuperação.

### Marcações "processo feito" no HTML

- Quando o HTML é aberto pela mesa HTTP (`ABRIR-MESA.bat`), a marcação é
  persistida em `acervo-tce/progresso.json`; `ordem-portal.json` preserva a
  ordem, mas não é a fonte da marcação.
- Quando o HTML é aberto diretamente como arquivo (`file://`) ou em modo
  offline, a marcação fica no `localStorage` do navegador, na chave
  `tce-completed-processes-v1` com o ciclo do acervo. Ela não fica dentro de
  `complementar-ato.html`, `dados-complementar-ato.json` ou nos PDFs.
- A verificação atual encontrou `progresso.json` vazio (`revision: 0`,
  `processes: {}`) tanto na versão 2026-09-14 quanto na 2026-09-16. Portanto,
  eventuais marcações feitas no HTML de outro PC ainda precisam ser
  exportadas do navegador daquele PC ou recuperadas do `progresso.json` que
  existia lá.
- O checkbox `Revisado` da extensão é outro estado: fica no
  `chrome.storage.local` do perfil do Chrome e não é migrado copiando a pasta
  do pacote.

## Pendências de release local

- O release atual está reconstruído e validado offline, mas ainda não é uma
  prova de efeito remoto no portal. A qualificação portal-real continua sendo
  a pendência de conclusão operacional.
- `work/tce-extractor/real_portal_session.py` ainda usa
  `--ignore-certificate-errors`; não usar esse runner para qualificação até
  remover o bypass ou substituí-lo por sessão isolada com certificado válido.
- `verify-project.ps1` não descobre os testes de automação na raiz, pois roda
  `unittest discover -s portable`; os 28 testes adicionais foram executados
  separadamente nesta análise. O gate de release deve incorporá-los ou
  documentar explicitamente essa separação.
- A falha única do verificador amplo (`tests/panel.test.mjs`, confirmação de
  envio automático) precisa ser estabilizada ou classificada como flake antes
  de reportar um gate único verde.

## Limites mantidos

- `autoSubmit=false` e `real_send_enabled=false` continuam sendo a fronteira
  segura até a qualificação real.
- Não usar Chrome pessoal, não digitar credenciais por automação, não publicar
  cookies/tokens/HAR/trace/PDFs e não tratar fixture/ZIP/health como prova de
  efeito remoto.
- Não avançar para conclusão, assinatura, tramitação ou envio sem autorização
  nova, imediata e ato a ato.

## Retomada

Ler este handoff junto de
`docs/notes/2026-09-12-fase4-bloqueio-handoff.md`,
`docs/notes/2026-09-15-qa-final-handoff.md` e
`docs/notes/2026-09-10-plano-consolidacao-main-e-conclusao.md` (Fases 4–7).
Próximo passo: usar a extração `final-professor-ipern` em sessão Chrome isolada com login humano,
repetir a observação e executar apenas os três preflights, mantendo o envio
desligado.
