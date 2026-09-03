# Deploy (backups-community)

1. Executar `python3 -m pytest -q` e `ruff check src tests`.
2. Publicar a entrega em `dev`.
3. Promover o mesmo commit para `master`.
4. No servidor, atualizar `origin/master` e trocar o checkout para `master`.
5. Validar o cron e o health check de replicacao.

O arquivo de credenciais da replicacao deve ser local, ter permissao `0600` e
ser referenciado por `password_env`. Nunca colocar segredos em commits, issues,
logs ou documentacao.
