"""Isolated Docker code execution sandbox."""

import json
import os
from typing import Any

import docker
from docker.errors import ContainerError, ImageNotFound


def run_code_in_sandbox(code: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Run arbitrary Python code inside a resource-constrained Docker container.

    The container receives a JSON payload via stdin:
      {"code": "...", "data": {...}}

    Returns stdout/stderr on success, or an error dict on failure/timeout.
    """
    image = os.getenv("SANDBOX_IMAGE", "analyst-sandbox:latest")
    payload = json.dumps({"code": code, "data": data or {}})

    try:
        client = docker.from_env()

        container = client.containers.run(
            image=image,
            command=None,
            stdin_open=True,
            detach=True,
            mem_limit="256m",
            cpu_period=100000,
            cpu_quota=50000,
            network_disabled=True,
            remove=False,
        )

        # Write payload to container stdin
        try:
            sock = container.attach_socket(
                params={"stdin": 1, "stream": 1, "stdout": 0, "stderr": 0}
            )
            sock._sock.sendall((payload + "\n").encode("utf-8"))
            sock._sock.close()
        except Exception:
            pass

        # Wait up to 10 seconds
        try:
            result = container.wait(timeout=10)
            exit_code = result.get("StatusCode", 0)
        except Exception:
            container.kill()
            container.remove(force=True)
            return {"success": False, "error": "Execution timed out after 10s"}

        stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
        stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
        container.remove(force=True)

        if exit_code != 0:
            return {"success": False, "error": stderr or "Non-zero exit code", "stdout": stdout, "stderr": stderr}

        return {"success": True, "stdout": stdout, "stderr": stderr}

    except ImageNotFound:
        return {
            "success": False,
            "error": f"Sandbox image '{image}' not found. Run: cd sandbox_image && docker build -t analyst-sandbox:latest .",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}
