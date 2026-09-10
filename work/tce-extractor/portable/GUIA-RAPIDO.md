# Guia rápido do pacote portátil TCE/RN

Este pacote baixa os eventos e arquivos dos processos selecionados, analisa os
documentos localmente, monta o HTML de conferência e fornece uma Extensão do
Chrome para auxiliar no preenchimento de sete campos do **Complementar Ato**.

> Segurança: o modo padrão consulta, organiza e preenche para revisão, mas
> **não envia**, não assina, não tramita e não conclui atos. A conclusão
> automática é um opt-in separado, condicionado a qualificação real e
> observação do resultado do portal; esta versão mantém o envio real bloqueado.
> Confira tudo antes de usar os dados no portal. O ZIP privado contém dados
> pessoais e não deve ser publicado.

## Comece aqui

1. Extraia o ZIP inteiro em uma pasta curta, como `C:\TCE-Atos`.
2. Não execute os arquivos diretamente de dentro do ZIP.
3. Abra `TESTAR-PACOTE.ps1` com o PowerShell para verificar a integridade.
   A opção 7 do menu faz apenas o diagnóstico de Python e OCR.
4. Para consultar o lote que já veio pronto, abra
   `acervo-tce\complementar-ato.html` ou escolha a opção 5 de `INICIAR.cmd`/`INICIAR.bat`.

## Primeiro uso em outro computador

### 1. Testar o pacote

Clique com o botão direito em `TESTAR-PACOTE.ps1` e escolha **Executar com
PowerShell**. O resultado esperado termina com:

```text
Pacote íntegro: verificação offline aprovada.
```

Python, Tesseract e o idioma português já estão incluídos. Não instale nada.

### 2. Entrar no e-Contas

Para baixar processos novos, abra `INICIAR.cmd` ou `INICIAR.bat`, escolha **1** ou **6** e siga
a mensagem exibida. Quando o navegador abrir, faça login no e-Contas, deixe a
tela **Meus Processos Finalísticos** carregada e volte ao terminal.

O login não acompanha o ZIP. Em cada computador será necessário autenticar-se
novamente.

### 3. Instalar a Extensão

1. No Chrome, abra `chrome://extensions`.
2. Ative **Modo do desenvolvedor**.
3. Clique em **Carregar sem compactação**.
4. Selecione a pasta `extensao-complementar-ato` deste pacote.
5. Opcionalmente, fixe o ícone **Complementar Ato TCE/RN** na barra do Chrome.

## Uso diário: qual opção escolher?

Abra `INICIAR.cmd` ou `INICIAR.bat` e escolha:

| Opção | O que faz | Quando usar |
|---|---|---|
| 1 | Coletar processos selecionados | Baixar eventos e arquivos novos |
| 2 | Analisar acervo local | Reprocessar PDFs, OCR e dados sem acessar o portal |
| 3 | Gerar HTML local | Atualizar o HTML; também executa a análise necessária |
| 4 | Atualizar dados da extensão | Recriar somente `dados-complementar-ato.json` |
| 5 | Abrir HTML existente | Consultar rapidamente o resultado já pronto |
| 6 | Fluxo completo | Coletar, analisar, atualizar resultados e abrir o HTML |
| 7 | Diagnóstico do runtime | Testar Python e idiomas do OCR; não substitui `TESTAR-PACOTE.ps1` |
| 8 | Zerar acervo e iniciar novo lote | Guardar o lote anterior e começar coleta, análise, HTML e JSON do zero |

Na seleção de processos, você pode digitar:

```text
1,4,8-12          seleciona os itens 1, 4 e 8 até 12
todos             seleciona tudo que aparece na lista atual
novos             ignora o que já teve a coleta concluída no checkpoint
buscar magnolia   procura por nome ou número antes da seleção
```

Para o dia a dia, mantenha a mesma pasta extraída e use `novos`. O checkpoint
será retomado e os documentos inalterados não serão baixados outra vez.
`novos` se refere à coleta dos arquivos, não ao check **Processo feito** do HTML.

## Conferir pelo HTML local

Use a opção 5 para abrir a mesa pelo helper local autenticado. Se o serviço
estiver indisponível, abra `acervo-tce\complementar-ato.html` como fallback
estático.

- Escolha o processo na lista superior.
- Troque entre Resolução Administrativa e Guia Financeira quando disponíveis.
- Arraste o divisor central para aumentar o PDF ou os campos.
- Use **Copiar valor** para levar um campo ao portal.
- Use **Processo feito** como conclusão manual do processo. Pela mesa aberta
  pelo helper, a marca é gravada no progresso portátil e compartilhada com a
  extensão; no fallback `file:`, fica somente no navegador.
- Confira sempre a citação de processo, evento e página.

No fallback `file:`, o check do HTML fica salvo no navegador daquele
computador. A marca **Revisado** da extensão continua sendo um controle
separado por interessado; nenhuma das duas marcações envia ou conclui o ato.

