# Migrations

`migrations/` 现在承载 Phase 2 的 Alembic 配置和首个核心持久化版本。

常用命令：

- `.venv/bin/alembic -c migrations/alembic.ini upgrade head`
- `.venv/bin/alembic -c migrations/alembic.ini downgrade base`
- `make test-migrations`

说明：

- 显式传入的 `sqlalchemy.url` 现在会优先于项目 settings，方便测试和临时库 smoke check。
- 未显式传入 `sqlalchemy.url` 时，Alembic 会回退到项目运行时 settings / `SIGNALARK_POSTGRES_DSN`。

目录说明：

- `migrations/alembic.ini`：Alembic 配置
- `migrations/env.py`：迁移运行环境
- `migrations/versions/`：版本脚本
