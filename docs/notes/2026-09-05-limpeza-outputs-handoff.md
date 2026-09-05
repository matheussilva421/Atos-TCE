# Limpeza de outputs — 2026-09-05

## Pedido e resultado

Manter somente o pacote mais novo. Removidos permanentemente 26 itens de outputs (pastas de pacotes/extrações, ZIPs antigos e respectivos SHA256): 13.990.135.415 bytes, aproximadamente 13,03 GiB. Relatórios, evidências e handoffs pequenos preservados.

Mantido: `outputs/TCE-Acervo-Atualizado-227-2026-09-05.zip` (1.737.402.229 bytes). Outputs ficou com 1.740.989.523 bytes, aproximadamente 1,62 GiB.

## Segurança e verificações

- ZIP: CRC integral aprovado, 10.256 entradas; SHA256 conferido antes e depois da limpeza: `a621791800a24ab6292b755d473aef6b3f407e167a4bf4beb8272acb68ff1720`.
- Alvos validados como filhos diretos de outputs; nenhum reparse point permitido; enumeração recursiva sem falhas.
- Confirmado que não restaram pastas de extração nem outros ZIPs em outputs.
- Código, testes, work e tmp não foram alterados. Não houve alteração de comportamento; suíte de aplicação não executada nesta limpeza.
- Exclusão sem Lixeira. O pacote atual continua recuperável por extração do ZIP mantido; versões históricas excluídas não podem ser restauradas por Git.

## Registro e continuidade

Manifesto gerado antes da remoção: `C:\Users\slvma\Documents\Codex\2026-09-02\g-2\cleanup-outputs-manifest.json`. Script operacional no mesmo diretório: `cleanup-outputs.ps1`.

Git: árvore limpa antes desta documentação; commit local deste handoff. Nenhum remote configurado, portanto sem push ao GitHub.

Pendências: nenhuma para a limpeza solicitada. Para uso portátil, extrair o ZIP mantido. Não limpar work/tmp sem nova autorização e análise de dependências.
