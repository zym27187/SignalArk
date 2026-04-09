from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def test_run_dev_stack_applies_migrations_before_starting_services(tmp_path: Path) -> None:
    root_dir = tmp_path / "workspace"
    scripts_dir = root_dir / "scripts"
    venv_bin_dir = root_dir / ".venv" / "bin"
    web_dir = root_dir / "apps" / "web"
    migrations_dir = root_dir / "migrations"
    fake_bin_dir = tmp_path / "bin"
    log_path = tmp_path / "run-dev-stack.log"

    scripts_dir.mkdir(parents=True)
    venv_bin_dir.mkdir(parents=True)
    web_dir.mkdir(parents=True)
    migrations_dir.mkdir(parents=True)
    fake_bin_dir.mkdir(parents=True)

    script_path = scripts_dir / "run_dev_stack.sh"
    script_path.write_text(
        (ROOT_DIR / "scripts" / "run_dev_stack.sh").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR)

    (web_dir / "package.json").write_text('{"name":"signalark-web"}\n', encoding="utf-8")
    (web_dir / "node_modules").mkdir()
    (migrations_dir / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")
    (root_dir / ".env").write_text(
        "SIGNALARK_POSTGRES_DSN=sqlite:///signalark-dev.sqlite3\n",
        encoding="utf-8",
    )

    logging_sleep = "sleep 1\n"
    _write_executable(
        venv_bin_dir / "alembic",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf 'alembic %s\\n' \"$*\" >> \"$SIGNALARK_LOG_PATH\"\n",
    )
    _write_executable(
        venv_bin_dir / "uvicorn",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf 'uvicorn %s\\n' \"$*\" >> \"$SIGNALARK_LOG_PATH\"\n"
        + logging_sleep,
    )
    _write_executable(
        venv_bin_dir / "python",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf 'python %s\\n' \"$*\" >> \"$SIGNALARK_LOG_PATH\"\n"
        + logging_sleep,
    )
    _write_executable(
        fake_bin_dir / "npm",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf 'npm %s\\n' \"$*\" >> \"$SIGNALARK_LOG_PATH\"\n"
        + logging_sleep,
    )

    env = dict(os.environ)
    env["PATH"] = f"{fake_bin_dir}:{env['PATH']}"
    env["SIGNALARK_INCLUDE_TRADER"] = "1"
    env["SIGNALARK_LOG_PATH"] = str(log_path)

    completed = subprocess.run(
        ["bash", str(script_path)],
        cwd=root_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )

    log_lines = log_path.read_text(encoding="utf-8").splitlines()

    assert completed.stdout.splitlines()[0] == "Applying database migrations"
    assert "Starting SignalArk trader runtime" in completed.stdout
    assert log_lines[0] == f"alembic -c {root_dir / 'migrations' / 'alembic.ini'} upgrade head"
    assert any(
        line == "uvicorn apps.api.main:app --factory --host 0.0.0.0 --port 8000 --reload"
        for line in log_lines
    )
    assert any(
        line
        == f"npm --prefix {root_dir / 'apps' / 'web'} run dev -- --host 127.0.0.1 --port 5173"
        for line in log_lines
    )
    assert any(line == "python -m apps.trader.main" for line in log_lines)
