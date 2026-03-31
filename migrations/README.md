# Migrations

`migrations/` 现在承载 Phase 2 的 Alembic 配置和首个核心持久化版本。

常用命令：

- `.venv/bin/alembic -c migrations/alembic.ini upgrade head`
- `.venv/bin/alembic -c migrations/alembic.ini downgrade base`

目录说明：

- `migrations/alembic.ini`：Alembic 配置
- `migrations/env.py`：迁移运行环境
- `migrations/versions/`：版本脚本
