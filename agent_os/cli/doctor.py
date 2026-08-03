import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from agent_os.backends import build_default_registry
from agent_os.checkpoints import DEFAULT_CHECKPOINT_DB
from agent_os.sandbox import get_sandbox_root


def run_doctor(json_output: bool) -> tuple[int, str]:
    warnings: list[str] = []
    exit_code = 0

    registry = build_default_registry()
    adapters_info: list[dict[str, Any]] = []

    for _, adapter in registry.items():

        # Binary check without subprocess
        import shutil
        binary_path = shutil.which(adapter.binary_name)

        if binary_path is None:
            auth_status = {"status": "unknown", "detail": f"Binary '{adapter.binary_name}' not found on PATH."}
        else:
            status_obj = adapter.authentication_status()
            auth_status = {"status": status_obj.status, "detail": status_obj.detail}

        adapters_info.append({
            "name": adapter.name,
            "binary_name": adapter.binary_name,
            "supported_roles": sorted(list(adapter.supported_roles)),
            "binary_path": binary_path,
            "auth_status": auth_status
        })

    resolved_config = {
        "router": os.getenv("LLM_ROUTER"),
        "architect": os.getenv("LLM_ARCHITECT"),
        "executor": os.getenv("LLM_EXECUTOR"),
        "sandbox": str(get_sandbox_root().resolve())
    }

    checkpoint_env = os.getenv("AGENT_OS_CHECKPOINTS_DB")
    cp_path_str = checkpoint_env if checkpoint_env is not None else DEFAULT_CHECKPOINT_DB
    cp_path = Path(cp_path_str).resolve()

    cp_exists = cp_path.exists()
    cp_writable = False

    if cp_exists:
        cp_writable = os.access(cp_path, os.W_OK)
        try:
            conn = sqlite3.connect(f"file:{cp_path}?mode=ro", uri=True)
            conn.close()
        except Exception as e:
            warnings.append(f"Checkpoint DB is not readable: {e}")
    else:
        cp_writable = os.access(cp_path.parent, os.W_OK)
        if not cp_writable:
            warnings.append(f"Checkpoint DB parent directory is not writable: {cp_path.parent}")

    if not cp_writable:
        warnings.append("Checkpoint DB is not writable.")
        exit_code = 1

    checkpoints_db = {
        "path": str(cp_path),
        "exists": cp_exists,
        "writable": cp_writable
    }

    # Validate configured config
    for role in ["architect", "executor"]:
        backend_str = resolved_config[role]
        if backend_str and backend_str.startswith("cli/"):
            backend_name = backend_str[4:]

            adapter_info = next((a for a in adapters_info if a["name"] == backend_name), None)
            if not adapter_info:
                warnings.append(f"Configured {role} backend '{backend_str}' is not registered.")
                exit_code = 1
                continue

            if role not in adapter_info["supported_roles"]:
                warnings.append(f"Configured {role} backend '{backend_str}' does not support role '{role}'.")
                exit_code = 1

            if adapter_info["binary_path"] is None:
                warnings.append(f"Configured {role} backend '{backend_str}' binary is missing.")
                exit_code = 1

            if adapter_info["auth_status"]["status"] == "unauthenticated":
                warnings.append(f"Configured {role} backend '{backend_str}' is unauthenticated.")
                exit_code = 1
            elif adapter_info["auth_status"]["status"] == "unknown":
                warnings.append(f"Configured {role} backend '{backend_str}' auth status is unknown.")

    report = {
        "registered_adapters": adapters_info,
        "resolved_config": resolved_config,
        "profile": None,
        "checkpoints_db": checkpoints_db,
        "warnings": warnings
    }

    if json_output:
        return exit_code, json.dumps(report, indent=2)

    # Render human output
    lines = []
    lines.append("Registered adapters")
    lines.append("-------------------")
    if not adapters_info:
        lines.append("none")
    for ad in adapters_info:
        lines.append(f"- {ad['name']} ({ad['binary_name']})")
        lines.append(f"  Roles : {', '.join(ad['supported_roles'])}")
        lines.append(f"  Binary: {ad['binary_path'] or 'missing'}")
        lines.append(f"  Auth  : {ad['auth_status']['status']} ({ad['auth_status']['detail']})")

    lines.append("")
    lines.append("Resolved config")
    lines.append("---------------")
    for k, v in resolved_config.items():
        lines.append(f"{k.capitalize()}: {v if v is not None else 'null'}")

    lines.append("")
    lines.append("Profile: none")

    lines.append("")
    lines.append("Checkpoints DB")
    lines.append("--------------")
    lines.append(f"Path    : {checkpoints_db['path']}")
    lines.append(f"Exists  : {'yes' if checkpoints_db['exists'] else 'no'}")
    lines.append(f"Writable: {'yes' if checkpoints_db['writable'] else 'no'}")

    lines.append("")
    lines.append("Warnings")
    lines.append("--------")
    if not warnings:
        lines.append("none")
    else:
        for w in warnings:
            lines.append(f"- {w}")

    lines.append("")
    if exit_code == 0:
        lines.append("STATUS: OK")
    else:
        lines.append("STATUS: FAIL")

    return exit_code, "\n".join(lines)
