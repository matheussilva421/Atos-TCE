# Candidato local de release — automação em lote

Data: 05/11/2026
Estado: `LOCAL_CANDIDATE` / `H1_INCOMPLETE` / `H2_NOT_RUN` / `H3_NOT_RUN` / `G7_PENDING`

Este documento prepara a entrega (T24) sem publicar, instalar em perfil profissional ou declarar homologação. A versão do manifesto permanece 0.1.1.

## Build candidato (dist)

| Arquivo | Bytes | SHA-256 |
| --- | --- | --- |
| manifest.json | 1.196 | `08F88EA93CFF23F23EC19A7A4C0DB6F1BC18EC79CAC9D54D55C4698E084E5B35` |
| background.js | 105.309 | `C037F721572DA854FC3DFD16DC3C36CDAF1029CB7F9A4DCF351F018346E86EB7` |
| form-content.js | 48.298 | `6BAAB8E748DB07F01F380B021DE6F5CBD844924115FD86753E9C55613C93C9F6` |
| autos-content.js | 981.945 | `11C81C7EFACFBA1D3884DAB48E7C088895750F2E6FF24916A81C333617280E96` |
| list-content.js | 20.236 | `EBBE0E02C466BD9BAA31469D39C379986D09AB6BAE520F220F45E03067D6FC0F` |
| vendor/pdf.worker.mjs | 1.417.586 | `BD88805178A26C729DB8C0107A5B630CB900EC070F4D8C7529A3E45530AFD41D` |

## Backup e ensaio de rollback

- Backup imutável: `work/batch-baseline-2026-11-05` (59 arquivos de fonte/configuração + 5 do build v0.1.1).
- Inventário `SHA256SUMS.txt`: 64 hashes verificados nesta data, **0 divergências**.
- Restauração: desligar a extensão candidata, apontar para a pasta restaurada do backup e recarregar. Nenhum perfil profissional foi tocado no ensaio.
- Limite conhecido: reverter código não desfaz ato já gravado no e-Contas; reversão institucional segue o procedimento oficial.

## Instalação do candidato (quando autorizada)

1. Gerar/extrair o pacote apenas em diretório local de homologação.
2. Abrir `chrome://extensions`, ativar modo desenvolvedor, carregar a pasta extraída.
3. Confirmar que a versão exibida é 0.1.1 e que o painel aparece apenas na listagem de processos.
4. Manter `BATCH_EXECUTION_ENABLED = false` até a validação do fluxo por processo e a autorização de H2.

Política institucional pode bloquear extensões não empacotadas; nesse caso, a instalação depende de aprovação interna e não deve ser contornada.

## O que não está homologado

- Fluxo de lote por processo em navegador (documentos, interessado, cinco campos e readback).
- Salvamento real (H2) e lote real (H3).
- Reinício de navegador e suspensão real do service worker.
- Revalidação da rota de Autos no QA desta sessão.

`REAL_SAVE_NOT_TESTED`. Este candidato não deve ser tratado como release aprovado.
