"""Parsers that normalize raw Linux command output into structured JSON.

Each parser tolerates distro differences and missing fields; anything it
cannot extract is simply omitted so the answer layer can say "unknown"
instead of hallucinating.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

_GB = 1024.0**3


def _maybe_json(text: str) -> Any | None:
    stripped = text.strip()
    if not stripped or stripped[0] not in "[{":
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


def _as_list(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


def parse_tool_output(tool_name: str, stdout: str, source: str = "") -> dict[str, Any]:
    """Dispatch raw stdout to the right normalizer."""
    parsed_json = _maybe_json(stdout)
    if parsed_json is not None and sys.platform == "win32":
        win_parsers = {
            "get_cpu_info": _parse_win_cpu,
            "get_memory_summary": _parse_win_memory_summary,
            "get_memory_topology": _parse_win_memory_topology,
            "get_block_devices": _parse_win_disks,
            "get_gpu_info": _parse_win_gpu,
            "get_dmi_system": _parse_win_system,
            "get_pci_devices": _parse_win_pnp,
        }
        parser = win_parsers.get(tool_name)
        if parser:
            try:
                return parser(parsed_json)
            except Exception as exc:
                return {"error": f"Failed to parse Windows '{tool_name}' output: {exc}"}

    parsers = {
        "get_cpu_info": _parse_lscpu,
        "get_memory_summary": _parse_free,
        "get_memory_topology": _parse_dmidecode_memory,
        "get_block_devices": _parse_lsblk,
        "get_gpu_info": _parse_lspci_gpus,
        "get_dmi_system": lambda t: _parse_dmi_system(t, source),
        "get_pci_devices": _parse_lspci,
    }
    parser = parsers.get(tool_name)
    if parser is None:
        return {"raw_output": stdout}
    try:
        return parser(stdout)
    except Exception as exc:  # never crash the assistant on odd output
        return {"error": f"Failed to parse '{tool_name}' output: {exc}", "raw_output": stdout[:2000]}


# ---------------------------------------------------------------- lscpu

def _parse_lscpu(text: str) -> dict[str, Any]:
    data: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            data[key.strip()] = val.strip()

    def _int(key: str) -> int | None:
        raw = data.get(key, "")
        m = re.search(r"\d+", raw)
        return int(m.group()) if m else None

    return {
        "model_name": data.get("Model name"),
        "architecture": data.get("Architecture"),
        "cores_per_socket": _int("Core(s) per socket"),
        "sockets": _int("Socket(s)"),
        "cpus": _int("CPU(s)"),
        "mhz": data.get("CPU max MHz") or data.get("CPU MHz"),
        "raw": data,
    }


# ---------------------------------------------------------------- free

def _parse_free(text: str) -> dict[str, Any]:
    for line in text.splitlines():
        if line.startswith("Mem:"):
            parts = line.split()
            # Mem: total used free shared buff/cache available
            if len(parts) >= 7:
                total, used, _free, _shared, _cache, available = parts[1:7]
                return {
                    "total_gb": round(int(total) / _GB, 1),
                    "used_gb": round(int(used) / _GB, 1),
                    "available_gb": round(int(available) / _GB, 1),
                    "source": "free -b",
                }
    return {"error": "Could not parse 'free' output."}


# ------------------------------------------------------- dmidecode memory

def _parse_dmidecode_memory(text: str) -> dict[str, Any]:
    max_cap = re.search(r"Maximum Capacity:\s*(.+)", text)
    modules: list[dict[str, Any]] = []

    # Split into per-device blocks
    blocks = re.split(r"Memory Device\s*\n\s*Handle:", text)
    for block in blocks[1:]:
        size_m = re.search(r"Size:\s*(.+)", block)
        speed_m = re.search(r"Speed:\s*(.+)", block)
        mfr_m = re.search(r"Manufacturer:\s*(.+)", block)
        pn_m = re.search(r"Part Number:\s*(.+)", block)
        size = size_m.group(1).strip() if size_m else "Unknown"
        installed = "No Module Installed" not in size
        modules.append(
            {
                "installed": installed,
                "size": size,
                "speed": speed_m.group(1).strip() if speed_m else None,
                "manufacturer": mfr_m.group(1).strip() if mfr_m else None,
                "part_number": pn_m.group(1).strip() if pn_m else None,
            }
        )

    # Fallback: count bare "Size:" lines if block split failed
    if not modules:
        sizes = re.findall(r"Size:\s*(.+)", text)
        modules = [
            {"installed": "No Module Installed" not in s, "size": s.strip()}
            for s in sizes
        ]

    used = sum(1 for m in modules if m.get("installed"))
    return {
        "maximum_capacity": max_cap.group(1).strip() if max_cap else None,
        "total_slots": len(modules),
        "used_slots": used,
        "free_slots": len(modules) - used,
        "module_details": modules,
    }


# ---------------------------------------------------------------- lsblk

def _parse_lsblk(text: str) -> dict[str, Any]:
    raw = json.loads(text)
    devices: list[dict[str, Any]] = []

    def _walk(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            name = node.get("name")
            tran = (node.get("tran") or "").lower()
            rota = node.get("rota")
            is_nvme = bool(name and name.startswith("nvme")) or tran == "nvme"
            is_ssd = is_nvme or (rota == 0 and node.get("type") == "disk")
            devices.append(
                {
                    "name": name,
                    "size": node.get("size"),
                    "type": node.get("type"),
                    "mountpoint": node.get("mountpoint"),
                    "model": node.get("model"),
                    "rota": rota,
                    "tran": node.get("tran"),
                    "is_nvme": is_nvme,
                    "is_ssd": is_ssd,
                }
            )
            children = node.get("children")
            if children:
                _walk(children)

    _walk(raw.get("blockdevices", []))
    return {
        "devices": devices,
        "has_nvme": any(d["is_nvme"] for d in devices),
    }


# ---------------------------------------------------------------- lspci

_GPU_RE = re.compile(r"(vga|3d controller|display)", re.I)


def _parse_lspci_gpus(text: str) -> dict[str, Any]:
    gpus = [ln.strip() for ln in text.splitlines() if _GPU_RE.search(ln)]
    return {"gpus": gpus}


def _parse_lspci(text: str) -> dict[str, Any]:
    devices = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return {"devices": devices, "count": len(devices)}


# ------------------------------------------------------- dmidecode / sysfs

def _parse_dmi_system(text: str, source: str = "") -> dict[str, Any]:
    # sysfs fallback: /sys/class/dmi/id files are key=value lines
    if source.startswith("/") or "sys/class/dmi" in source:
        kv: dict[str, str] = {}
        for line in text.splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                kv[k.strip()] = v.strip()
        return {
            "manufacturer": kv.get("sys_vendor"),
            "product_name": kv.get("product_name"),
            "product_version": kv.get("product_version"),
            "board_name": kv.get("board_name"),
            "board_vendor": kv.get("board_vendor"),
            "source": "sysfs",
        }

    def _field(name: str) -> str | None:
        m = re.search(rf"{re.escape(name)}:\s*(.+)", text)
        return m.group(1).strip() if m else None

    return {
        "manufacturer": _field("Manufacturer"),
        "product_name": _field("Product Name"),
        "product_version": _field("Version"),
        "board_name": None,
        "board_vendor": None,
        "source": "dmidecode",
    }


def _parse_win_cpu(payload: Any) -> dict[str, Any]:
    cpu = _as_list(payload)[0] if _as_list(payload) else {}
    cores = cpu.get("NumberOfCores")
    logical = cpu.get("NumberOfLogicalProcessors")
    return {
        "model_name": cpu.get("Name"),
        "architecture": None,
        "cores_per_socket": cores,
        "sockets": 1,
        "cpus": logical,
        "mhz": cpu.get("MaxClockSpeed"),
        "raw": cpu,
        "source": "win32_processor",
    }


def _parse_win_memory_summary(payload: Any) -> dict[str, Any]:
    row = _as_list(payload)[0] if _as_list(payload) else {}
    total_kb = int(row.get("TotalVisibleMemorySize") or 0)
    free_kb = int(row.get("FreePhysicalMemory") or 0)
    total_gb = round(total_kb / (1024 * 1024), 1)
    free_gb = round(free_kb / (1024 * 1024), 1)
    return {
        "total_gb": total_gb,
        "used_gb": round(max(total_gb - free_gb, 0), 1),
        "available_gb": free_gb,
        "source": "win32_operatingsystem",
    }


def _parse_win_memory_topology(payload: Any) -> dict[str, Any]:
    modules = []
    for row in _as_list(payload):
        cap = int(row.get("Capacity") or 0)
        modules.append(
            {
                "installed": cap > 0,
                "size": f"{round(cap / (1024 ** 3), 1)} GB" if cap else "No Module Installed",
                "speed": row.get("Speed"),
                "manufacturer": row.get("Manufacturer"),
                "part_number": row.get("PartNumber"),
                "bank": row.get("BankLabel"),
            }
        )
    used = sum(1 for m in modules if m.get("installed"))
    return {
        "maximum_capacity": None,
        "total_slots": len(modules),
        "used_slots": used,
        "free_slots": max(len(modules) - used, 0),
        "module_details": modules,
        "source": "win32_physicalmemory",
    }


def _parse_win_disks(payload: Any) -> dict[str, Any]:
    devices = []
    for row in _as_list(payload):
        iface = str(row.get("InterfaceType") or "").lower()
        media = str(row.get("MediaType") or "").lower()
        size = int(row.get("Size") or 0)
        is_nvme = "nvme" in iface or "nvme" in media
        is_ssd = is_nvme or "ssd" in media
        devices.append(
            {
                "name": row.get("DeviceID") or row.get("Model"),
                "size": f"{round(size / (1024 ** 3), 1)}G" if size else None,
                "type": "disk",
                "mountpoint": None,
                "model": row.get("Model"),
                "tran": row.get("InterfaceType"),
                "is_nvme": is_nvme,
                "is_ssd": is_ssd,
            }
        )
    return {"devices": devices, "has_nvme": any(d["is_nvme"] for d in devices)}


def _parse_win_gpu(payload: Any) -> dict[str, Any]:
    gpus = [str(row.get("Name")) for row in _as_list(payload) if row.get("Name")]
    return {"gpus": gpus, "source": "win32_videocontroller"}


def _parse_win_system(payload: Any) -> dict[str, Any]:
    row = _as_list(payload)[0] if _as_list(payload) else payload if isinstance(payload, dict) else {}
    return {
        "manufacturer": row.get("Manufacturer"),
        "product_name": row.get("ProductName") or row.get("Model"),
        "product_version": None,
        "board_name": row.get("BoardName"),
        "board_vendor": row.get("BoardVendor"),
        "source": "win32_computersystem",
    }


def _parse_win_pnp(payload: Any) -> dict[str, Any]:
    devices = [f"{row.get('PNPClass')}: {row.get('Name')}" for row in _as_list(payload)]
    return {"devices": devices, "count": len(devices)}


def read_sysfs_dmi() -> str:
    """Helper used by fallbacks: concatenate /sys/class/dmi/id key files."""
    base = Path("/sys/class/dmi/id")
    parts: list[str] = []
    for name in (
        "sys_vendor",
        "product_name",
        "product_version",
        "product_serial",
        "board_vendor",
        "board_name",
    ):
        p = base / name
        if p.exists():
            try:
                parts.append(f"{name}={p.read_text(encoding='utf-8', errors='replace').strip()}")
            except OSError:
                continue
    return "\n".join(parts)