Se o PDF aparecer vazio, confirme que o ZIP foi totalmente extraído e use
**Abrir PDF**. Não mova apenas o HTML sem a pasta `processos`. A mesa servida
pelo helper atualiza revisões incrementais; o fallback `file:` não faz polling.

## Preencher com a Extensão

1. Na Área Restrita, abra **Complementar Ato**.
2. Informe o processo e selecione exatamente um interessado.
3. Clique no ícone da extensão para abrir o painel lateral.
4. Na primeira utilização de cada lote, clique em **Importar/Atualizar dados**
   e escolha `acervo-tce\dados-complementar-ato.json`.
5. Clique em **Atualizar prévia**.
6. Confira o valor documental, a opção proposta, o status e a fonte.
7. Clique em **Preencher campos disponíveis** somente depois da conferência.
8. Revise os campos no próprio formulário do TCE.
9. Marque **Revisado** no painel apenas como controle local.

A importação é feita uma vez para o lote inteiro, e não uma vez por processo.
A extensão reconhece automaticamente o processo e o interessado que estão na
tela.

### Ato atual, Execução e Histórico

O painel lateral organiza a conferência em três abas:

- **Ato atual:** mostra a fundamentação, a fonte documental, o valor atual do
  portal e a proposta para cada um dos sete campos. “Por semelhança”,
  “Divergente”, “Revisado” e “Confirmado no portal” são estados diferentes.
- **Execução:** acompanha uma execução persistida pela mesa local. O botão de
  início é explícito; pausar impede novos passos e encerrar preserva o
  relatório. Fechar o painel não retoma nem cancela a execução.
- **Histórico:** consulta execuções anteriores e abre o relatório HTML parcial.
  Consultar histórico não muda a aba do portal e não retoma uma execução.

Até a qualificação ponta a ponta, a capacidade de envio real permanece
desabilitada (`real_send_enabled=false`). O modo manual continua sendo o caminho
disponível: **Preencher campos disponíveis** só prepara valores para revisão e
nenhuma ação do modo manual clica em **Complementar Ato**, limpa ou conclui o
ato. Se o resultado ficar incerto, confira o portal e o relatório; não use um
reenvio direto como recuperação.

Para preparar um lote por marcador, inicie a mesa local, importe o JSON do lote,
informe no painel o texto exato do marcador exibido pela Área Restrita e clique
em **Iniciar**. O worker seleciona o marcador, confirma a filtragem, pagina até
o fim, abre os processos, seleciona o interessado e prepara somente os atos com
ação observável **Complementar Ato**. O painel mostra totais descobertos,
elegíveis e pendentes; a fila é congelada antes da primeira escrita.

O checkbox **Concluir automaticamente os atos elegíveis** só pode ser marcado
com capacidade de envio qualificada. Quando habilitado, o fluxo registra
`send_intent` antes de cada ação, emite um comando de uso único, relê o ato e
aguarda prova de aceitação e persistência. Um timeout, erro de rede, diálogo
desconhecido ou ausência de observador pausa o lote como `unconfirmed`; não há
reenvio automático. A qualificação é específica para as versões instaladas e
não é transportada pelo ZIP.

O botão **Executar piloto de um ato** só aparece quando o serviço foi iniciado
explicitamente com `--automation-pilot` e há um ato atual identificado. Ele
limita o serviço a um único comando consumido por raiz, permanece bloqueado para
lotes comuns e não deve ser usado em portal real antes da autorização e dos
gates da Fase 9. Reiniciar o serviço não restaura o crédito do piloto.

### Significado das cores

- **Verde:** correspondência exata ou segura.
- **Amarelo:** opção mais parecida, aproximação ou empate; confira manualmente.
- **Divergência:** o portal já possui outro valor. A extensão não substitui
  automaticamente. O override é individual e mostra uma confirmação.
- **Pendente:** o dado não foi encontrado com segurança.

Somente estes sete campos podem ser escritos:

```text
Modalidade
Fundamento legal
Data de publicação no DOE
Cargo
Matrícula
Data de nascimento
Gênero
```

A data do DOE corresponde à data expressa na Resolução Administrativa e é
apresentada como `DD/MM/AAAA`. Valores financeiros e a conclusão da análise
continuam manuais.

## Baixar um lote novo no futuro

### Já terminei todo o acervo: quero começar do zero

1. Abra `INICIAR.cmd` e escolha **8**.
2. Confira a pasta `acervo-tce` mostrada e confirme somente se terminou o lote.
3. O conteúdo antigo sai do acervo ativo e fica em `backups-acervo` para recuperação.
   Scripts, runtime, extensão e perfil de login são preservados.
4. Selecione os processos da lista atual. Após a coleta, o programa executa a
   análise e gera o novo HTML e o novo `dados-complementar-ato.json`.
5. Importe o novo JSON no painel da extensão. Essa importação substitui o lote
   anterior e zera as marcas **Revisado**. O HTML novo começa com checks separados.

