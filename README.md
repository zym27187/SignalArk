# SignalArk

SignalArk 是一个面向个人项目的 `paper trading` V1 仓库。

当前仓库包含两部分内容：

- `v1-ai-execution-phases/`：按阶段拆分的 AI 执行说明
- 最小 Python 工程模板：为后续 `Phase 0 -> Phase 9` 落代码准备目录、依赖和入口骨架

## 基线技术栈

- Python `3.12`
- `uv` 负责依赖与虚拟环境
- `FastAPI` 作为控制面 API
- `Pydantic v2 + pydantic-settings` 作为配置与数据校验基础
- `SQLAlchemy 2.0 + Alembic + psycopg` 作为 PostgreSQL 持久化基线
- `structlog` 负责结构化日志
- `pytest` 负责单元、集成和 e2e 测试

详细约定见：

- `v1-ai-execution-phases/implementation-decisions.md`

## 当前目录骨架

```text
apps/
  api/
  trader/
  collector/
  research/
configs/
migrations/
src/
tests/
v1-ai-execution-phases/
```

## 推荐起步方式

1. 先阅读 `v1-ai-execution-phases/00-master-plan.md`
2. 再阅读 `v1-ai-execution-phases/testing-standards.md`
3. 再阅读 `v1-ai-execution-phases/implementation-decisions.md`
4. 复制 `.env.example` 为本地 `.env`
5. 执行 `uv sync --all-extras`
6. 从 `Phase 0` 开始落代码

## 常用命令

```bash
make install
make lint
make format
make test-unit
make api
```

## 说明

- 现在的 `apps/api/main.py`、`apps/trader/main.py`、`apps/collector/main.py` 仅提供最小入口骨架
- 真正的交易语义、数据库、控制面和风控仍应按 phase 文档顺序实现

