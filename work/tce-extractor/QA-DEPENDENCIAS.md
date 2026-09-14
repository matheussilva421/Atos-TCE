# Dependências de QA do checkout

As suítes Python do checkout exercitam importação de `.xlsx`, OCR/PDF e
fixtures de navegador. O runtime embutido em `portable/runtime` é reservado
para o pacote publicado e pode não existir ou ser mínimo no repositório; ele
não deve ser usado como interpretador de desenvolvimento.

Prepare um interpretador Python 3.14 para QA com as versões fixadas:

```powershell
python -m pip install --requirement .\requirements-qa.txt
python -m unittest discover -p 'test*.py'
```

O arquivo `requirements-qa.txt` fixa `openpyxl`, `et-xmlfile`, `PyMuPDF` e
Playwright. O construtor do pacote baixa as duas dependências de planilha e
PyMuPDF em staging temporário, valida SHA-256 e copia as licenças do wheel;
nenhum `pip install` é executado no computador de destino.

Para os fixtures Playwright que exigirem o navegador local, instale somente o
browser aprovado pelo ambiente de QA conforme a política do projeto. Login,
cookies e credenciais dos portais não fazem parte das fixtures nem do pacote.
