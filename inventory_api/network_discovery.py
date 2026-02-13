import ipaddress
import re
import shutil
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed


DEFAULT_PING_TIMEOUT_MS = 600
DEFAULT_MAX_HOSTS = 1024
SNMP_SERIAL_OIDS = (
    "1.3.6.1.2.1.43.5.1.1.17.1",  # prtGeneralSerialNumber
    "1.3.6.1.2.1.25.3.2.1.3.1",   # hrDeviceDescr
)
SNMP_NAME_OIDS = (
    "1.3.6.1.2.1.1.5.0",          # sysName
    "1.3.6.1.2.1.43.5.1.1.16.1",  # prtGeneralPrinterName
    "1.3.6.1.2.1.25.3.2.1.3.1",   # hrDeviceDescr
)


def _run_command(command, timeout_sec=3):
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        errors="ignore",
    )


def _is_windows():
    return shutil.which("cmd.exe") is not None


def _normalize_mac(value):
    if not value:
        return None
    raw = str(value).strip().upper().replace("-", ":")
    if re.fullmatch(r"([0-9A-F]{2}:){5}[0-9A-F]{2}", raw):
        return raw
    return None


def _parse_latency_ms(output):
    if not output:
        return None
    found = re.search(r"(\d+)\s*ms", output, re.IGNORECASE)
    if found:
        try:
            return int(found.group(1))
        except (TypeError, ValueError):
            return None
    lt1 = re.search(r"time\s*<\s*1", output, re.IGNORECASE)
    if lt1:
        return 1
    return None


def ping_host(ip, timeout_ms=DEFAULT_PING_TIMEOUT_MS):
    if _is_windows():
        command = ["ping", "-n", "1", "-w", str(max(100, int(timeout_ms))), ip]
    else:
        wait_sec = max(1, int(round(timeout_ms / 1000)))
        command = ["ping", "-c", "1", "-W", str(wait_sec), ip]

    try:
        completed = _run_command(command, timeout_sec=max(2, int(timeout_ms / 1000) + 2))
    except Exception:
        return False, None

    raw_output = (completed.stdout or "") + "\n" + (completed.stderr or "")
    text = raw_output.lower()
    reachable = completed.returncode == 0 or "ttl=" in text
    latency_ms = _parse_latency_ms(raw_output)
    return reachable, latency_ms


def _read_arp_map():
    arp_map = {}
    commands = []
    if _is_windows():
        commands = [["arp", "-a"]]
    else:
        commands = [["ip", "neigh"], ["arp", "-an"]]

    for command in commands:
        if not shutil.which(command[0]):
            continue
        try:
            completed = _run_command(command, timeout_sec=4)
        except Exception:
            continue
        output = (completed.stdout or "") + "\n" + (completed.stderr or "")
        for line in output.splitlines():
            match = re.search(r"((?:\d{1,3}\.){3}\d{1,3}).*?(([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2})", line)
            if not match:
                continue
            ip = match.group(1)
            mac = _normalize_mac(match.group(2))
            if mac:
                arp_map[ip] = mac
    return arp_map


def _try_reverse_dns(ip):
    try:
        host, _, _ = socket.gethostbyaddr(ip)
        return host
    except Exception:
        return None


def _sanitize_discovered_name(value):
    if not value:
        return None
    name = str(value).strip().strip('"').strip()
    if not name:
        return None
    if re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", name):
        return None
    return name[:200]


def _try_snmp_value(ip, oids, timeout_sec=2):
    snmpget = shutil.which("snmpget")
    if not snmpget:
        return None, "none"

    for oid in oids:
        command = [snmpget, "-v2c", "-c", "public", "-Oqv", "-t", "0.4", "-r", "0", ip, oid]
        try:
            completed = _run_command(command, timeout_sec=timeout_sec)
        except Exception:
            continue

        if completed.returncode != 0:
            continue
        value = (completed.stdout or "").strip().strip('"')
        lowered = value.lower()
        if (
            not value
            or "no such" in lowered
            or lowered == "null"
            or lowered == "unknown"
        ):
            continue
        return value, "snmp"
    return None, "none"


def _try_snmp_serial(ip):
    value, source = _try_snmp_value(ip, SNMP_SERIAL_OIDS)
    if not value:
        return None, source
    return value[:100], source


def _try_snmp_name(ip):
    value, source = _try_snmp_value(ip, SNMP_NAME_OIDS)
    if not value:
        return None, source
    return _sanitize_discovered_name(value), source


