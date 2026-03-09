# Render pago: checklist rapido (3 meses de teste)

## 1) Blueprint/planos
- Arquivo `render.yaml` ja preparado com:
  - Web service: `starter`
  - Banco Postgres: `basic-256mb`

## 2) Variaveis no Render
- Confirmar no servico web:
  - `DATABASE_URL` (fromDatabase -> connectionString)
  - `SECRET_KEY` (gerada)
  - `SITE_EM_CONFIGURACAO=0`
  - `RESET_DATABASE_ON_START=0`

## 3) Migrar dados do SQLite atual
- No seu ambiente local (na raiz do projeto), rode:

```powershell
$env:DATABASE_URL="<External Database URL do Render Postgres>"
$env:SQLITE_PATH="controle_processos.db"
$env:TRUNCATE_FIRST="1"
python scripts/migrate_sqlite_to_postgres.py
```

- Observacoes:
  - Use a **External Database URL** do Render (normalmente ja vem com SSL).
  - `TRUNCATE_FIRST=1` apaga dados do Postgres antes de copiar.

## 4) Validacao apos deploy
- Entrar no sistema e validar:
  - login
  - dashboard
  - gerencias
  - verificar dados (processos/demandas)
  - importacao e exportacao

## 5) Rollback rapido
- Se algo falhar:
  - voltar o deploy para commit anterior no Render
  - manter `RESET_DATABASE_ON_START=0`
