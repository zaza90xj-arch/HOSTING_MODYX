"""Server detection and live metrics. Everything here is measured on the machine the panel runs on.
Nothing is invented: when a value cannot be read, it is returned as None / the call raises, and the UI shows 'unavailable'."""
import ipaddress
import os
import platform
import shutil
import socket
import subprocess
import time
from pathlib import Path

TOOLS = ("python3", "pip3", "node", "npm", "git", "docker", "nginx")
SUPPORTED_ARCH = ("x86_64", "amd64", "aarch64", "arm64")


def _os_release():
    data = {}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                data[k] = v.strip().strip('"')
    except OSError:
        pass
    return data


def _tool_version(name):
    path = shutil.which(name)
    if not path:
        return None
    try:
        r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=3)
        out = (r.stdout or r.stderr).strip().splitlines()
        return out[0][:80] if out else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def in_container():
    if Path("/.dockerenv").exists():
        return True
    try:
        txt = Path("/proc/1/cgroup").read_text()
        return any(x in txt for x in ("docker", "kubepods", "lxc", "containerd"))
    except OSError:
        return False


def interfaces():
    import psutil
    out = []
    for name, addrs in psutil.net_if_addrs().items():
        for a in addrs:
            if a.family == socket.AF_INET:
                ip = ipaddress.ip_address(a.address)
                scope = "loopback" if ip.is_loopback else "private" if ip.is_private else "public"
                out.append({"name": name, "ip": a.address, "scope": scope})
    return out


def detect(storage_root):
    """Static facts about this machine. Returns {'ok': False} if psutil is unavailable."""
    try:
        import psutil
    except ImportError:
        return {"ok": False}
    osr = _os_release()
    du = shutil.disk_usage(storage_root)
    vm = psutil.virtual_memory()
    arch = platform.machine().lower()
    ifaces = interfaces()
    info = {
        "ok": True,
        "system": platform.system(),
        "os": osr.get("PRETTY_NAME") or platform.platform(),
        "os_id": osr.get("ID", ""),
        "kernel": platform.release(),
        "arch": arch,
        "cpu_logical": psutil.cpu_count(logical=True),
        "cpu_physical": psutil.cpu_count(logical=False),
        "ram_total": vm.total,
        "disk_total": du.total, "disk_free": du.free,
        "uptime_h": round((time.time() - psutil.boot_time()) / 3600, 1),
        "interfaces": ifaces,
        "has_public_ip": any(i["scope"] == "public" for i in ifaces),
        "container": in_container(),
        "root": hasattr(os, "geteuid") and os.geteuid() == 0,
        "tools": {t: _tool_version(t) for t in TOOLS},
    }
    warn = []
    if info["system"] != "Linux":
        warn.append("warn_not_linux")
    if arch not in SUPPORTED_ARCH:
        warn.append("warn_arch")
    if info["root"]:
        warn.append("warn_root")
    if info["container"]:
        warn.append("warn_container")
    if info["ram_total"] < 900 * 1024 * 1024:
        warn.append("warn_low_ram")
    if du.total and du.used / du.total > 0.85:
        warn.append("warn_disk")
    info["warnings"] = warn
    return info


def metrics(storage_root):
    """Live numbers. Raises on failure so the API can answer 503 instead of fake zeros."""
    import psutil
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    du = shutil.disk_usage(storage_root)
    net = psutil.net_io_counters()
    return {
        "ts": time.time(),
        "cpu": psutil.cpu_percent(interval=0.2),
        "load": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
        "ram": {"used": vm.total - vm.available, "total": vm.total, "pct": vm.percent},
        "swap": {"used": sw.used, "total": sw.total, "pct": sw.percent},
        "disk": {"used": du.used, "total": du.total, "pct": round(du.used / du.total * 100, 1) if du.total else 0},
        "net": {"sent": net.bytes_sent, "recv": net.bytes_recv},
        "processes": len(psutil.pids()),
        "uptime_s": int(time.time() - psutil.boot_time()),
    }
