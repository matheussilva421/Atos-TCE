# F7 — H2 adaptador: um salvamento real (GATE A)

Data: 05/11/2026
Estado: `H2_ADAPTER_BLOCKED_EXTERNAL_AUTH` / `NOT_RUN`

Este gate é diferente do H2 supervisionado de 05/11/2026. Aqui o clique e a confirmação devem ser feitos pelo runner/adaptador da extensão, com checkpoint, tentativa única e verificação independente. Nenhum salvamento foi executado nesta fase.

## Pré-condições já atendidas

- F1–F6 locais: 323 unitários PASS e 24 navegador PASS em um ciclo.
- Build de QA com salvamento habilitado: `work/qa-save-build-2026-11-05`, background SHA-256 `C69E92C062FE810F3C98F63CF8FDCCAC6F21FC2BE60C5F5EB23537B2A832CBDB`. Não executado.
- Build seguro de distribuição restaurado em `dist` com os três flags falsos.
- Adaptador com diálogo estrutural, revalidação pré-clique, checkpoint `SAVE_PENDING`, `SAVE_UNCERTAIN` sem retry e verificação em aba nova.

## Autorização necessária

O operador deve autorizar expressamente, nesta conversa:

1. Executar **um único ato novo** no Chrome QA.
2. Limite de **1 processo examinado** e **1 salvamento**.
3. Não substituir o alvo se ele ficar inelegível.
4. Não repetir o clique após resultado incerto.
5. Manter o build de distribuição desligado; usar apenas o build de QA preparado.

O processo/ato exato deve ser escolhido pelo operador na interface; não registrar número de processo, nome, CPF, matrícula ou nascimento em logs/evidências.

## Procedimento (somente após autorização)

1. Copiar o build de QA para um caminho novo e carregá-lo no perfil QA; nunca no Chrome profissional.
2. Fazer login manual, aplicar o filtro do operador e selecionar o ato autorizado.
3. Conferir: um único interessado, status pendente, cinco campos preenchidos, sem erro visível e sem divergência.
4. Iniciar o lote com limites 1/1. O runner deve gravar `SAVE_ARMED` antes do clique.
5. Aceitar somente o diálogo homologado: **Complementar ato**, **sim, complementar**, **NÃO**.
6. Verificar em aba nova: rota/processo corretos, formulário renderizado e botão “Complementar ato” ausente.
7. Gravar `CONFIRMED` apenas com essa evidência; caso contrário, `SAVE_UNCERTAIN` e parar.
8. Encerrar o Chrome QA e restaurar o build seguro em `dist`.

## Condições de parada imediata

- Diálogo diferente do homologado, botão ausente/desabilitado, rota ou processo divergente.
- Mais de um interessado, campo faltando, erro visível ou valor divergente.
- Timeout, resposta vazia, falha de storage ou dúvida sobre o clique.
- Qualquer risco de autosave não previsto.

## Resultado

| Item | Valor |
| --- | --- |
| Status | `NOT_RUN` |
| Autorização | ausente |
| Tentativas de clique | 0 |
| Salvamentos confirmados pelo motor | 0 |
| Última evidência | build de QA preparado, não executado |

## Evidência a preencher após o gate

`docs/evidence/batch-h2-adapter.md` deve receber: data, build/hash, resultado `PASS/FAILED/UNCERTAIN`, contador, eventos sanitizados, prova pós-save, riscos e aceite do operador. Não copiar dados pessoais.
