
"""Run untrusted repository tests inside a restricted Docker container."""

from __future__ import annotations

import os
import selectors
import subprocess
import time
import uuid
from pathlib import Path


WORKER_IMAGE = os.getenv(
    "AUTORESOLVE_WORKER_IMAGE",
    "autoresolve-test-worker:python312",
)

MAX_OUTPUT_BYTES = 64 * 1024


def run_pytest_in_worker(
    repo_path: Path,
    test_args: list[str] | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess:
    """Run pytest in Docker while retaining only bounded output."""

    repo_root = repo_path.resolve()
    if not repo_root.is_dir():
        raise FileNotFoundError("Worker repository directory is missing.")
    if timeout <= 0:
        raise ValueError("Worker timeout must be positive.")
    if test_args is not None:
        if not isinstance(test_args, list) or any(
            not isinstance(arg, str)
            or not arg
            or arg.startswith("-")
            or Path(arg).is_absolute()
            or ".." in Path(arg).parts
            for arg in test_args
        ):
            raise ValueError("Invalid test arguments.")

    container_name = f"autoresolve-worker-{uuid.uuid4().hex[:12]}"

    container_user = (
        f"{os.getuid()}:{os.getgid()}"
        if hasattr(os, "getuid") and hasattr(os, "getgid")
        else "65534:65534"
    )

    command = [
        "docker", "run", "--rm",
        "--name", container_name,
        "--network", "none",
        "--read-only",
        "--cap-drop", "ALL",
        "--pids-limit", "64",
        "--memory", "256m",
        "--cpus", "0.5",
        "--user", container_user,
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
        "--mount", f"type=bind,src={repo_root},dst=/workspace,readonly",
        "--workdir", "/workspace",
        "--env", "PYTHONDONTWRITEBYTECODE=1",
        "--env", "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
        "--entrypoint", "python",
        WORKER_IMAGE,
        "-m", "pytest", "-q", "-p", "no:cacheprovider",
    ]

    if test_args:
        command.extend(test_args)

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
        bufsize=0,
    )

    buffers = {
        "stdout": bytearray(),
        "stderr": bytearray(),
    }
    truncated = {"stdout": False, "stderr": False}

    def retain(name: str, chunk: bytes) -> None:
        buffer = buffers[name]
        buffer.extend(chunk)
        if len(buffer) > MAX_OUTPUT_BYTES:
            del buffer[:-MAX_OUTPUT_BYTES]
            truncated[name] = True

    deadline = time.monotonic() + timeout

    if os.name == "nt":
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True,
                timeout=10,
                check=False,
            )
            raise

        stdout_text = stdout.decode("utf-8", errors="replace")[-MAX_OUTPUT_BYTES:]
        stderr_text = stderr.decode("utf-8", errors="replace")[-MAX_OUTPUT_BYTES:]

        if process.returncode in (125, 126, 127):
            raise RuntimeError(
                f"Docker worker failed (exit {process.returncode}): "
                f"{stderr_text[-500:]}"
            )

        return subprocess.CompletedProcess(
            command,
            process.returncode,
            stdout_text,
            stderr_text,
        )
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")

            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)

                events = selector.select(min(remaining, 0.5))
                for key, _ in events:
                    chunk = os.read(key.fileobj.fileno(), 8192)
                    if chunk:
                        retain(key.data, chunk)
                    else:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()

                if process.poll() is not None and not events:
                    # Continue until both pipes reach EOF.
                    continue

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(command, timeout)
        returncode = process.wait(timeout=remaining)


    except subprocess.TimeoutExpired as exc:
        try:
            process.kill()
        except (OSError, PermissionError):
            pass
        try:
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            pass

        def decode_partial(name: str) -> str:
            text = bytes(buffers[name]).decode("utf-8", errors="replace")
            if truncated[name]:
                text = "[Earlier output truncated; showing final output only.]\n" + text
            return text

        exc.stdout = decode_partial("stdout")
        exc.stderr = decode_partial("stderr")

        try:
            subprocess.run(
                ["docker", "kill", container_name],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

        try:
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

        raise
    except KeyboardInterrupt:
        try:
            process.kill()
        except (OSError, PermissionError):
            pass
        try:
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            pass

        try:
            subprocess.run(
                ["docker", "kill", container_name],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

        try:
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

        raise

    finally:
        try:
            if process.poll() is None:
                try:
                    process.kill()
                except (OSError, PermissionError):
                    pass
                try:
                    process.wait(timeout=2)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        finally:
            for stream in (process.stdout, process.stderr):
                if stream is not None and not stream.closed:
                    stream.close()

    def decode_output(name: str) -> str:
        text = bytes(buffers[name]).decode("utf-8", errors="replace")
        if truncated[name]:
            text = "[Earlier output truncated; showing final output only.]\n" + text
        return text

    stdout_text = decode_output("stdout")
    stderr_text = decode_output("stderr")

    # pytest itself only exits with 0-5. 125/126/127 come from Docker: the
    # daemon is not running, the image is missing, or the command was not found.
    # Without this check that looks like "the test failed", which is misleading.
    if returncode in (125, 126, 127):
        raise RuntimeError(
            "Docker could not start the test worker "
            f"(exit {returncode}). Is Docker running and is the image "
            f"'{WORKER_IMAGE}' built? Details: {stderr_text.strip()[-500:]}"
        )

    return subprocess.CompletedProcess(
        command,
        returncode,
        stdout_text,
        stderr_text,
    )
