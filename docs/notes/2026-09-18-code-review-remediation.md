# Remediação da revisão de código (CR-01 → CR-26)

**Data:** 2026-09-18 · **Branch:** `codex/mesa-local-refactor`

Este documento é o recibo das correções pedidas em
`docs/2026-09-18-atos-tce-code-review-ai-remediation.md`. Cada linha traz o
commit que fechou o item e os testes que o provam.

O que **não** foi executado, por desenho: os gates reais de M2, M3 e M5 (portal
autenticado + operador), a retirada do legado, a limpeza destrutiva por recibo,
a escolha do disco externo de arquivamento e o merge para `main`.

## Fase A — portal e preenchimento

| CR | Correção | Commit | Testes |
|---|---|---|---|
| CR-01 | `OPEN_ACT` só prova a navegação; a identidade autoritativa continua sendo a do `READ_FORM` | `1f02f5e` | `tests/test_fill_service.py` (OPEN_ACT de list/interested/form sem identidade avança; outcome desconhecido bloqueia; identidade observada divergente bloqueia; nenhuma escrita antes do READ_FORM validado) |
| CR-02 | Roteador orientado a molduras: enumeração por `webNavigation`, mensagens com `frameId`, ambiguidade bloqueia | `a732548` | `extension/tests/router.test.mjs` (scan usa a moldura de lista; duas listas recusadas; READ_FORM ignora formulário de outro ato; duas molduras iguais bloqueiam; FILL_FORM escreve em uma única moldura; moldura que desaparece tem retry limitado) |
| CR-03 | `FILL_FORM` nunca escolhe aba/moldura pelo primeiro booleano: localiza a identidade exata antes de escrever | `a732548` | `extension/tests/router.test.mjs` (escrita em exatamente uma moldura; sem moldura confirmada, zero escritas) |
| CR-04 | Fallback manual preso à aba ativa da janela atual | `a732548` | `extension/tests/router.test.mjs` (aba ativa sem formulário + outra aba com formulário bloqueia; dois formulários na aba ativa bloqueiam; aba fora do portal bloqueia) |
| CR-05 | Preenchimento em duas fases: valida tudo antes de escrever | `a732548` | `extension/tests/fill-form.test.mjs` (campo posterior inválido → `writeCount == 0` em todos; opção indisponível; controle ausente) |
| CR-14 | Varredura congela escopo, marcador, papel e paginação da primeira página | `a732548` | `extension/tests/router.test.mjs` (setor, marcador, papel e página repetida abortam; fluxo normal congela o contexto) |

## Fase B — bridge e comandos

| CR | Correção | Commit | Testes |
|---|---|---|---|
| CR-06 | Comando `CLAIMED` tem lease: token de claim, prazo e limite de tentativas (schema v6) | `605af03` | `tests/test_area_scan.py` (worker morto devolve o comando; dois pollers não recebem o mesmo lease; tentativas esgotadas → `FAILED`) |
| CR-07 | Resultado só conclui com o claim correto: ownership e token conferidos na mesma transação | `605af03` | `tests/test_area_scan.py`, `tests/test_api_server.py` (token velho → 409; outro cliente → 403; replay → 200 `replayed` sem segundo scan) |
| CR-08 | Payload malformado não vira sucesso: contrato por tipo de comando | `605af03` | `tests/test_api_server.py` (`{}`, `ok:"true"`, `ok:1`, role inválida, FILL_FORM sem `field_results` → 400 e workflow parado) |
| CR-09 | Ação da Mesa para reparear a extensão (revoga clientes e emite novo código) | `605af03` | `tests/test_bridge.py` (reset revoga, token antigo deixa de funcionar, novo token pareia e sobrevive a restart) |
| CR-10 | Token só vale na origem pareada; GET de service worker sem `Origin` usa o ID confiável declarado no cabeçalho | este bloco | `tests/test_bridge.py` (origem diferente → 401; sem origem e sem ID confiável → 401; ID confiável sem origem → 200; ID não confiável → 401) |

## Fase C — jobs e e-Contas

| CR | Correção | Commit | Testes |
|---|---|---|---|
| CR-11 | Retomada de job pausado por login ou interrompido, sem repetir o que já foi baixado | `79b1290` | `tests/test_econtas_acquisition.py` (resume continua; lote concluído não repete; resume concorrente e status errado recusados), `tests/test_api_server.py` (rota `POST /api/v1/jobs/<id>/resume`) |
| CR-12 | Recuperação de estado na abertura: comandos, jobs e análise interrompida | `79b1290` | `tests/test_econtas_acquisition.py` (claim devolvido à fila; job vira `INTERRUPTED` e itens voltam a `QUEUED`; `DOWNLOADED` sobrevive; pausa de login continua retomável; `ANALISANDO` vira `ERRO` com evento; recuperação idempotente) |
| CR-13 | Recibo por processo vindo do coletor promovido; só recibo positivo + arquivos vira `DOWNLOADED` | `79b1290` | `tests/test_econtas_acquisition.py` (arquivo parcial + recibo de falha não vira download; reutilizado positivo vira; positivo sem arquivos falha; chave sem recibo nunca vira; chave fora do lote reprova o lote), `tests/test_promoted_equivalence.py` (regiões RECIBO documentadas) |

O motor promovido (`app/econtas/runtime/`) passou a ser versionado em
`0efde07`: ele era ignorado por `**/runtime/` e um clone rodaria um coletor
diferente do revisado.

## Fase D — armazenamento

