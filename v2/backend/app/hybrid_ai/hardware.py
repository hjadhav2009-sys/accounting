from __future__ import annotations

import os
import shutil
import socket
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class HardwareProfile:
    logical_cpu_count: int
    available_ram_gb: float | None
    gpu_name: str
    vram_gb: float | None
    free_disk_gb: float
    profile: str
    local_runtime: str
    runtime_healthy: bool

    def public(self) -> dict[str, object]: return asdict(self)


def _localhost_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=.15): return True
    except OSError: return False


def detect_hardware(storage_root: Path) -> HardwareProfile:
    free_gb = shutil.disk_usage(storage_root.resolve().anchor).free / 1024 ** 3
    ram_gb: float | None = None
    try:
        import ctypes
        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong),
                        ("total_phys", ctypes.c_ulonglong), ("avail_phys", ctypes.c_ulonglong),
                        ("total_page", ctypes.c_ulonglong), ("avail_page", ctypes.c_ulonglong),
                        ("total_virtual", ctypes.c_ulonglong), ("avail_virtual", ctypes.c_ulonglong),
                        ("avail_extended", ctypes.c_ulonglong)]
        status = MemoryStatus(); status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            ram_gb = round(status.total_phys / 1024 ** 3, 1)
    except (AttributeError, OSError): pass
    runtime = next((name for name in ("llama-server", "llama-cli", "ollama") if shutil.which(name)), "")
    healthy = _localhost_open(8080) or _localhost_open(11434)
    if healthy and not runtime: runtime = "localhost-compatible-server"
    cpu = os.cpu_count() or 1
    profile = "LITE"
    if ram_gb and ram_gb >= 32 and cpu >= 8: profile = "ADVANCED"
    elif ram_gb and ram_gb >= 16 and cpu >= 4: profile = "STANDARD"
    return HardwareProfile(cpu, ram_gb, "Intel(R) HD Graphics 620" if os.name == "nt" else "unknown",
                           None, round(free_gb, 1), profile, runtime, healthy)
