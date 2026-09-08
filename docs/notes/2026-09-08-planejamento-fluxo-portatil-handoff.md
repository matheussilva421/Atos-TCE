# Handoff — planejamento do fluxo portátil — 08/09/2026

## Entrega

Criado `docs/notes/2026-09-08-fluxo-portatil-plano-implementacao.md`, com decisões aprovadas, mapa de módulos reais, contratos e fases 0–8 para outro agente implementar.

Somente documentação: nenhum coletor, PDF, HTML, JSON de acervo ou extensão foi alterado. Não houve coleta, OCR, instalação ou teste no portal nesta sessão.

## Descobertas relevantes

- Pipeline atual regenera resultados globais; publicação incremental exige merge por processo e escritor único.
- JSON da extensão é v1 estrito. Plano mantém compatibilidade usando sidecar para geometria.
- HTML seleciona documento pelo número do evento; fase 4 corrige ambiguidade com ID documental.
- Progresso hoje fica dividido entre localStorage e chrome.storage; plano centraliza em arquivo portátil sem transformar Revisado em Concluído.
- Empacotador usa allowlist de arquivos da extensão; novos módulos devem ser adicionados explicitamente.
- Não existe AGENTS.md físico na raiz; instruções globais foram fornecidas pela conversa.

## Validações e Git

Inspeção estática de módulos Python, PowerShell, JS, testes, manifest, gitignore e empacotador. Verificação PowerShell de 20 caminhos existentes referenciados: 20 passaram, zero falharam. Conferidas nove fases (0–8) e ausência de placeholders TBD/TODO. `git diff --check` sem erros; conferir também o diff staged antes do commit. Não foi rodada suíte funcional: documentação não equivale a implementação testada.

Consulta de `git remote -v` não retornou remoto. Não criar remoto nem enviar dados pessoais. Commit apenas dos dois documentos de planejamento.

## Retomada

Ler o plano inteiro; começar pela fase 0 com baseline atual. Não executar todas as fases sem gates. Manter navegação, correções, salvamento e conclusão do ato sob controle do usuário. Autenticação/QA humano é checkpoint de parada. Somente Luna xhigh se houver subagentes compatíveis disponíveis; senão agente principal.

Pendências: todas as fases funcionais. Nenhum código parcialmente implementado; não há rollback funcional necessário.
