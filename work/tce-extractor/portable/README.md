# Coletor portátil de processos do TCE/RN

> **Entrega de 12/09/2026 — coleta, extração, HTML e extensão manual.**
> Abra `GUIA-RAPIDO.html` e use a opção **6 — Fluxo completo** de `INICIAR.cmd`.
> Depois importe `acervo-tce\dados-complementar-ato.json` na extensão. Pareamento
> não é necessário para a importação manual. As funções experimentais de
> execução automática descritas adiante estão fora desta entrega; não use
> Iniciar execução, piloto ou conclusão automática. O ZIP limpo não contém
> processos prontos: HTML e JSON são criados após coleta e análise.

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
Para validar o checkout antes de construir o ZIP, use um interpretador de QA
com as versões fixadas em `..\requirements-qa.txt`; essas dependências são de
desenvolvimento e não são instaladas no computador de destino. Veja
`..\QA-DEPENDENCIAS.md`.

## Instalação e uso

1. Extraia o ZIP em caminho curto, por exemplo `C:\TCE-Atos`, de preferência
   fora do OneDrive.
2. Abra `chrome://extensions` → **Modo do desenvolvedor** → **Carregar sem compactação** e selecione a pasta `extensao-complementar-ato`.
3. No outro computador, faça login novamente no e-Contas. Perfis autenticados,
   cookies e credenciais nunca entram no ZIP.
4. Execute `INICIAR.cmd` (ou `INICIAR.bat`) e escolha uma das opções 1–11. A ponte local
   é iniciada antes do menu. Para coletar, deixe **Meus Processos** visível na janela
   do Chrome/Edge e pressione `ENTER`. Use `INICIAR.bat ponte` para iniciar e verificar
   a conexão local sem abrir o menu.

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

Para drenar um lote congelado pela análise da Área Restrita, informe o JSON
persistido e, quando a análise já tiver sido dividida, o número do lote. A
ordem das chaves é preservada e qualquer processo ausente ou duplicado faz a
coleta parar antes do primeiro download:

```powershell
& .\Coletar-Processos-TCE.ps1 `
  -FilaCongelada 'D:\TCE-Atos\dados-locais\automacao\analises\analysis-....json' `
  -NumeroLote 1 `
  -ModoPreparacao progressivo
