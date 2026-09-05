# Organização e manutenção

As fontes operacionais ficam em work/tce-extractor. A hierarquia foi preservada porque os scripts resolvem outputs a partir de dois níveis acima. O pacote pronto funciona por caminhos relativos e deve ser extraído inteiro.

Dados e entregas estão em outputs, sempre fora do Git. Perfis e evidências de teste estão em tmp e nos diretórios locais de desenvolvimento, também ignorados. Montagens históricas foram preservadas: não apagar um staging sem verificar referências nos scripts e sem conferir a entrega correspondente.

Para publicar futuramente: revisar git diff --cached, configurar um remoto privado explicitamente e somente então fazer push. A pasta chamada Github não cria, por si só, um repositório remoto.
