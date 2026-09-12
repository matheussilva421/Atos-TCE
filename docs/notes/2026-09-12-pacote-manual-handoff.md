# Pacote portátil manual — 2026-09-12

## Decisão e escopo vigente

O usuário cancelou a automação e pediu um ZIP para coletar processos, extrair dados, montar HTML e usar a extensão. Não retomar pilotos nem fases de envio. O pacote final está limpo, sem acervo privado, perfis, credenciais, histórico de execução ou qualificação.

## Estado preservado da tentativa anterior

Piloto final run-bde0f309f7ac497f85cdd36520df0ba9 encerrado pela extensão, revisão 3, status stopped. Nenhum ato enviado. Um preflight foi conferido no portal (100065/2026); o segundo ficou pendente por referência de vantagem salarial misturada com fundamento. Tarefa 4.2 não passa e foi cancelada pelo usuário, não concluída.

Correções já verdes de navegação e pausa para revisão foram preservadas. Os três testes de fundamento recém-escritos, ainda sem implementação (2 falhas esperadas), foram retirados da suíte ativa e preservados em tmp/fase41/abandoned-legal-tests.txt. O defeito permanece pendente; não houve alteração correspondente em produção. No uso manual, propostas ambíguas exigem conferência do operador.

## Preparação realizada

Guia simplificado, empacotamento por allowlist e validação de runtime, CRC, inventário, extração/HTML/JSON e extensão concluídos. Manifesto recuperado do pacote fase11k; hashes conferidos pelo empacotador.

## Entrega validada

- ZIP: `outputs/TCE-Coleta-Extracao-HTML-Extensao-2026-09-12-pdf-corrigido.zip`.
- Tamanho: 95.878.429 bytes (91,44 MiB); 294 entradas.
- SHA-256: `85faeea8972810949e331710e2f03c6274bc37fc24e3ec4a4842347532f7edd5`.
- Checksum ao lado: mesmo nome acrescido de `.sha256`.
- Gerado pelo empacotador existente, sem modificar suas regras; guias HTML/Markdown simplificados, README orienta opção 6 e importação manual do JSON, sem pareamento obrigatório.
- Inclui coleta, pipeline, gerador HTML, extensão, Python, Tesseract/português e PDF.js. Não inclui acervo, perfis, dados locais, credenciais ou autorização de envio. Módulos/controles experimentais permanecem no código existente, fora do fluxo de uso documentado; nenhuma remoção arquitetural foi feita.
- O staging antigo só conservava diretórios de runtime. Binários e manifesto foram recuperados da extração fase11k. A primeira auditoria recusou 11 arquivos de cache não declarados; foram movidos para `tmp/fase41/manual-build-runtime-cache-quarantine`. Segunda auditoria passou. Originais/pacotes anteriores preservados.

## Testes e evidências

- `npm test` na extensão: **362 executados, 362 aprovados, 0 falhas** (`tmp/fase41/manual-node.log`).
- `python -m unittest test_tce_extractor test_batch_runner test_analysis_pipeline test_html_generator test_package_audit test_extension_zip_packager`: **138 testes, 136 aprovados, 0 falhas, 2 skips ambientais** (`manual-python-final.log`). Primeiro passe falhou em dois checks textuais de tópicos dos guias; títulos ajustados e suíte completa reexecutada verde.
- `Test-PortableMenu.ps1`: **83 aprovados, 0 falhas**. `Test-TcePortable.ps1`: **114 aprovados, 0 falhas**, no Windows PowerShell.
- ZIP: CRC de todas as entradas aprovado, paths sem travessia e conteúdo limpo; inventários staging/ZIP comparados pelo empacotador; manifesto/licenças/hashes aprovados.
- `TESTAR-PACOTE.ps1` na extração nova: **verificação offline aprovada**, Python/PyMuPDF, Tesseract/DLLs/idiomas e auditoria pública.
- Extensão do ZIP em Chrome descartável 145: **7 linhas**, troca de interessado sem reimportação, empate recalculado, DOM incompleto bloqueado, dados persistidos após reiniciar perfil, controles de envio/limpeza intactos. Resultado `manual-extension-smoke.json`, duração 12,778 s.
- Pipeline executado com o **Python/app extraídos do ZIP**, sobre cópia privada de um processo real: 18 documentos indexados, 2 prioritários, seis campos encontrados, gênero ausente mantido como missing. Gerou HTML, JSON e evidências; segunda execução também aprovada. Status partial é correto pela ausência de gênero, não falha do pipeline.
- HTML e PDF.js renderizados em Chrome via HTTP local, processo/cargo visíveis, **0 erros JavaScript**. Guia inspecionado visualmente. Capturas privadas em tmp/fase41, fora do ZIP/Git.
- OCR real do executável embalado, idioma por, sobre imagem de teste: reconheceu `DOCUMENTO DE TESTE 12345`.
- `git diff --check`: limpo.

## Estado final e limites

