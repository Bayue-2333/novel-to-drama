"""Read-only capability snapshot. Never queues jobs or loads models."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone
from urllib.request import urlopen
from urllib.parse import urlsplit


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find_binary(name, runtime):
    direct = shutil.which(name)
    if direct:
        return direct
    suffix = ".exe" if os.name == "nt" else ""
    candidates = sorted((runtime / ".tools").glob(f"**/{name}{suffix}"))
    return str(candidates[0]) if candidates else None


def snapshot(server_url, skills_root, timeout=10):
    url = urlsplit(server_url)
    if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
        raise ValueError("Use an HTTP(S) server URL without embedded credentials")
    runtime = skills_root / "openmontage" / "runtime"
    dependencies = ["openmontage", "shuohao-skills", "novel-outline", "novel-characters",
                    "novel-art", "novel-script", "novel-storyboard"]
    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "server_url": server_url.rstrip("/"),
        "skills": {name: (skills_root / name / "SKILL.md").is_file() for name in dependencies},
        "imagegen_skill_present": (skills_root / ".system/imagegen/SKILL.md").is_file(),
        "runtime_present": runtime.is_dir(),
        "binaries": {name: find_binary(name, runtime) for name in ("node", "ffmpeg", "ffprobe")},
        "python": sys.executable,
        "errors": [],
        "generation_verified": False,
        "limitations": ["Node presence is not model/workflow readiness", "Built-in imagegen tool availability must be checked in the active session"],
    }
    payloads = {}
    for endpoint in ("system_stats", "object_info"):
        try:
            with urlopen(result["server_url"] + "/" + endpoint, timeout=timeout) as response:
                payloads[endpoint] = json.load(response)
            if not isinstance(payloads[endpoint], dict):
                raise ValueError("Expected a JSON object")
        except Exception as exc:
            result["errors"].append({"endpoint": endpoint, "type": type(exc).__name__, "message": str(exc)})
            payloads.pop(endpoint, None)
    stats = payloads.get("system_stats", {})
    result["comfyui_version"] = stats.get("system", {}).get("comfyui_version")
    result["devices"] = [{k: device.get(k) for k in ("name", "vram_total", "vram_free")}
                         for device in stats.get("devices", [])]
    info = payloads.get("object_info", {})
    result["local_h3_nodes"] = sorted(name for name, item in info.items()
                                      if "minimax_h3" in item.get("python_module", "") and not item.get("api_node"))
    result["h3_nodes_present"] = bool(result["local_h3_nodes"])
    result["status"] = "snapshot_ready" if not result["errors"] and result["h3_nodes_present"] else "needs_setup"
    return result, payloads.get("object_info")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8188")
    parser.add_argument("--skills-root", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "skills")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()
    result, info = snapshot(args.url, args.skills_root, args.timeout)
    write_json(args.out / "preflight.json", result)
    if info is not None:
        write_json(args.out / "object_info.json", info)
    else:
        # Do not leave a previous successful snapshot looking fresh after a failed GET.
        write_json(args.out / "object_info.json", {})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "snapshot_ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
