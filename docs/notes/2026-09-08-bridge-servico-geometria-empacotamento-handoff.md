# Handoff — bridge, serviço, geometria e empacotamento — 08/09/2026

## Resumo

Continuação da execução do plano `2026-09-08-fluxo-portatil-plano-implementacao.md` no checkout compartilhado. Três subagentes Luna xhigh auditaram, em escopos separados, bridge/estado, serviço/empacotamento e testes. A integração foi revisada no agente principal.

Foram corrigidos quatro pontos concretos:

- envelopes e erros do bridge agora são validados antes de chegar ao painel; o timeout não depende de `fetch` respeitar `AbortSignal`;
- importação incremental preserva `Revisado` por processo/interessado, enquanto importação manual continua limpando o legado;
- encerramento do serviço libera o lock de estado, e falha de porta/runtime retorna modo manual sem exceção não tratada;
- palavras nativas do PDF são transformadas para coordenadas da página exibida considerando CropBox e rotação 0/90/180/270.

Também foram endurecidos o schema de `ordem-portal.json`, a origem `chrome-extension` aceita pelo pareamento e a auditoria/empacotamento do acervo completo.

## Arquivos alterados neste bloco

- `work/tce-extractor/portable/extensao-complementar-ato/background/service-worker.js`
- `work/tce-extractor/portable/extensao-complementar-ato/lib/bridge-client.js`
- `work/tce-extractor/portable/extensao-complementar-ato/lib/messages.js`
- `work/tce-extractor/portable/extensao-complementar-ato/sidepanel/panel.js`
- testes Node correspondentes de bridge, painel e service worker;
- `portable/app/bridge_auth.py`, `archive_index.py`, `evidence_geometry.py`, `local_service.py`, `package_audit.py`, `prepare_transfer.py`;
- `package_complete_archive.py`, `Empacotar-Acervo-Completo.ps1`;
- testes Python de estado/serviço/geometria/transferência/auditoria/pacote.

Nenhum PDF, credencial, perfil de navegador ou acervo pessoal foi alterado.

## Verificação executada

| Comando | Resultado |
|---|---:|
| `C:\Python314\python.exe -m unittest discover -s . -p 'test_*.py' -q` | 276 pass, 0 fail, 5 skips |
| `node --test` em `portable/extensao-complementar-ato` | 124 pass, 0 fail |
| `node --test` em `portable/app/web` | 4 pass, 0 fail |
| `tests/Test-TcePortable.ps1` | 114 pass, 0 fail |
| `tests/Test-PortableMenu.ps1` | 74 pass, 0 fail |
| `tests/Test-PortableReset.ps1` | 31 pass, 0 fail, 1 skip ambiental |
| `test_extension_zip_packager.py` | 1 pass, 0 fail |
| `git diff --check` | limpo |

Os skips são ambientais/fixture; não constituem validação de OCR real, portal, bridge em navegador real ou segundo computador. A suíte Python também imprime warnings esperados de `ResourceWarning` ao testar respostas HTTP de erro e a ajuda de CLI em um caso negativo; terminou com código 0.

## Artefato entregue

ZIP somente da extensão, regenerado depois das mudanças do bridge:

- caminho: `artifacts/extensao-complementar-ato-2026-09-08-v5.zip`
- tamanho: 34.364 bytes
- SHA-256: `4CA334FECA7483B44429C12C6A6DFAAB126202F03D64F3296B3463F33B019E98`
- entradas: 11, todas sob `extensao-complementar-ato/`
- CRC: verificado
- não inclui `package.json`, testes, `docs`, `work`, credenciais ou acervo

O v4 foi preservado. O v5 é o pacote que corresponde ao source atual.

## Status do GitHub

- branch: `main`
- base antes deste bloco: `ffc6c08 docs: record retry auth verification`
- `origin`: inexistente; push não foi possível nem foi simulado
- commit deste bloco: `e041a93 feat: harden portable bridge and package validation`
- checkout verificado limpo em `main`; não há `origin`, portanto nenhum push foi executado

## Pendências de release

O resultado permanece candidato integrado, não release validada. Faltam gates que exigem ambiente/autorização humana:

1. QA manual no Chrome/Área Restrita com login real, somente leitura e preenchimento autorizado; nunca enviar/finalizar ato;
2. benchmark dos mesmos 20 processos, incluindo mediana/p95 de sincronização e cliques;
3. teste do ZIP extraído em ambiente sem Python/Node no `PATH`;
4. o gate de segundo PC foi dispensado explicitamente pelo usuário e não faz parte desta entrega;
5. screenshot de PDF completo com evidência alinhada, mantido fora do Git por possível dado pessoal;
6. confirmar versão/hash de runtime portátil e Tesseract no pacote de distribuição final;
7. a drenagem agora é cooperativa: `prepare_transfer.py` publica pedido, aguarda marcadores ativos até 60 s e só então cria o ZIP; falta validar esse protocolo contra uma coleta real e gerar o pacote com acervo privado disponível.

## Atualização de continuação — segurança, drenagem e mesa — 08/09/2026

- `BridgeAuth.validate` exige a origem exata registrada; bearer sem `Origin` não é aceito.
- A sessão HTML emite CSRF separado, mantém a sessão em cookie HttpOnly, exige Origin local exata nas mutações e o HTML envia `X-CSRF-Token`.
- `POST /api/v1/selection` valida `tab_id >= 0`, `frame_id >= 0`, `sequence > 0`, rejeita booleanos como inteiros e retorna a sequência descartada quando recebe mensagem antiga.
- O exportador bloqueia explicitamente duas pessoas distintas com a mesma normalização (`interested identity collision`), exigindo seleção explícita antes da sincronização.
- `review-app.js` é instalado pelo HTML servido e `review.css` é carregado como asset real; o fallback inline continua somente para o modo `file:`.
- A transferência usa `transfer-request.json`, pausa novos escritores, espera o marcador ativo desaparecer e falha sem ZIP se o timeout for atingido. O coletor verifica a solicitação entre processos; o serviço recusa iniciar durante a pausa.

Testes deste bloco: 284 Python pass, 5 skips; 5 testes web JS pass; 114 TCE PowerShell pass; 74 Menu PowerShell pass. Não há `origin` configurado para push.

## Retomada

1. Reexecutar `git status --short --branch` e revisar o diff documental.
2. Atualizar os checkboxes do plano apenas para gates locais evidenciados; manter os gates externos desmarcados.
3. Executar `git diff --check`, as suítes acima e uma auditoria final do v5.
4. O commit local já existe como `e041a93`; não tentar push enquanto `origin` não existir.
5. Se houver autorização para QA real, parar no checkpoint antes de qualquer envio/finalização e registrar evidência sanitizada.
