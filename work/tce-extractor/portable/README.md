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

Em cada coleta, `-ModoPreparacao progressivo` (padrão) analisa e publica cada
processo assim que seus documentos são sincronizados; `-ModoPreparacao completo`
faz a mesma preparação por processo depois da varredura e só então abre a mesa
no fluxo completo. Com a mesa local pareada, o painel da extensão consulta as
revisões incrementais e atualiza o dataset sem preencher campos. O HTML aberto
como arquivo continua sendo o fallback estático e não recarrega sozinho.
`-MaxDownloads` aceita somente 1 ou 2 e limita os workers de download em
runspaces; hash, deduplicação, versões e checkpoint continuam no coordenador
único. O token de sessão é passado somente em memória ao worker e nunca entra
no acervo, logs ou ZIP.

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

Quando uma página escaneada exige OCR, a classificação grava `cache-ocr.json` e
o cache separado `cache-ocr-geometria.json`. Texto e caixas daquele passe são
reutilizados pelo batch quando o hash do PDF, a versão geométrica e o runtime
OCR coincidem; cache antigo ou incompatível não é tratado como geometria válida.

A mesa mostra a Resolução, a Guia e outros eventos em páginas completas. Quando
os assets locais estão disponíveis, usa o viewer PDF.js fixado no manifesto de
dependências e sobrepõe somente retângulos de evidência que tenham documento,
hash e página resolvidos; em `file:` ou navegador restrito, retorna ao iframe
nativo e ao botão **Abrir PDF**. Clicar numa fonte nunca altera o formulário.

O serviço local opcional fica somente em `127.0.0.1`, usa código temporário de
pareamento e mantém tokens em memória/sessão. Para usá-lo, inicie o helper pela
opção própria do menu, informe o código em **Mesa local** na extensão e pare-o
com `INICIAR.cmd parar`. Se a ponte estiver indisponível, importação manual do
JSON e HTML estático continuam válidos. A pesquisa da extensão por número de
processo ou interessado apenas localiza o registro; a seleção no portal e o
clique **Preencher campos disponíveis** continuam deliberados.

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
