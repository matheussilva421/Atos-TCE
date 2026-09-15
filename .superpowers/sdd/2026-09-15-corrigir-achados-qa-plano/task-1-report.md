# Task 1 — Relatório de empacotamento e privacidade

**Data:** 15/09/2026
**Escopo:** somente a Task 1 do plano `corrigir-achados-qa-plano`.
**Restrições observadas:** sem rede, login, envio de atos ou alteração do pacote de referência de 14/09.

## Causa raiz

O empacotador público mantinha uma allowlist de módulos incompleta: `process_list.py` e `register_process_list.py` eram usados pelo fluxo, mas não eram copiados para `app/` no ZIP. A auditoria também tratava `.xlsx` e `.sqlite3` como binários allowlisted em qualquer caminho, permitindo que dados binários privados fora do acervo privado passassem sem finding. Além disso, o auditor exigia apenas `extension_exporter.py` e `package_complete_archive.py` como módulos de app.

## Alterações implementadas

- `work/tce-extractor/empacotar-coletor-portatil.ps1`
  - Incluídos `process_list.py` e `register_process_list.py` na lista explícita de cópia.
  - Mantido o padrão `Copy-PackageFile`; nenhuma cópia recursiva foi adicionada.
- `work/tce-extractor/portable/app/package_audit.py`
  - `.xlsx` e `.sqlite3` deixaram de ser binários globais allowlisted.
  - Esses sufixos são reconhecidos sem erro de binário somente quando estão diretamente sob `acervo-tce` em distribuição `private`.
  - Qualquer ocorrência em distribuição `public`, inclusive sob `acervo-tce`, gera `forbidden_file` e torna `report.ok` falso.
  - A auditoria pública passou a exigir os quatro módulos de app, incluindo os dois da lista autoritativa.
- `work/tce-extractor/test_package_audit.py`
  - Fixtures públicas válidas atualizadas com os novos módulos obrigatórios.
  - Adicionadas regressões para `.xlsx`/`.sqlite3` fora e dentro de `acervo-tce` em modo público.
  - Atualizada a regressão de módulos ausentes e o contrato do empacotador.

## TDD — RED

Com os testes novos escritos e antes da correção de produção:

```text
python -m unittest -v test_package_audit.PackageAuditContractTests.test_public_audit_rejects_workbook_and_sqlite_outside_private_archive test_package_audit.PackageAuditContractTests.test_public_audit_rejects_workbook_and_sqlite_inside_archive test_package_audit.PackageAuditContractTests.test_public_audit_requires_app_modules_and_extension_when_directories_are_absent test_package_audit.PackagerContractTests.test_public_packager_has_explicit_extension_inventory_and_modules
```

Resultado RED: 4 métodos de teste executados; 1 método passou e 3 métodos produziram 4 registros de falha (incluindo 2 subtestes do inventário dos módulos). As falhas foram as esperadas: os binários públicos fora do acervo não produziam findings, os módulos ausentes não eram exigidos e os nomes não estavam no empacotador. A rejeição pública de binários sob `acervo-tce` já era coberta pela regra de caminho privado e permaneceu verde.

## TDD — GREEN

Após a correção mínima:

```text
python -m unittest -v test_package_audit.PackageAuditContractTests.test_public_audit_rejects_workbook_and_sqlite_outside_private_archive test_package_audit.PackageAuditContractTests.test_public_audit_rejects_workbook_and_sqlite_inside_archive test_package_audit.PackageAuditContractTests.test_accepts_workbook_and_sqlite_as_known_private_binary_data test_package_audit.PackageAuditContractTests.test_public_audit_requires_app_modules_and_extension_when_directories_are_absent test_package_audit.PackagerContractTests.test_public_packager_has_explicit_extension_inventory_and_modules
```

Resultado GREEN: 5 testes executados; 5 passaram; 0 falharam.

## Regressão

```text
python -m unittest -v test_package_audit
```

Resultado: 49 testes executados; 47 passaram; 0 falharam; 2 foram ignorados porque o ambiente Windows não concedeu privilégio para criar symlinks nos testes de reparse point.

```text
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\tests\Test-TcePortable.ps1
```

Resultado: 136 testes/checks passaram; 0 falharam.

Verificações adicionais: `python -m py_compile work/tce-extractor/portable/app/package_audit.py` e `git diff --check` passaram.

## Fronteiras e pendências

- O empacotamento físico não foi executado: `work/tce-extractor/staging-task5-verified` e seu runtime verificado não estão presentes neste checkout. O teste offline de contrato do empacotador foi executado; gerar um ZIP exigiria fontes de runtime ausentes e criaria artefatos fora do escopo.
- Nenhum dado real, PDF, planilha pessoal, credencial, perfil, rede, login ou envio foi usado.
- A referência de 14/09 permaneceu sem alterações no Git.

## GitHub

Commit nominal da implementação da Task 1: `605834f` (`fix: harden portable package audit`).
Este relatório e o handoff receberam uma atualização documental posterior para registrar o hash real.

## Fix round 1 — revisão dos testes

### Apontamento P2.1 — aceite privado dos binários

O teste `test_accepts_workbook_and_sqlite_as_known_private_binary_data` passou a construir uma distribuição privada estruturalmente válida: runtime/manifesto/licença, extensão válida, `acervo-tce/dados-complementar-ato.json` e os dois binários de fixture. Além da ausência de `binary_unrecognized`, ele agora exige `report.ok`, impedindo que findings estruturais sejam ignorados.

RED da alteração do teste, antes da fixture ser completada:

```text
python -m unittest -v test_package_audit.PackageAuditContractTests.test_accepts_workbook_and_sqlite_as_known_private_binary_data
```

Resultado: 1 teste executado, 1 falhou como esperado; findings observados: `manifest_missing`, `manifest_runtime_missing`, `manifest_license_missing`, `license_missing` e `private_data_missing`.

### Apontamento P2.2 — ausência individual dos módulos

Foi adicionado `test_public_audit_rejects_each_missing_authoritative_process_module`. Ele parte de uma árvore pública válida, remove somente `process_list.py` ou somente `register_process_list.py` em subtestes separados e exige o finding correspondente `app_file_missing`.

RED contra o auditor anterior, carregado read-only do parent de `605834f`:

```text
python -c 'import subprocess,sys,types,unittest; source=subprocess.check_output(["git","show","605834f^:work/tce-extractor/portable/app/package_audit.py"]); module=types.ModuleType("package_audit"); module.__file__="package_audit.py"; sys.modules["package_audit"]=module; exec(compile(source,"package_audit.py","exec"),module.__dict__); sys.path.insert(0,"."); suite=unittest.defaultTestLoader.loadTestsFromName("test_package_audit.PackageAuditContractTests.test_public_audit_rejects_each_missing_authoritative_process_module"); result=unittest.TextTestRunner(verbosity=2).run(suite); raise SystemExit(0 if result.wasSuccessful() else 1)'
```

Resultado: 1 método com 2 subtestes; ambos falharam como esperado no auditor anterior, que não produziu `app_file_missing` para nenhum dos módulos.

GREEN após os testes finais:

```text
python -m unittest -v test_package_audit.PackageAuditContractTests.test_accepts_workbook_and_sqlite_as_known_private_binary_data test_package_audit.PackageAuditContractTests.test_public_audit_rejects_each_missing_authoritative_process_module
```

Resultado: 2 testes executados; 2 passaram; 0 falharam.

Suíte focada atualizada:

```text
python -m unittest -v test_package_audit
```

Resultado: 49 testes executados; 47 passaram; 0 falharam; 2 skips por privilégio de symlink no Windows.