Pilotos encerrados; bridge piloto PID 28140 encerrada após confirmar comando e raiz exatos. Chrome de trabalho e Chrome pessoal preservados. Nenhum ato enviado. Não houve nova coleta autenticada nesta entrega: a coleta teve 114 checks locais; login/seleção no PC destino continuam humanos. A automação foi cancelada, não declarada funcional. O defeito de fundamento antes descrito continua sujeito a revisão manual.

Próximo passo do usuário: extrair o ZIP, abrir GUIA-RAPIDO.html e executar INICIAR.cmd → opção 6. A extensão usa `acervo-tce/dados-complementar-ato.json`, importado manualmente.

Arquivos de código herdados e correções verdes da sessão anterior foram preservados; apenas os testes ainda sem implementação foram retirados e arquivados como investigação cancelada. Handoff anterior foi sanitizado para retirar identificador pessoal e código temporário antes de publicação.

## GitHub e retomada

Branch main. Publicação de código/docs por staging nominal ao fim deste bloco; hash de commit/push registrado no fechamento abaixo. ZIP, tmp/, outputs/, PDFs e dados pessoais ficam fora do Git. Novo objetivo substitui integralmente os preflights em andamento.

## Correção após a captura com PDF vazio

O usuário apontou que uma captura exibida pelo agente tinha PDF em branco. A conferência HTTP anterior mostrou conteúdo na captura mais recente, mas o assert apenas procurava um canvas, já presente mesmo quando oculto. Não serve como gate de renderização.

Novo teste `test_manual_review_browser.py` verifica canvas visível com pixels opacos de texto e papel. Reprodução RED: rota autenticada `/review` não abria sem `publicacao-atual.json`; HTML estático tentava polling e dizia desconectado. Controle negativo sem assets recusou a imagem vazia. Correção mínima: `portable/app/local_service.py` constrói a conferência com os artefatos da extração local quando não existe publicação; `html_generator.py` dispensa polling no modo manual. GREEN: 3/3 testes, incluindo PDF renderizado pela rota do menu. Guias orientam abrir pelo INICIAR.cmd → 5; duplo clique no HTML pode bloquear os módulos locais do PDF.js. Sem automação/piloto.

A primeira revisão do ZIP ainda falhou com PDF real: a lista usava event_id interno do portal, enquanto manifest/sidecar usavam o número do evento; a URL autenticada retornava 404. Teste corrigido para consumir write_visual_evidence real, sem fabricar IDs (RED). html_generator reutiliza a identidade canônica do documento-alvo (GREEN, 4/4 com test_review_assets). Os ZIPs intermediários foram preservados, mas estão superados pelo arquivo -pdf-corrigido acima.
## Fechamento da validação do PDF

- Suíte ampliada: `python -m unittest test_tce_extractor test_batch_runner test_analysis_pipeline test_html_generator test_package_audit test_extension_zip_packager test_local_service test_review_live_browser test_manual_review_browser test_review_assets`: **166 executados, 163 aprovados, 0 falhas, 3 skips**, 64,042 s. Log `tmp/fase41/manual-final-python-v2.log`.
- ZIP final extraído do zero em `tmp/manual-package-final-pdf-v2`, auditado limpo antes de adicionar cópia privada para QA. `TESTAR-PACOTE.ps1` passou. CRC completo passou. O ZIP continua sem dados privados.
- Python e serviço da própria extração abriram a rota `/review` com o processo real 100065/2026, sem publicação de automação. Canvas visível com pixels de texto/papel, status Modo manual, nenhum pageerror JavaScript. Foto final inspecionada: documento inteiro com cabeçalho, texto e assinatura visíveis em PDF.js a 75%. `tmp/fase41/manual-final-pdf-visible.png`; relatório `manual-final-pdf-report.json`. Helper local da QA encerrado.
- Captura antiga apontada pelo usuário estava em fallback vazio. A presença de canvas no DOM era gate insuficiente; teste novo rejeita assets ausentes. O relatório intermediário que usou uma extração modificada foi substituído pela QA da extração final intacta.
- Limitação observada fora da abertura inicial: cliques muito rápidos de zoom podem provocar renderizações concorrentes e mensagem de fallback. A conferência final usou zoom sequencial aguardando renderização. Não declarar esse comportamento corrigido. Abrir PDF continua disponível.
- Outros limites preservados: nova coleta autenticada depende do login humano; ambiguidades jurídicas exigem revisão. Nenhum ato enviado, automação cancelada.
- Arquivos adicionais: html_generator.py, portable/app/local_service.py e test_manual_review_browser.py, além de guias e documentos previamente listados.

## Publicação confirmada

Código e documentação publicados em origin/main: commit c53cdf1 (fix: restore manual portable review and PDF document links), push bem-sucedido em 12/09/2026. Este fechamento documental segue no commit seguinte. ZIP local ignorado pelo Git; entregar o link do arquivo -pdf-corrigido. Não retomar automação. Nenhum processo ou PDF privado foi publicado.
