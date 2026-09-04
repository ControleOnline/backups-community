# AGENTS — backups-community

Ponte curta para a documentação técnica deste repositório.

## Wiki técnica

| Categoria | Página |
| --- | --- |
| Início | [Home](https://github.com/ControleOnline/backups-community/wiki) |
| Arquitetura e contratos | [Architecture](https://github.com/ControleOnline/backups-community/wiki/Architecture) |
| Configuração JSON | [Configuration](https://github.com/ControleOnline/backups-community/wiki/Configuration) |
| Replicação MySQL | [Replication](https://github.com/ControleOnline/backups-community/wiki/Replication) |
| Operação e cron | [Operations](https://github.com/ControleOnline/backups-community/wiki/Operations) |
| Desenvolvimento / testes | [Development](https://github.com/ControleOnline/backups-community/wiki/Development) |

## Escopo

CLI local de backup/restore/manutenção (Python 3.11+). Provider inicial: MySQL.
Sem interface HTTP. Sem participação em `APP_TYPE` de produto.

## Relacionados

- Operação de bases usadas por `api-community` e ambientes de staging/dev do ecossistema ControleOnline.
- README na raiz do repositório para uso rápido e exemplos.

## Regras para agents



- Não versionar credenciais, `config/*.json` reais, dumps ou logs.
- Documentação técnica canônica vive na **wiki** deste repositório; este arquivo só indexa.
