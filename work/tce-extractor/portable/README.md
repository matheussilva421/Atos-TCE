# Coletor portátil de processos do TCE/RN

Para começar sem precisar conhecer os arquivos técnicos, abra
`GUIA-RAPIDO.html`. A mesma orientação está disponível em texto no arquivo
`GUIA-RAPIDO.md`.

O pacote enumera dinamicamente os processos de **Meus Processos Finalísticos**,
permite selecionar o que será coletado e sincroniza eventos e documentos. Não
há quantidade fixa de processos codificada.

## Requisitos

- Windows 10 ou 11;
- Windows PowerShell 5.1 ou PowerShell 7;
- Google Chrome ou Microsoft Edge;
- acesso ao e-Contas e à rede do TCE quando a coleta exigir autenticação.

Python e Tesseract já vêm no runtime; Node.js não é necessário. Não instale componentes no
computador de destino. `TESTAR-PACOTE.ps1` faz a verificação offline sem login.

## Instalação e uso

1. Extraia o ZIP em caminho curto, por exemplo `C:\TCE-Atos`, de preferência
   fora do OneDrive.
2. Abra `chrome://extensions` → **Modo do desenvolvedor** → **Carregar sem compactação** e selecione a pasta `extensao-complementar-ato`.
3. No outro computador, faça login novamente no e-Contas. Perfis autenticados,
   cookies e credenciais nunca entram no ZIP.
4. Execute `INICIAR.cmd` e escolha uma das opções 1–8. Para coletar, deixe
   **Meus Processos** visível na janela do Chrome/Edge e pressione `ENTER`.

Seleções aceitas:

```text
1,4,8-12            baixa os itens 1, 4 e 8 até 12
todos               baixa todos os processos exibidos
novos               baixa apenas os que não estão concluídos no checkpoint
buscar magnolia     filtra a lista; depois escolha pelos novos números
```

## Checkpoint e processos novos

Terminou o acervo inteiro? A opção **8 — Zerar acervo e iniciar novo lote** pede
confirmação, guarda o acervo anterior em `backups-acervo` e inicia coleta,
análise, HTML e JSON novos. Os backups ficam locais e não entram no ZIP seguinte.
O novo ciclo começa com checks de HTML separados; importe o JSON novo na extensão
para substituir o lote e limpar as marcas Revisado. Scripts/runtime/login ficam
preservados. Se falhar depois do reset, retome pela opção **6**, sem zerar de novo.

Use `novos` para recortar o lote atual. `-BaseConcluidos` aceita um checkpoint,
um diretório de acervo ou um ZIP privado anterior. A base é combinada com o
checkpoint do destino e, por padrão, somente processos completos são excluídos.

`-BaselineAllComplete` deve ser informado explicitamente junto com
`-BaseConcluidos` quando toda a base tiver sido conferida como concluída; ele não
é implícito e não completa o checkpoint parcial do destino.

```powershell
& .\Coletar-Processos-TCE.ps1 -Selecao 'novos' -BaseConcluidos 'D:\TCE-Base\checkpoint.json'
```

## Análise local e Complementar Ato

O fluxo é: coletar `novos` → analisar localmente → usar a ação 4 para
atualizar somente `acervo-tce\dados-complementar-ato.json` → importar esse
**único JSON** uma vez no painel quando o lote mudar. Ele atende todo o lote,
não um arquivo por processo.

Na Área Restrita, abra **Complementar Ato**, confira processo e interessado,
preencha os sete campos permitidos, revise e conclua manualmente:

```text
modalidade
fundamento_legal
data_publicacao_doe
cargo
matricula
data_nascimento
genero
```

Aproximações e empates ficam amarelos. **Divergências** não são sobrescritas sem override individual. A extensão não submete, não limpa, não assina, não tramita e não conclui o ato.

## HTML, revisão e diagnóstico

O HTML continua disponível. Seu check é independente da marcação **Revisado**
da extensão; revisar um formato não marca o outro.

`TESTAR-PACOTE.ps1` verifica offline Python/Tesseract, idiomas `por`, `eng` e
`osd`, manifest e todos os arquivos declarados, permissões exatas, ausência de
dependência de Node e o JSON quando `acervo-tce` existir. Sem acervo, o auditor
roda em `public`; com acervo, em `private`.

## Segurança, privacidade e limites

- O coletor consulta e baixa; não envia atos ao TCE.
- URLs temporárias, tokens, cookies e perfis autenticados não entram no ZIP
  público.
- Dados pessoais existem no ZIP privado e no JSON
  `acervo-tce\dados-complementar-ato.json`; não publique nem compartilhe fora
  do ambiente autorizado.
- O ZIP completo exclui cookies e o perfil autenticado; no outro PC é preciso
  fazer login novamente.
- O portal pode mudar a tela ou as APIs; o pacote não contorna CAPTCHA,
  bloqueios de rede ou autenticação. A decisão e a conclusão do ato permanecem
  manuais.

Se a enumeração retornar zero, confirme que a lista terminou de carregar. Para
uma verificação offline, execute `TESTAR-PACOTE.ps1`; a opção 7 diagnostica o
runtime empacotado.
