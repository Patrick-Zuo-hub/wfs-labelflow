import socket
import threading
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(Settings(runtime_root=tmp_path / "jobs")))


@pytest.fixture
def live_server_url(tmp_path: Path) -> str:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    config = uvicorn.Config(
        create_app(Settings(runtime_root=tmp_path / "browser-jobs")),
        host="127.0.0.1",
        port=port,
        log_level="error",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        thread.join(0.01)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)