| CR | Correção | Commit | Testes |
|---|---|---|---|
| CR-15 | Auditoria recalcula o SHA de cada blob canônico e de cada cópia externa; corrupção não conta como preservação | `a4f2dac` | `tests/test_storage_audit.py` (blob com bytes de outro sha não preserva; bytes certos preservam; cópia externa do mesmo tamanho com bytes errados não preserva; modo rápido nunca afirma verificação) |
| CR-16 | Apply revalida o canônico por hash e compara um fingerprint forte do candidato com o recibo | `a4f2dac` | `tests/test_cleanup_storage.py` (árvore que mudou de conteúdo mantendo o tamanho é recusada; blob canônico corrompido depois da auditoria bloqueia; recibo sem verificação de hash não autoriza remoção) |
| CR-17 | Auditoria abre o banco em modo somente leitura e nunca migra | `a4f2dac` | `tests/test_store.py` (schema atual abre; schema antigo é recusado sem migrar; banco ausente é reportado) |
| CR-18 | Backup guiado pelos SHAs referenciados; cópia externa entra no ZIP no caminho canônico | `eb41b16` | `tests/test_backup.py` (blob só externo entra; cópia externa corrompida aborta; SHA referenciado sem cópia aborta; duas cópias geram uma entrada) |
| CR-19 | `scripts/restore-backup.py`: dry-run, validação de manifest/CRC/DB/blobs, bloqueio de path traversal, publicação atômica e reconciliação | `eb41b16` | `tests/test_backup.py` (round-trip completo; dry-run não escreve; destino não vazio exige flag e é movido, não apagado; blob divergente, membro com `..`, backup sem manifest e ZIP truncado recusados) |
| CR-20 | Arquivo híbrido em duas fases: prepara e verifica tudo antes de publicar | `dda0bcc` | `tests/test_archive_manager.py` (falha no segundo SHA deixa ambos HOT, com visões intactas e sem bytes no destino; arquivamento bem-sucedido não deixa staging) |
| CR-21 | Reconciliador distingue presente/verificado/corrompido e conta corrupção | `dda0bcc` | `tests/test_archive_manager.py` (blob local corrompido não é HOT; blob íntegro continua HOT; cópia externa corrompida não conta como ARCHIVED) |
| CR-22 | `scripts/configure-archive.py` valida caminho absoluto, fora de data/dist/tmp, com sonda de escrita, antes de persistir; Mesa mostra o status | `dda0bcc` | `tests/test_configure_archive.py` (caminho válido persiste e não deixa sonda; relativo, dentro de data, dist e tmp recusados; nada é persistido quando a validação falha) |
| CR-23 | `replace_documents` reconcilia por `(process_id, source_id)`: ids estáveis, evidência preservada e perda registrada | `a4f2dac` | `tests/test_store.py` (id e `fields.document_id` sobrevivem à atualização; documento novo não mexe nos antigos; remoção referenciada vira evento + `REVISAR`; remoção não referenciada é silenciosa) |
| CR-24 | Erro de PDF distingue arquivado (409, restaure) de ausente (410) e de arquivo indisponível | `a4f2dac` | `tests/test_api_server.py` (documento arquivado → 409 com instrução; MISSING → 410) |

## Fase E — infraestrutura e documentação

| CR | Correção | Commit | Testes |
|---|---|---|---|
| CR-25 | GitHub Actions com os gates offline em Windows | (este commit) | o próprio workflow; nada nele depende de dados privados |
| CR-26 | Handoff consolidado em uma tabela por marco + este recibo | (este commit) | revisão documental; `Test-DocumentationTracking` do gate legado continua verde |

## O que continua bloqueado no humano

## Gates offline executados no fechamento (2026-09-18)

| Gate | Comando | Resultado |
|---|---|---|
| Suíte Python da raiz | `python -m unittest discover -s tests -p 'test_*.py' -q` | 552 testes, 552 aprovados, 0 falhas |
| Suíte da extensão | `cd extension && npm test` | 107 testes, 107 aprovados |
| Suíte web da Mesa | `node --test app/web/tests/*.test.mjs` | 15 testes, 15 aprovados |
| Contrato do pacote | `python -m unittest tests.test_packaging_contract -v` | 82 executados, 80 aprovados, 2 pulados |
| Gate do projeto (legado) | `work/tce-extractor/verify-project.ps1` | 7 estágios verdes, 1254 executados, 1252 aprovados, 0 falhas, 2 pulados |
| Higiene | `git diff --check` | limpo |

Pacote reconstruído e promovido: `dist/Atos-TCE-portable.zip`, 96.112.921 bytes,
SHA-256 `b8bab47451b53cf7f318cc7689b850439bb6385acf7da846665a06d29089fbb1`,
509 entradas, 430 arquivos de runtime conferidos, sem acervo. O smoke de
extração limpa passou; o `verify-package.ps1` só falhou em seguida, ao tentar
remover a pasta de extração, porque o processo Python do smoke continuou vivo
segurando `libcrypto-3.dll` (artefato do terminal desta sessão). Rodado de novo
com `-SkipSmoke`, o verificador fecha com código 0 e o mesmo hash. A rotação
deixou o build novo como atual e o anterior como `.previous.zip`.

| Gate | Por quê |
|---|---|
| M2 real (varredura extensão × CDP) | exige login humano na Área Restrita |
| M3 real (download limitado) | exige e-Contas autenticado e processos pendentes |
| M5 real (preenchimento supervisionado) | exige portal aberto e conferência humana; o clique final é do operador |
| Retirada do legado (M6 4, 5 e 7) | exige os três gates acima, tag `pre-legacy-retirement` com backup remoto e autorização explícita |
| Limpeza por recibo | exige auditoria verificada por hash e autorização explícita |
