"""
actions/cmd_control.py — ClawOS Terminal / Shell Control

Execute shell commands, run scripts, manage processes.
Maps to: cmd_control tool in executor.
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any


def _get_shell() -> str:
    if sys.platform == "win32":
        return "powershell.exe"
    return "/bin/bash"


def _run_cmd(cmd: str, timeout: int = 30, capture: bool = True) -> dict:
    """Run a shell command and return output."""
    shell = _get_shell()
    is_win = sys.platform == "win32"
    exe = "cmd.exe" if is_win else "/bin/bash"
    args = ["-c", cmd] if not is_win else ["/c", cmd]

    try:
        if capture:
            result = subprocess.run(
                [exe] + args,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=os.getcwd(),
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        else:
            subprocess.run([exe] + args, check=True, timeout=timeout, cwd=os.getcwd())
            return {"success": True, "stdout": "", "stderr": "", "returncode": 0}
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": f"Command timed out after {timeout}s", "returncode": -1}
    except FileNotFoundError:
        return {"success": False, "stdout": "", "stderr": f"Shell not found: {exe}", "returncode": -1}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}


def cmd_control(parameters: dict, player: Any = None) -> str:
    """
    Execute a terminal/shell command.
    Parameters:
        command (str): The shell command to run.
        timeout (int, optional): Timeout in seconds. Default 30.
        capture (bool, optional): Capture stdout/stderr. Default True.
    Returns:
        str: Human-readable result.
    """
    if not isinstance(parameters, dict):
        parameters = {"command": str(parameters)}

    command = parameters.get("command", "")
    if not command:
        return "cmd_control: no command provided"

    timeout = int(parameters.get("timeout", 30))
    capture = parameters.get("capture", True)

    result = _run_cmd(command, timeout=timeout, capture=capture)

    if result["success"]:
        output = result.get("stdout", "").strip()
        if output:
            # Truncate long output
            if len(output) > 2000:
                output = output[:2000] + f"\n... [truncated, {len(output)} total chars]"
            return f"Ran successfully:\n{output}"
        return "Command completed successfully (no output)."
    else:
        stderr = result.get("stderr", "").strip()
        return f"Command failed (code {result['returncode']}):\n{stderr}"


# Expose as both function and module-level callable
def run_command(command: str, timeout: int = 30) -> dict:
    """Direct command runner. Returns dict with success/stdout/stderr."""
    return _run_cmd(command, timeout=timeout)
