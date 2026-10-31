
import subprocess
import sys

import pytest

from backend.orchestrator import docker_worker


def test_worker_never_falls_back_to_host_pytest(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()

    def fail_docker(*args, **kwargs):
        raise FileNotFoundError("Docker executable unavailable")

    monkeypatch.setattr(docker_worker.subprocess, "Popen", fail_docker)

    with pytest.raises(FileNotFoundError, match="Docker executable unavailable"):
        docker_worker.run_pytest_in_worker(repo)


def test_worker_requests_restricted_docker_settings(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    captured = {}

    real_popen = subprocess.Popen

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs

        # Run a harmless local process to test output handling without Docker.
        return real_popen(
            [
                sys.executable,
                "-c",
                "import sys; print('worker-ok'); print('worker-error', file=sys.stderr)",
            ],
            **kwargs,
        )

    monkeypatch.setattr(docker_worker.subprocess, "Popen", fake_popen)

    result = docker_worker.run_pytest_in_worker(repo)
    command = captured["command"]

    assert result.returncode == 0
    assert "worker-ok" in result.stdout
    assert "worker-error" in result.stderr

    assert "--network" in command
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command
    assert "--cap-drop" in command
    assert command[command.index("--cap-drop") + 1] == "ALL"
    assert "--pids-limit" in command
    assert "--memory" in command
    assert "--cpus" in command
    assert "--user" in command
    assert "--mount" in command
    mount_value = command[command.index("--mount") + 1]
    assert "dst=/workspace,readonly" in mount_value

    assert command[-5:] == [
        "-m", "pytest", "-q", "-p", "no:cacheprovider"
    ]

    assert captured["kwargs"]["stdout"] == subprocess.PIPE
    assert captured["kwargs"]["stderr"] == subprocess.PIPE
    assert captured["kwargs"]["text"] is False
    assert captured["kwargs"]["bufsize"] == 0


def test_worker_bounds_large_output(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()

    real_popen = subprocess.Popen

    def fake_popen(command, **kwargs):
        return real_popen(
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.write('x' * 100000 + '\\nFINAL-MARKER\\n')",
            ],
            **kwargs,
        )

    monkeypatch.setattr(docker_worker.subprocess, "Popen", fake_popen)

    result = docker_worker.run_pytest_in_worker(repo)

    assert result.returncode == 0
    assert len(result.stdout.encode("utf-8")) < docker_worker.MAX_OUTPUT_BYTES + 100
    assert "Earlier output truncated" in result.stdout
    assert "FINAL-MARKER" in result.stdout


def test_worker_cleans_up_container_on_timeout(tmp_path, monkeypatch):
    import os

    repo = tmp_path / "repo"
    repo.mkdir()
    cleanup_commands = []

    class FakeProcess:
        def __init__(self):
            stdout_r, stdout_w = os.pipe()
            stderr_r, stderr_w = os.pipe()
            os.close(stdout_w)
            os.close(stderr_w)

            self.stdout = os.fdopen(stdout_r, "rb", buffering=0)
            self.stderr = os.fdopen(stderr_r, "rb", buffering=0)
            self.returncode = None

        def poll(self):
            return None

        def kill(self):
            self.returncode = -9

        def wait(self, timeout=None):
            self.returncode = -9
            return self.returncode

    def fake_popen(command, **kwargs):
        return FakeProcess()

    def fake_run(command, **kwargs):
        cleanup_commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(docker_worker.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(docker_worker.subprocess, "run", fake_run)
    monkeypatch.setattr(docker_worker.time, "monotonic", iter([0, 0, 2]).__next__)

    with pytest.raises(subprocess.TimeoutExpired):
        docker_worker.run_pytest_in_worker(repo, timeout=1)

    assert len(cleanup_commands) == 2
    assert cleanup_commands[0][:2] == ["docker", "kill"]
    assert cleanup_commands[1][:3] == ["docker", "rm", "-f"]
    assert cleanup_commands[0][2] == cleanup_commands[1][3]

def test_worker_rejects_path_traversal_test_args(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    docker_started = False

    def fake_popen(*args, **kwargs):
        nonlocal docker_started
        docker_started = True
        raise AssertionError("Docker must not start for invalid test arguments")

    monkeypatch.setattr(docker_worker.subprocess, "Popen", fake_popen)

    with pytest.raises(ValueError, match="Invalid test arguments"):
        docker_worker.run_pytest_in_worker(
            repo,
            ["../outside.py"],
        )

    assert docker_started is False

@pytest.mark.parametrize(
    "bad_args",
    [
        "../outside.py",
        ["../outside.py"],
        "tests/test_example.py",
        [""],
        [123],
        ["--help"],
        ["/etc/passwd"],
    ],
)
def test_worker_rejects_invalid_test_args_before_launch(
    tmp_path, monkeypatch, bad_args
):
    repo = tmp_path / "repo"
    repo.mkdir()

    def unexpected_popen(*args, **kwargs):
        raise AssertionError("Docker must not start for invalid arguments")

    monkeypatch.setattr(docker_worker.subprocess, "Popen", unexpected_popen)

    with pytest.raises(ValueError, match="Invalid test arguments"):
        docker_worker.run_pytest_in_worker(repo, bad_args)

def test_worker_accepts_safe_relative_test_path(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    captured = {}

    class FakeProcess:
        def __init__(self):
            import os

            stdout_r, stdout_w = os.pipe()
            stderr_r, stderr_w = os.pipe()
            os.write(stdout_w, b"1 passed\n")
            os.close(stdout_w)
            os.close(stderr_w)
            self.stdout = os.fdopen(stdout_r, "rb", buffering=0)
            self.stderr = os.fdopen(stderr_r, "rb", buffering=0)
            self.returncode = 0

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            return self.returncode

    def fake_popen(command, **kwargs):
        captured["command"] = command
        return FakeProcess()

    monkeypatch.setattr(docker_worker.subprocess, "Popen", fake_popen)

    result = docker_worker.run_pytest_in_worker(
        repo,
        ["tests/test_example.py"],
    )

    assert result.returncode == 0
    assert captured["command"][-1] == "tests/test_example.py"