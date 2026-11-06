# Patch 2.0.4 — Meus Processos, CORS e opção de abas

Data: 06/11/2026
Versão: 2.0.4
Estado: `PATCH_VERIFIED`

## Correções e opção

1. **Meus Processos reconhecida como listagem.**
   - Rota `#/dashboard/meus/meus-processos` suportada.
   - Verificação real no Chrome QA: 25 linhas; painel e pré-visualização funcionando.

2. **Presets separados por rota.**
   - `complementadorFilterPreset` para `processos-no-setor`.
   - `complementadorFilterPreset:meus-processos` para Meus Processos.

3. **Tempos ampliados.**
   - Leitura/aplicação: 180 s; busca documental: 600 s; abas: 30 s; iframe: 60 s; retry de content script: 40 s.

4. **CORS do PDF.**
   - Fetch do anexo com `credentials: omit`.
   - Teste real no QA: 200 e `application/pdf`.

5. **Zerar lote.**
   - Botão **Zerar lote** no painel limpa o diário local e reabilita o Iniciar.
   - Recusa zerar quando existe `saveAttemptId` ou `SAVE_UNCERTAIN`, para não perder um salvamento incerto.

6. **Janela fixa.**
   - As abas de trabalho são criadas na janela onde o lote foi iniciado; abrir outra janela no segundo monitor não desvia os processos.

7. **Abas de processos com problema — opção no painel.**
   - Checkbox **“Manter abas de processos com problema”**, marcado por padrão.
   - Marcado: revisão/falha mantêm Autos e Complementar Ato abertos.
   - Desmarcado: as duas abas são fechadas após o processo problemático.
   - `SAVE_UNCERTAIN` sempre mantém as abas, independentemente da opção.
   - `CONFIRMED` sempre fecha as duas abas.
   - A preferência é persistida em `chrome.storage.local` e aplicada no início do lote.
- As abas de Autos/Complementar Ato são criadas na janela onde o lote foi iniciado; abrir outra janela no segundo monitor não desvia mais os processos.

## Testes

| Verificação | Resultado |
| --- | --- |
| Unitários | **337 PASS** |
| Navegador | **25 PASS** |
| Verificação do checkbox no QA | começa marcado; desmarcar e recarregar mantém a escolha |

## ZIP 2.0.4

- Arquivo: `release/Complementador-eContas-2.0.4.zip`
- Bytes: 646.605
- SHA-256: `817A8D3B2B55E3A85967A555255C2B9A548522BF11685F62983DC62B73A0D8A3`
- Manifesto: 2.0.4
- Extração conferida, 0 divergências.
- Flags funcionais: execução true, salvamento true, fill-only false; o lote só começa com clique explícito.

## Instalação no outro PC

1. Remover/desativar a versão anterior.
2. Carregar a pasta extraída do `Complementador-eContas-2.0.4.zip`.
3. Confirmar versão 2.0.4 em `chrome://extensions`.
4. Aplicar o filtro, definir os limites e iniciar explicitamente o lote.
5. Ajustar o checkbox de abas problemáticas antes de rodar.

## Limitações

- A outra máquina não foi acessada diretamente; o patch amplia os limites e corrige CORS/rota, mas a confirmação final é no ambiente do operador.
- Kill físico do service worker e autosave continuam limitações conhecidas.
