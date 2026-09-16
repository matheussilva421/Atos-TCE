# Handoff — Fundamentação legal de professores v2 — Task 8

## Resumo

Atualizados os inventários de distribuição para incluir os três módulos do crosswalk jurídico v2 e os consumidores operacionais alterados. O empacotador de extensão foi executado com sucesso em ZIP temporário controlado; o pacote contém 22 entradas exatas e a versão `legal-foundation-v2`.

## Arquivos alterados

- `work/tce-extractor/portable/app/package_audit.py`
- `work/tce-extractor/package_complete_archive.py`
- `work/tce-extractor/empacotar-extensao-complementar-ato.ps1`
- `work/tce-extractor/empacotar-coletor-portatil.ps1`
- `work/tce-extractor/package_qa_release.ps1`
- `work/tce-extractor/verify_qa_release.py`
- `work/tce-extractor/test_package_audit.py`

O teste de contrato foi ampliado para exigir:

- `lib/legal-reference-parser-v2.js`;
- `lib/retirement-legal-profile.js`;
- `lib/portal-legal-crosswalk.js`.

## Decisões técnicas

- As três novas bibliotecas são allowlisted nos auditores Python e nos dois empacotadores PowerShell.
- O release QA copia também `legal-foundation.js`, `automation-preflight.js`, `automation-controller.js`, `panel.js` e `panel-view.js`, evitando misturar o crosswalk v2 com consumidores antigos.
- A checagem de paridade do release QA foi ampliada para esses arquivos.
- Nenhum fluxo de envio real, login ou finalização de portal foi executado.

## Testes e evidências

- `python -m unittest -q test_package_audit.py test_package_complete_archive.py`
  - 68 testes; 68 passaram; 0 falharam; 2 skips esperados.
- `pwsh -NoProfile -File .\empacotar-extensao-complementar-ato.ps1 -OutputPath .\.codex-qa\extensao-complementar-ato-v2.zip -Force`
  - ZIP criado com 22 arquivos.
- Auditoria direta do ZIP:
  - três módulos v2 presentes;
  - consumidores legais presentes;
  - `legal-foundation-v2` presente na implementação da fundação;
  - `panel.js` importa a constante de versão;
  - inventário exato confirmado.

## Limitações

- `staging-task5-verified` e a base histórica `outputs/TCE-Atos-Novos-43-COM-GUIA-2026-09-05` não estão disponíveis neste worktree; por isso o `package_qa_release.ps1 -Build` completo não foi executado.
- O ZIP de extensão em `.codex-qa/` é evidência local temporária e não deve ser versionado.

## Próxima retomada

1. Criar o relatório da matriz de 12 fixtures e executar a suíte JavaScript completa.
2. Rodar as suítes Python portáteis e os contratos de empacotamento novamente.
3. Remover artefatos temporários locais, revisar o diff e atualizar o handoff final.
