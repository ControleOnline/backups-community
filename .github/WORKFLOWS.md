# CI/CD (backups-community)

O projeto deve validar cada alteracao com a suite Python e o lint. Apos a
promocao, `master`, `dev` e o checkout do servidor devem apontar para o mesmo
SHA. O servidor nao executa uma branch divergente de `master`.

Configuracoes, credenciais, dumps, logs e estado temporario sao dados de
runtime e permanecem fora do Git.
