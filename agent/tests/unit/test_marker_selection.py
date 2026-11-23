from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


FIXTURE_TEMPLATE = """\
import socket

def _deny_network(*args, **kwargs):
    raise AssertionError("marker fixtures must remain offline")

socket.create_connection = _deny_network
socket.getaddrinfo = _deny_network
socket.socket.connect = _deny_network

"""


def _run_fixture_tests(agent_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "LANGCHAIN_TRACING_V2": "false",
            "LANGSMITH_TRACING": "false",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        }
    )
    env.pop("LANGCHAIN_API_KEY", None)
    env.pop("LANGSMITH_API_KEY", None)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            str(agent_root / "pyproject.toml"),
            *args,
            "--collect-only",
            "-q",
        ],
        cwd=agent_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )


def test_default_and_explicit_marker_selection(tmp_path: Path) -> None:
    agent_root = Path(__file__).parents[2]
    common = FIXTURE_TEMPLATE
    live_fixture = tmp_path / "test_live_fixture.py"
    redis_fixture = tmp_path / "test_redis_fixture.py"
    baseline_fixture = tmp_path / "test_baseline_fixture.py"
    live_fixture.write_text(
        common
        + "\nimport pytest\n\n@pytest.mark.live\ndef test_live():\n    pass\n",
        encoding="utf-8",
    )
    redis_fixture.write_text(
        common
        + "\nimport pytest\n\n@pytest.mark.redis\ndef test_redis():\n    pass\n",
        encoding="utf-8",
    )
    baseline_fixture.write_text(
        common + "\ndef test_baseline():\n    pass\n",
        encoding="utf-8",
    )
    fixtures = (str(baseline_fixture), str(live_fixture), str(redis_fixture))

    default = _run_fixture_tests(agent_root, *fixtures)
    assert default.returncode == 0, default.stdout + default.stderr
    assert "test_baseline" in default.stdout
    assert "test_live" not in default.stdout
    assert "test_redis" not in default.stdout

    live = _run_fixture_tests(agent_root, *fixtures, "-m", "live")
    assert live.returncode == 0, live.stdout + live.stderr
    assert "test_baseline" not in live.stdout
    assert "test_live" in live.stdout
    assert "test_redis" not in live.stdout

    redis = _run_fixture_tests(agent_root, *fixtures, "-m", "redis")
    assert redis.returncode == 0, redis.stdout + redis.stderr
    assert "test_baseline" not in redis.stdout
    assert "test_live" not in redis.stdout
    assert "test_redis" in redis.stdout
