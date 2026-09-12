# Coletar processos, extrair dados e conferir

Pacote portátil TCE/RN — 12/09/2026. Fluxo manual, sem automação de atos.

## Primeiro uso

1. Extraia o ZIP inteiro em uma pasta curta, por exemplo C:\TCE-Atos. Não execute dentro do ZIP.
2. Abra INICIAR.cmd e escolha **6 — Fluxo completo**.
3. Siga a orientação do coletor, faça login no e-Contas no navegador indicado e deixe **Meus Processos Finalísticos** carregado.
4. Escolha os processos: `todos`, `novos`, ou posições como `1,4,8-12`.
5. Aguarde a coleta dos documentos, extração/OCR, geração do HTML e do JSON da extensão.
6. Confira a tela aberta pelo menu. Para reabrir depois, use **INICIAR.cmd → 5 — Abrir HTML**.

Python, OCR Tesseract e português estão incluídos. É necessário Windows 10/11 com PowerShell e Chrome/Edge. O login é feito por você; não acompanha o ZIP. O pacote começa sem acervo. Para verificar os arquivos antes do uso, clique com o botão direito em TESTAR-PACOTE.ps1 e escolha Executar com PowerShell.

## Uso diário: uma etapa por vez

| Opção do INICIAR.cmd | Ação |
| --- | --- |
| 1 | Coletar os processos escolhidos |
| 2 | Analisar os documentos já baixados |
| 3 | Gerar/atualizar o HTML local |
| 4 | Atualizar o JSON da extensão |
| 5 | Abrir o HTML existente |
| 6 | Fazer o fluxo completo |
| 7 | Conferir Python e OCR |

Não use a opção 8 para retomar uma coleta: ela inicia um novo lote. Para continuar, use 6 e a seleção adequada; o checkpoint permite reaproveitar o que já foi processado.

## Usar a Extensão

1. Abra `chrome://extensions`, ative Modo do desenvolvedor e clique em Carregar sem compactação.
2. Selecione a pasta `extensao-complementar-ato` do pacote extraído.
3. Na Área Restrita, abra manualmente Complementar Ato e selecione o interessado.
4. Abra o painel da extensão e use Importar/Atualizar dados para escolher `acervo-tce\dados-complementar-ato.json`.
5. Clique em Atualizar prévia. Confira processo, interessado, valores e fontes.
6. Use Preencher campos disponíveis e revise no próprio formulário. Opções aproximadas, empates ou divergências exigem sua conferência.
7. Qualquer conclusão/envio no portal fica a seu cargo.

Um JSON atende o lote inteiro. Importe novamente após atualizar os dados. A importação manual não precisa de código de pareamento nem de ponte local. Se o iniciador exibir um código, ele é opcional para este fluxo. Não use os controles de execução automática, piloto ou conclusão automática.

## HTML local e arquivos importantes

- `acervo-tce\processos`: documentos coletados.
- `acervo-tce\complementar-ato.html`: conferência dos dados e fontes.
- `acervo-tce\dados-complementar-ato.json`: lote para importar na extensão.
- `extensao-complementar-ato`: extensão para Chrome/Edge compatível.
- `TESTAR-PACOTE.ps1`: verificação offline do pacote.

Para ver o PDF dentro da tela, abra pelo **INICIAR.cmd → 5**. O iniciador serve os arquivos neste computador; isso não executa automação no portal e não exige pareamento da extensão. Abrir o HTML diretamente com duplo clique pode bloquear o PDF.js no navegador. Mantenha as pastas `app` e `acervo-tce` juntas. Se o visualizador não carregar, use Abrir PDF. Os documentos originais não são alterados. Após a coleta, a pasta passa a conter dados pessoais: não publique o acervo.

## Diagnóstico

Execute TESTAR-PACOTE.ps1. A extensão no modo manual não envia atos: ela preenche campos para sua revisão.
