"""Run the production browser workflow against a dedicated, disposable fixture database.

Requires PostgreSQL, a built frontend, and Playwright Chromium (or an explicit
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH). Never uses market credentials or main data.
"""

import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]


def ready(url: str, process: subprocess.Popen[bytes], log: Path) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Service exited; inspect {log}")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(0.25)
    raise RuntimeError(f"Service readiness timed out; inspect {log}")


def main() -> int:
    database = os.getenv(
        "UI_TEST_DATABASE_URL",
        "postgresql+psycopg://cyclescope:cyclescope@localhost:5432/cyclescope_ui_test",
    )
    url = make_url(database)
    if not (url.database or "").endswith("_ui_test"):
        raise ValueError("UI_TEST_DATABASE_URL must identify a disposable *_ui_test database")
    admin_url = url.set(drivername="postgresql", database="postgres").render_as_string(
        hide_password=False
    )
    with psycopg.connect(admin_url, autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname=%s", (url.database,)
        ).fetchone()
        if not exists:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(url.database)))
    environment = {
        **os.environ,
        "DATABASE_URL": database,
        "MARKET_DATA_PROVIDER": "synthetic_research",
        "CYCLESCOPE_API_URL": "http://127.0.0.1:8011",
        "PLAYWRIGHT_BASE_URL": "http://127.0.0.1:3001",
        "NEXT_TELEMETRY_DISABLED": "1",
        "CYCLESCOPE_DEFAULT_AS_OF": "2024-03-28",
        "CYCLESCOPE_DEFAULT_START": "2022-04-04",
    }
    for key in ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY"):
        environment.pop(key, None)
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=environment, check=True
    )
    subprocess.run(
        [
            str(ROOT / ".venv/bin/cyclescope"),
            "ingest",
            "--universe",
            "all",
            "--start",
            "2020-01-02",
            "--end",
            "2022-11-08",
        ],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    logs = ROOT / ".local"
    logs.mkdir(exist_ok=True)
    processes: list[subprocess.Popen[bytes]] = []
    try:
        with (
            (logs / "e2e-api.log").open("wb") as api_log,
            (logs / "e2e-web.log").open("wb") as web_log,
        ):
            backend = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "cyclescope.api.app:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8011",
                ],
                cwd=ROOT,
                env=environment,
                stdout=api_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            processes.append(backend)
            ready("http://127.0.0.1:8011/health", backend, logs / "e2e-api.log")
            frontend = subprocess.Popen(
                ["npm", "run", "start", "--", "--port", "3001"],
                cwd=ROOT / "frontend",
                env=environment,
                stdout=web_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            processes.append(frontend)
            ready("http://127.0.0.1:3001", frontend, logs / "e2e-web.log")
            return subprocess.run(
                ["npm", "run", "test:e2e"], cwd=ROOT / "frontend", env=environment, check=False
            ).returncode
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
