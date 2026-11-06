# Patch 2.0.2 — Meus Processos e tempos ampliados

Data: 06/11/2026
Versão: 2.0.2
Estado: `PATCH_VERIFIED`

## Problemas corrigidos

1. **Meus Processos não era reconhecida como listagem.**
   - Rota adicionada: `#/dashboard/meus/meus-processos`.
   - A tabela, os links e as classes de status são as mesmas; o painel agora aparece e a pré-visualização funciona.
   - Verificação real no Chrome QA: 25 linhas, **23 pendentes e 2 concluídos**.

2. **Presets de filtro eram compartilhados entre listagens diferentes.**
   - Presets agora usam chave por rota:
     - `complementadorFilterPreset` para `processos-no-setor`;
     - `complementadorFilterPreset:meus-processos` para Meus Processos.
   - O preset antigo continua valendo para a listagem antiga; Meus Processos não é mais esvaziado por ele.

3. **Tempos curtos em máquinas mais lentas.**
   - Leitura/aplicação do lote: 180 s (antes 60 s).
   - Busca documental: 600 s (antes 300 s).
   - Espera de abas: 30 s (antes 10 s).
   - Espera do iframe de Autos: 60 s (antes 30 s).
   - Retry de content script em aba nova: 40 s (antes 20 s).

4. **CORS do PDF em outra máquina.**\n   - O fetch do anexo passou de `credentials: include` para `credentials: omit`; o servidor responde `Access-Control-Allow-Origin: *` e o Chrome bloqueava o modo com credenciais.\n   - Teste real no QA: `omit` retorna 200 e `application/pdf`.\n\n5. **Abas após salvar.**
   - Processos `CONFIRMED` fecham as duas abas de trabalho após o ACK.
   - Revisão, falha e incerteza mantêm as abas para conferência.

## Testes

| Verificação | Resultado |
| --- | --- |
| Unitários | **330 PASS** |
| Navegador | **25 PASS** (inclui painel em Meus Processos) |
| Build / build:test | PASS |
| Verificação real de Meus Processos | 25 linhas, 23 pendentes, 2 concluídos |

## ZIP 2.0.2

- Arquivo: `release/Complementador-eContas-2.0.2.zip`
- Bytes: 645.600
- SHA-256: `3FA30669A3DBBFA663387152F88FE1EBF9AF015888F3E98CB01F6248F5A78D0B`
- Manifesto: 2.0.2
- Extração conferida, 0 divergências.
- Flags funcionais: execução true, salvamento true, fill-only false; o lote só começa com clique explícito.

## Instalação no outro PC

1. Remover/desativar a versão 2.0.0 instalada.
2. Carregar a pasta extraída do `Complementador-eContas-2.0.2.zip`.
3. Confirmar versão 2.0.2 em `chrome://extensions`.
4. Abrir a lista, aplicar o filtro, definir os limites e clicar em “⚡ Rodar automação”.

Se o problema de tempo persistir, registrar o código de erro exibido no painel/diário para diagnóstico específico; não repetir um salvamento incerto.

## Limitações

- A outra máquina não foi acessada diretamente; o patch amplia os limites e corrige a rota, mas a confirmação final é no ambiente do operador.
- Kill físico do service worker e autosave continuam limitações conhecidas.
