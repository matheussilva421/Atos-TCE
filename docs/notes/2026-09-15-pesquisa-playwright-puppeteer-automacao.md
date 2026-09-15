# Pesquisa: Playwright e Puppeteer na automação de Complementação de Atos

**Data:** 2026-09-15  
**Escopo:** avaliar as fontes fornecidas para a automação segura da Complementação de Atos na Área Restrita, sem login, envio ou tramitação nesta pesquisa.

## Conclusão executiva

Sim, as fontes ajudam. A recomendação é manter o Playwright como camada principal de navegador e usar Puppeteer apenas se surgir uma necessidade pontual no harness Node. O projeto já tem a decisão estrutural correta: `work/tce-extractor/qa_portal_recorder.py` usa Playwright com contexto persistente, perfil privado `dados-locais/chrome-qa-profile`, extensão explicitamente carregada, trace, HAR e captura estrutural sem valores dos campos.

Não há justificativa técnica, neste momento, para migrar o gravador para Puppeteer ou adicionar duas camadas de automação ao fluxo real. Isso aumentaria superfície, dependências e divergência entre o teste e a ferramenta que grava a sessão.

## O que as fontes confirmam

### Playwright

- O Playwright fornece automação para Chromium, Firefox e WebKit, com APIs para Python, TypeScript/JavaScript, Java e .NET. A documentação destaca auto-wait, locators, assertions, isolamento por contexto e tracing ([Playwright](https://playwright.dev/)).
- Para extensões, a documentação recomenda Chromium em contexto persistente e informa que as flags necessárias para carregar extensões foram removidas do Google Chrome e do Edge; a fixture deve preferir o Chromium distribuído pelo Playwright ([Chrome extensions](https://playwright.dev/docs/chrome-extensions)).
- O Trace Viewer permite inspeção local do `trace.zip`, com timeline, locators, snapshots DOM, screenshots, console e requisições de rede ([Trace viewer](https://playwright.dev/docs/trace-viewer)).
- A API de rede permite observar, interceptar e simular requisições HTTP/HTTPS, XHR e `fetch`, além de reutilizar HAR em fixtures ([Network](https://playwright.dev/docs/network)).

Aplicação ao projeto:

1. **Fixture da extensão:** usar Chromium gerenciado pelo Playwright para testar as cinco abas, service worker MV3, popup/painel, frames e controles sem tocar o portal.
2. **Gravador real:** manter o Chrome instalado somente no perfil QA privado e em modo headed, com login feito pelo usuário e observação sem submissão.
3. **Diagnóstico:** enriquecer os eventos já existentes com classe de frame, rota sanitizada, fingerprint estrutural, duração, transição observada, console e falha de rede.
4. **Falhas controladas:** simular 401, 403, timeout e indisponibilidade de bridge em fixtures; esses resultados continuam sendo `PASS_FIXTURE` ou `BLOCKED`, nunca `PASS_REAL`.

### Puppeteer

- Puppeteer oferece uma API JavaScript/Node de alto nível sobre Chrome DevTools Protocol e WebDriver BiDi; o modo headless é o padrão ([Puppeteer](https://pptr.dev/), [repositório oficial](https://github.com/puppeteer/puppeteer)).
- A API atual possui suporte explícito a extensões não empacotadas por `enableExtensions`, instalação em runtime e acesso a service workers/realms de extensões ([Chrome extensions](https://pptr.dev/guides/chrome-extensions)).
- `userDataDir`, `channel`, `executablePath` e `debuggingPort` existem em `LaunchOptions` ([LaunchOptions](https://pptr.dev/api/puppeteer.launchoptions)). O pacote `puppeteer` pode baixar um navegador compatível; `puppeteer-core` evita esse download, mas exige navegador executável configurado ([Puppeteer](https://pptr.dev/)).

Aplicação ao projeto:

- Pode ser útil para um pequeno teste Node isolado de carregamento da extensão, caso uma suíte Node existente precise de uma API Puppeteer.
- Não resolve o bloqueio do Chrome instalado por política/ambiente, não transforma fixture em evidência do portal real e não substitui o perfil QA nem o gate humano.
- Introduzir Puppeteer no gravador atual duplicaria tracing, fixtures, locators e tratamento de service worker. O ganho esperado é menor que o custo de manutenção.

### Artigo do Medium

O artigo é útil como panorama de bibliotecas, mas é fonte secundária e não deve definir contratos de segurança, compatibilidade ou arquitetura. A própria menção a `pyppeteer` como port não oficial reforça que não devemos escolher a biblioteca Python por esse artigo ([artigo](https://medium.com/the-pythonworld/9-python-libraries-that-automate-the-internet-so-you-dont-have-to-63b99306fbff)). Decisões técnicas devem continuar baseadas na documentação oficial acima e nos testes deste repositório.

## Compatibilidade com a arquitetura atual

| Necessidade | Recomendação | Evidência/limite |
|---|---|---|
| Gravar sessão humana autenticada | Playwright no Chrome instalado, perfil QA exclusivo | O usuário faz login; o recorder observa; sem credencial no código |
| Testar extensão MV3 em fixture | Playwright + Chromium gerenciado | Extensão carregada em contexto persistente; service worker verificado pelo manifesto |
| Capturar trace, HAR, screenshots e console | Playwright | Artefatos brutos ficam somente em `dados-locais` |
| Simular 401/403/timeout/bridge | Playwright Network + fixtures locais | Não gera evidência `PASS_REAL` |
| Teste Node específico de extensão | Puppeteer opcional | Só adicionar se houver caso concreto que reduza custo ou cubra uma lacuna |
| Requisições HTTP sem DOM | `requests`/cliente HTTP somente em fixture ou contrato explícito | Não serve para fluxo autenticado dinâmico, frames e seleção visual |
| Interação por coordenadas | Não recomendado | Frágil, não identifica estruturalmente o processo/interessado e não é fail-closed |

## Riscos e ajustes necessários

1. **Sensibilidade dos artefatos.** Trace e HAR podem conter cookies, cabeçalhos, corpos de requisição, identificadores e dados pessoais mesmo quando o relatório está sanitizado. Devem continuar em `dados-locais/qa-runs/`, fora do Git, ZIP e relatório público. A opção de conteúdo do HAR deve ser mínima ou omitida nas fixtures sempre que o corpo não for necessário.
2. **Diferença entre fixture e portal real.** Chromium gerenciado é a melhor base para testes determinísticos da extensão, mas não prova o comportamento do Chrome instalado, da política do computador ou do portal. A sessão real continua separada e permanece `BLOCKED` até evidência humana estável.
3. **Service worker MV3.** O worker pode ser suspenso e reiniciado. Fixtures devem tolerar reobtenção do worker e tratar chamadas interrompidas como falha explícita, nunca como sucesso silencioso.
4. **Identidade estrutural.** Locators devem usar role, label, name/id estável, frame e identidade do processo/interessado. Não usar texto solto, posição ou coordenadas para decidir o alvo.
5. **Gate de envio.** `auto_submit=false` e `real_send_enabled=false` devem permanecer. Um teste de envio só pode simular consumo único, duplicata, timeout incerto e bloqueio de reenvio em fixture; o portal real exige autorização nova e específica.

## Experimento seguro recomendado

Este é o próximo bloco de implementação, ainda sem acessar a Área Restrita:

1. Criar uma fixture Playwright com Chromium gerenciado, contexto persistente temporário sob `dados-locais`, extensão carregada por allow-list e verificação de um único service worker compatível com o manifesto.
2. Exercitar a navegação de cinco abas, teclado, foco, painel, prévia, `Revisado`, sete campos, divergência e override usando HTML/frames sintéticos sanitizados.
3. Adicionar fixtures de rede para 401, 403, timeout, bridge indisponível e `ERR_NETWORK_ACCESS_DENIED`, verificando estados bloqueados e propagação de erro.
4. Gerar trace/HAR privado do experimento e executar uma asserção de pós-processamento que rejeite `Cookie`, `Authorization`, Bearer, senha, token, CPF e valores digitados no relatório sanitizado.
5. Reexecutar a matriz offline. Somente depois repetir a sessão no Chrome QA com login manual, sem envio, e tentar os três preflights consecutivos exigidos pelo gate real.

## Decisão

- **Adotar:** Playwright como browser driver único do QA e do gravador.
- **Manter separado:** Chromium gerenciado para fixtures; Chrome instalado para a sessão manual real.
- **Opcional:** Puppeteer em um teste Node pequeno e isolado, apenas se um caso demonstrar vantagem objetiva.
- **Não adotar:** `pyppeteer` como dependência de produção, automação por coordenadas ou cliente HTTP como substituto do navegador.

## Estado ao registrar esta pesquisa

- Branch: `main`.
- Pacote de referência: `Versions/TCE-Meus-Processos-165-e-Setor-156-Extensao-Reorganizada-2026-09-14` preservado.
- Gravador existente: Playwright, trace/HAR/screenshots e eventos estruturais sanitizados.
- Segurança: nenhuma credencial digitada; nenhum envio, conclusão, assinatura ou tramitação executado.
- Matriz QA anterior: `24 PASS_FIXTURE`, `1 PASS_PACKAGE`, `5 BLOCKED`, `0 PASS_REAL`; os cinco gates reais permanecem condicionados à sessão humana isolada.

