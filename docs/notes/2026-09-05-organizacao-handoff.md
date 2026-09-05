# Migração para repositório local

Destino: C:/Users/slvma/Downloads/Github/Complementação de Atos.

Transferidos outputs (incluindo ZIP227 e backup), portable histórico, anexos recebidos, código operacional work/tce-extractor, testes e runtimes verificados. A hierarquia relativa foi preservada para manter os empacotadores funcionando. Documentação histórica permanece em work/tce-extractor/docs/notes, local e fora do Git.

Criados README.md, docs/ESTRUTURA.md, .gitignore por lista de permissão e .gitattributes preservando bytes de scripts Windows. Git inicializado em main, sem remoto configurado. Nenhuma criação/publicação de repositório remoto foi autorizada separadamente.

Resíduos na origem g-2: parte de staging/runtime/runtime/python/Lib/site-packages com acesso negado; parte de tmp/qa-mcp-live com arquivos em uso. Não houve exclusão forçada nem fechamento de navegador. A migração dessas sobras técnicas está pendente; não são fontes nem o pacote final. Move-Item transferiu parcialmente esses diretórios; consultar ambas as localizações antes de retomar, nunca sobrescrever cegamente.

Nenhum PDF, ZIP, backup ou perfil foi apagado. Sem mudança de lógica de extração nesta reorganização. Helpers históricos de QA apontam em alguns casos para o caminho original e precisam revisão antes de reexecução; não executar reset/coleta durante validação da migração.

Próximo: testar extensão no novo caminho, comparar SHA256 do ZIP227 e conferir a lista de arquivos staged antes do commit. Não publicar dados pessoais. Git safe.directory será usado somente como opção por comando, sem mudar configuração global.

## Validação final

- node --test na extensão:106 passaram,0 falharam.
- python -B -m unittest test_archive_index test_extension_exporter test_reset_archive -q:29 executados,28 passaram,1skip(symlink sem privilégio),0falhas.
- ZIP227 SHA256 preservado:a621791800a24ab6292b755d473aef6b3f407e167a4bf4beb8272acb68ff1720.
- Gate dos caminhos staged:sem PDFs,ZIPs,outputs,tmp,runtime,acervo ou perfis. Varredura limitada por padrões de tokens não apontou resultados; não substitui revisão de segurança antes de publicação.
- Repositório local main pronto para commit inicial; remoto ausente,portanto sem push. Não criar remoto público automaticamente.
- Não houve exclusões. Migração principal concluída; sobras técnicas bloqueadas permanecem na origem, com arquivo MOVIDO-PARA.md apontando o novo destino. Próximo passo opcional:fechar manualmente Chrome QA e revisar resíduos antes de limpar. Projeto deve ser reaberto no Codex pelo novo diretório.