Se cancelar a confirmação, nada é zerado. Se a coleta/análise falhar depois do
reinício, o backup continua disponível; retome o lote novo pela opção **6**, sem
usar **8** novamente. Os backups não entram no próximo ZIP e continuam ocupando
espaço nesta máquina até você decidir removê-los.

### Quero apenas atualizar sem zerar

Na mesma pasta, use a opção 1 e digite `novos`. Depois escolha a opção 2, 3 ou
6 para atualizar a análise e o HTML. O arquivo da extensão também é atualizado
pela análise; a opção 4 permite atualizá-lo separadamente.

Se começar com uma pasta vazia e quiser usar um ZIP antigo como base de tudo que
já foi concluído, abra o PowerShell na raiz do pacote e execute:

```powershell
& .\Coletar-Processos-TCE.ps1 `
  -Selecao 'novos' `
  -BaseConcluidos 'D:\Caminho\TCE-Atos-Anterior.zip' `
  -BaselineAllComplete
```

Use `-BaselineAllComplete` somente quando todos os processos da base antiga já
tiverem sido realmente conferidos.

## Criar outro ZIP completo

Depois de coletar e analisar um novo lote, abra o PowerShell na raiz e execute:

```powershell
& .\Empacotar-Acervo-Completo.ps1 `
  -Destino 'D:\Destino\TCE-Atos-Atualizado.zip'
```

O empacotador bloqueia a substituição silenciosa de um ZIP existente e executa
a auditoria antes de publicar o arquivo.

## Diagnóstico e problemas comuns

### Estou substituindo uma versão antiga da extensão

Extraia o ZIP novo em outra pasta; preserve o antigo. Em `chrome://extensions`,
carregue a pasta `extensao-complementar-ato` do kit novo ou recarregue a extensão
se atualizou a mesma pasta. Evite manter duas cópias habilitadas ao mesmo tempo.
Depois de atualizar, recarregue a tela do portal **somente se não houver edição
pendente** e importe o JSON do lote desejado. Não recarregue um formulário com
dados ainda não salvos. A versão compatível desta rodada é **1.1.0**.

### O terminal diz que a sessão não está autenticada

Faça login na janela de navegador aberta pelo coletor, volte para **Meus
Processos Finalísticos** e tente novamente. O pacote não copia cookies de outro
navegador.

### Nenhum processo foi encontrado

Espere a lista terminar de carregar, confirme o setor correto e deixe a aba da
lista visível antes de pressionar `ENTER` no terminal.

### O HTML abre, mas o PDF não aparece

Extraia o ZIP inteiro, preserve a estrutura das pastas e evite abrir o HTML a
partir de dentro do ZIP. Caminhos muito longos e pastas sincronizadas podem
causar problemas; prefira `C:\TCE-Atos`.

### A extensão não reconhece a tela

Confirme que você está em `https://novaarearestrita.tce.rn.gov.br/`, na tela
**Complementar Ato**, com um interessado selecionado. Depois clique em
**Atualizar prévia**.

### Apareceu amarelo ou divergência

Não preencha às cegas. Compare a proposta com o PDF e a citação. Em empate, a
extensão mostra a primeira opção do portal como proposta amarela. Divergências
só podem ser substituídas uma por vez, após confirmação.

### O diagnóstico falhou

Não use o pacote para preencher dados. Execute `TESTAR-PACOTE.ps1`, anote a
linha marcada como **FALHOU** e preserve a pasta para correção.

## O que existe em cada pasta

| Item | Finalidade |
|---|---|
| `INICIAR.cmd` / `INICIAR.bat` | Menus principais; o `.bat` delega ao `.cmd` |
| `GUIA-RAPIDO.html` | Este guia em formato visual |
| `TESTAR-PACOTE.ps1` | Diagnóstico offline de integridade |
| `Coletar-Processos-TCE.ps1` | Coleta direta e opções avançadas |
| `Empacotar-Acervo-Completo.ps1` | Gera um novo ZIP privado auditado |
| `acervo-tce` | HTML, resultados, checkpoints, eventos e PDFs |
| `extensao-complementar-ato` | Extensão para carregar no Chrome |
| `runtime` | Python, PyMuPDF e Tesseract portáteis |
| `app` | Componentes internos do coletor e analisador |
| `licenses` | Licenças dos componentes incluídos |
| `runtime-manifest.json` | Inventário e hashes do runtime |

Não edite `runtime`, `app` ou `runtime-manifest.json`. Para uso normal, concentre-se
em `INICIAR.cmd`/`INICIAR.bat`, no HTML, na extensão e na pasta `acervo-tce`.

## Limites de segurança

- O coletor baixa documentos, mas não envia nem altera processos.
- A extensão não assina, não tramita, não conclui e não limpa o formulário.
- A decisão final e a conclusão da análise permanecem manuais.
- O pacote privado contém dados pessoais. Guarde-o somente em local autorizado.
- CAPTCHA, bloqueio de rede, alteração do portal ou expiração da sessão exigem
  intervenção humana.