```

Essa etapa baixa os documentos do e-Contas e, se `-Python`, `-Tesseract` e
`-Tessdata` forem fornecidos, executa a preparação/OCR incremental local. Ela
não abre o formulário de Complementar Ato nem envia atos.

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
preencha os sete campos permitidos, revise e conclua manualmente. Esse é o
modo padrão e seguro:

```text
modalidade
fundamento_legal
data_publicacao_doe
cargo
matricula
data_nascimento
genero
```

Aproximações e empates ficam amarelos. **Divergências** não são sobrescritas sem override individual. No modo manual, a extensão não submete, não limpa, não assina, não tramita e não conclui o ato.

O painel possui as abas **Ato atual**, **Execução** e **Histórico** para separar
conferência, acompanhamento e consulta. A execução automática aceita um
**Marcador do lote**: o worker seleciona o marcador exato no portal, confirma o
resultado, percorre todas as páginas, abre cada processo elegível, seleciona o
interessado e faz preflight dos sete campos antes de congelar a fila. Linhas
sem identidade ou sem ação observável **Complementar Ato** ficam pendentes.

O checkbox **Concluir automaticamente os atos elegíveis** é um opt-in separado
e só fica habilitado quando há serviço, qualificação versionada e observador de
resultado do portal. Nesse modo, cada ato exige intenção persistida, comando
único, releitura e confirmação; timeout ou resultado incerto pausa o lote e não
faz reenvio automático. A versão atual do pacote mantém
`real_send_enabled=false` até a qualificação real, portanto a execução real
continua bloqueada neste checkout. Fechar o painel não retoma a execução.

## HTML, revisão e diagnóstico

O HTML continua disponível. No modo servido pelo helper, **Processo feito** é
gravado no progresso portátil e compartilhado com a extensão. No fallback
`file:`, ele fica salvo somente no navegador. A marcação **Revisado** da
extensão continua sendo um controle separado por interessado; uma marca não
substitui a outra.

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
opção própria do menu: a mesa aberta pelo menu usa uma sessão local temporária
e acompanha as revisões incrementais sem expor caminhos absolutos; o código da
extensão continua sendo informado em **Mesa local**. Pare-o com
`INICIAR.cmd parar`. Se a ponte estiver indisponível, importação manual do JSON
e HTML estático continuam válidos. A pesquisa da extensão por número de
processo ou interessado apenas localiza o registro; a seleção no portal e o
clique **Preencher campos disponíveis** continuam deliberados.

## Fluxo híbrido por marcador e lotes

1. Mantenha a Área Restrita autenticada em **Processos no setor / finalísticos /
   Proc./Doc. Eletrônicos** e selecione manualmente o marcador desejado no próprio
   portal. A extensão lê esse marcador; não é preciso digitá-lo nem importar um
   dataset anterior.
2. **Analisar pendências no portal** percorre todas as páginas em modo somente
   leitura, pausa se origem, marcador ou paginação mudarem e considera pendente
   somente a linha com o ícone vermelho **Complementar Ato**. A prévia congela a
   ordem e **Criar lotes da análise** grava o snapshot em
   `acervo-tce\automacao\analises`.
3. Para a lista autoritativa, use a opção **11 — Analisar lista na Área Restrita e
   baixar em lotes de 300**. O menu importa `Complementar Ato - Professor IPERN.xlsx`
   (ou outro `.xlsx` informado), preserva o original e registra manifesto SHA-256,
   ordem e duplicidades. A extensão percorre o marcador selecionado e consulta por
   número/ano os processos ausentes; somente o controle vermelho semântico
   **Complementar Ato** entra na fila.
4. Após revisar a prévia congelada, confirme **cada lote de até 300** no painel.
   Antes de cada confirmação a ponte reconcilia todas as chaves exatamente no
   e-Contas; ausência ou ambiguidade bloqueia aquele lote. A fila preserva a ordem
   da primeira ocorrência da planilha, e duplicidades aparecem somente no relatório.
   O coletor local baixa documentos, eventos e PDFs com checkpoint e executa
   OCR/preparação incremental.
5. O relatório derivado contém uma linha por linha original da planilha, status da
   Área Restrita, assinatura sanitizada do controle, lote, estado do e-Contas,
   documentos baixados e erro. O fluxo mantém `autoSubmit=false` e não preenche,
   complementa, finaliza, tramita ou envia atos.
   O estado do job fica visível no painel;
   nenhum ato é preenchido ou enviado por essa etapa.
6. Como fallback, a opção **10 — Baixar e preparar OCR de lote congelado** em
   `INICIAR.cmd` lista os snapshots locais e executa o mesmo coletor sem
   substituição de processo. A opção **9 — Verificar ponte local** confirma que
   o serviço loopback está respondendo.

Processos sem documento/OCR entram como `acquisition_pending`: eles contam na
prévia de aquisição e no lote, mas não são apresentados como prontos para
preflight. Identidade ambígua, ausência da ação observada e processos já
complementados ficam fora da fila de aquisição.

Para abrir a mesa entregue no ZIP, primeiro extraia o pacote inteiro e dê duplo
clique em `ABRIR-MESA.cmd` (equivalente a `INICIAR.cmd abrir-mesa`). O iniciador
valida dados, serviço e assets do PDF.js, inicia `/review` por HTTP local e mostra
um erro objetivo quando a extração estiver incompleta. Não abra o HTML diretamente
dentro do ZIP: módulos do PDF.js não são suportados em `file://`.

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