def _try_windows_ping_name(ip):
    if not _is_windows() or not shutil.which("ping"):
        return None
    try:
        completed = _run_command(["ping", "-a", "-n", "1", "-w", "350", ip], timeout_sec=2)
    except Exception:
        return None

    output = (completed.stdout or "") + "\n" + (completed.stderr or "")
    for raw_line in output.splitlines():
        line = raw_line.strip()
        marker = f"[{ip}]"
        if marker not in line:
            continue
        left_part = line.split(marker, 1)[0].strip()
        if not left_part:
            continue
        # Works for both "Pinging NAME [ip]" and localized variants.
        candidate = left_part.split()[-1]
        sanitized = _sanitize_discovered_name(candidate)
        if sanitized and sanitized.lower() != ip.lower():
            return sanitized
    return None


def _try_windows_nbtstat_name(ip):
    if not _is_windows() or not shutil.which("nbtstat"):
        return None
    try:
        completed = _run_command(["nbtstat", "-A", ip], timeout_sec=2)
    except Exception:
        return None

    output = (completed.stdout or "") + "\n" + (completed.stderr or "")
    for line in output.splitlines():
        match = re.search(r"^\s*([^\s<]+)\s*<00>\s+UNIQUE", line, re.IGNORECASE)
        if not match:
            continue
        candidate = _sanitize_discovered_name(match.group(1))
        if candidate and candidate.upper() not in {"WORKGROUP", "MSHOME"}:
            return candidate
    return None


def _iter_ipv4_hosts(network):
    if network.prefixlen >= 31:
        for ip in network:
            yield str(ip)
        return
    for host in network.hosts():
        yield str(host)


def suggest_local_cidrs():
    cidrs = set()

    try:
        import psutil  # Optional dependency

        for addresses in psutil.net_if_addrs().values():
            for item in addresses:
                if item.family != socket.AF_INET:
                    continue
                address = (item.address or "").strip()
                netmask = (item.netmask or "").strip()
                if not address or address.startswith("127."):
                    continue
                try:
                    if netmask:
                        network = ipaddress.ip_network(f"{address}/{netmask}", strict=False)
                    else:
                        network = ipaddress.ip_network(f"{address}/24", strict=False)
                except ValueError:
                    continue
                if not network.is_private:
                    continue
                if network.num_addresses > DEFAULT_MAX_HOSTS:
                    network = ipaddress.ip_network(f"{address}/24", strict=False)
                cidrs.add(str(network))
    except Exception:
        pass

    if not cidrs:
        try:
            _, _, addrs = socket.gethostbyname_ex(socket.gethostname())
        except Exception:
            addrs = []
        for address in addrs:
            if not address or address.startswith("127."):
                continue
            try:
                network = ipaddress.ip_network(f"{address}/24", strict=False)
            except ValueError:
                continue
            if network.is_private:
                cidrs.add(str(network))

    return sorted(cidrs)


def scan_network(cidr, timeout_ms=DEFAULT_PING_TIMEOUT_MS, max_hosts=DEFAULT_MAX_HOSTS):
    network = ipaddress.ip_network(cidr, strict=False)
    if network.version != 4:
        raise ValueError("Only IPv4 ranges are supported.")
    if not network.is_private:
        raise ValueError("Only private network ranges are allowed.")

    host_count = network.num_addresses if network.prefixlen >= 31 else max(network.num_addresses - 2, 0)
    if host_count > max_hosts:
        raise ValueError(f"Range is too large ({host_count} hosts). Max allowed is {max_hosts}.")

    hosts = list(_iter_ipv4_hosts(network))
    alive = []
    workers = min(128, max(8, len(hosts)))

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(ping_host, ip, timeout_ms): ip for ip in hosts}
        for future in as_completed(future_map):
            ip = future_map[future]
            try:
                reachable, latency_ms = future.result()
            except Exception:
                reachable, latency_ms = False, None
            if reachable:
                alive.append({"ip_address": ip, "latency_ms": latency_ms})

    arp_map = _read_arp_map()

    results = []
    for item in alive:
        ip = item["ip_address"]
        hostname = _sanitize_discovered_name(_try_reverse_dns(ip))
        snmp_name, name_source = _try_snmp_name(ip)
        ping_name = _try_windows_ping_name(ip) if not snmp_name and not hostname else None
        nbt_name = _try_windows_nbtstat_name(ip) if not snmp_name and not hostname and not ping_name else None
        serial, serial_source = _try_snmp_serial(ip)
        resolved_name = snmp_name or hostname or ping_name or nbt_name or ip
        resolved_source = (
            "snmp" if snmp_name
            else "dns" if hostname
            else "ping" if ping_name
            else "nbtstat" if nbt_name
            else "ip"
        )
        results.append({
            "name": resolved_name,
            "name_source": resolved_source if resolved_source != "snmp" else name_source,
            "ip_address": ip,
            "mac_address": arp_map.get(ip),
            "serial_number": serial,
            "serial_source": serial_source,
            "latency_ms": item.get("latency_ms"),
        })

    results.sort(key=lambda row: tuple(int(part) for part in row["ip_address"].split(".")))
    return {
        "cidr": str(network),
        "host_count": len(hosts),
        "alive_count": len(results),
        "results": results,
    }
