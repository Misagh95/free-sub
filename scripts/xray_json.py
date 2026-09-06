#!/usr/bin/env python3
"""
Convert Xray JSON config exports into standard subscription URIs.

Workers in ``sources.txt`` serve Xray node exports: a JSON array where each
element is a full Xray config object (``outbounds``, ``streamSettings``, ...).
This module extracts the proxy outbound of every node and renders it as a
``vless://`` / ``vmess://`` / ``trojan://`` / ``ss://`` / ``hysteria2://`` /
``tuic://`` URI so the normal subscription pipeline can consume it.
"""

from __future__ import annotations

import base64
import json
import urllib.parse

PROXY_PROTOCOLS = {
    "vless",
    "vmess",
    "trojan",
    "ss",
    "shadowsocks",
    "hysteria2",
    "tuic",
}


def parse_xray_json(text: str) -> list[str]:
    """Return subscription URIs extracted from an Xray JSON export."""
    stripped = text.lstrip()
    if not stripped or stripped[0] not in "[{":
        return []
    try:
        payload = json.loads(text)
    except (ValueError, TypeError):
        return []
    nodes = payload if isinstance(payload, list) else [payload]
    if not nodes or not isinstance(nodes[0], dict):
        return []

    uris: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        name = str(node.get("remarks") or node.get("name") or "Node")
        for outbound in node.get("outbounds") or []:
            if not isinstance(outbound, dict):
                continue
            uri = _outbound_to_uri(outbound, name)
            if uri:
                uris.append(uri)
    return uris


def _set(params: dict[str, str], key: str, value) -> None:
    if value not in (None, ""):
        params[key] = str(value)


def _authority(address: str, port) -> str:
    if ":" in address and not address.startswith("["):
        address = f"[{address}]"
    return f"{address}:{port}"


def _stream_params(stream: dict) -> dict[str, str]:
    """Common streamSettings → URI query parameters."""
    params: dict[str, str] = {}
    security = (stream.get("security") or "none").lower()
    network = stream.get("network") or "tcp"

    tls = stream.get("tlsSettings") or {}
    reality = stream.get("realitySettings") or {}

    sni = (tls.get("serverName") or reality.get("serverName") or "").strip()
    fp = (tls.get("fingerprint") or reality.get("fingerprint") or "").strip()
    alpn = tls.get("alpn") or []
    if isinstance(alpn, str):
        alpn = [alpn]
    alpn_str = ",".join(str(a) for a in alpn if a)
    insecure = bool(tls.get("allowInsecure") or reality.get("allowInsecure"))

    if security == "reality":
        params["security"] = "reality"
        _set(params, "pbk", reality.get("publicKey"))
        _set(params, "sid", reality.get("shortId"))
        _set(params, "spx", reality.get("spiderX"))
    elif security in ("tls", "xtls"):
        params["security"] = "tls"
    else:
        params["security"] = "none"

    params["type"] = network

    if network == "ws":
        ws = stream.get("wsSettings") or {}
        _set(params, "host", ws.get("host"))
        _set(params, "path", ws.get("path"))
    elif network in ("grpc", "gun"):
        grpc = stream.get("grpcSettings") or {}
        _set(params, "serviceName", grpc.get("serviceName"))
        _set(params, "path", grpc.get("serviceName"))
    elif network in ("http", "h2"):
        http = stream.get("httpSettings") or {}
        host = http.get("host") or []
        if isinstance(host, list):
            host = ",".join(str(h) for h in host if h)
        _set(params, "host", host)
        _set(params, "path", http.get("path"))
    elif network == "httpupgrade":
        hu = stream.get("httpupgradeSettings") or {}
        _set(params, "host", hu.get("host"))
        _set(params, "path", hu.get("path"))
    elif network == "xhttp":
        xh = stream.get("xhttpSettings") or {}
        _set(params, "host", xh.get("host"))
        _set(params, "path", xh.get("path"))
        _set(params, "mode", xh.get("mode"))

    _set(params, "sni", sni)
    _set(params, "fp", fp)
    if alpn_str:
        params["alpn"] = alpn_str
    if insecure:
        params["insecure"] = "1"
    return params


def _vless_uri(outbound: dict, name: str) -> str | None:
    settings = outbound.get("settings") or {}
    vnext = settings.get("vnext") or []
    if not vnext:
        return None
    server = vnext[0]
    address = (server.get("address") or "").strip()
    port = server.get("port")
    users = server.get("users") or []
    if not users:
        return None
    uid = (users[0].get("id") or "").strip()
    if not address or not port or not uid:
        return None
    params = _stream_params(outbound.get("streamSettings") or {})
    params["encryption"] = (users[0].get("encryption") or "none").strip() or "none"
    flow = (users[0].get("flow") or "").strip()
    _set(params, "flow", flow)
    query = urllib.parse.urlencode(params)
    return f"vless://{uid}@{_authority(address, port)}?{query}#{urllib.parse.quote(name)}"


def _vmess_uri(outbound: dict, name: str) -> str | None:
    settings = outbound.get("settings") or {}
    vnext = settings.get("vnext") or []
    if not vnext:
        return None
    server = vnext[0]
    address = (server.get("address") or "").strip()
    port = server.get("port")
    users = server.get("users") or []
    if not users:
        return None
    uid = (users[0].get("id") or "").strip()
    if not address or not port or not uid:
        return None
    params = _stream_params(outbound.get("streamSettings") or {})
    payload = {
        "v": "2",
        "ps": name,
        "add": address,
        "port": str(port),
        "id": uid,
        "aid": str(users[0].get("alterId") or 0),
        "scy": (users[0].get("security") or "auto").strip() or "auto",
        "net": params.get("type", "tcp"),
        "type": "none",
        "host": params.get("host", ""),
        "path": params.get("path", ""),
        "tls": "tls" if params.get("security") == "tls" else "",
        "sni": params.get("sni", ""),
        "alpn": params.get("alpn", ""),
        "fp": params.get("fp", ""),
    }
    blob = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return "vmess://" + base64.b64encode(blob).decode("ascii")


def _trojan_uri(outbound: dict, name: str) -> str | None:
    settings = outbound.get("settings") or {}
    servers = settings.get("servers") or []
    if not servers:
        return None
    server = servers[0]
    address = (server.get("address") or "").strip()
    port = server.get("port")
    password = (server.get("password") or "").strip()
    if not address or not port or not password:
        return None
    params = _stream_params(outbound.get("streamSettings") or {})
    params["security"] = "tls"
    query = urllib.parse.urlencode(params)
    return f"trojan://{password}@{_authority(address, port)}?{query}#{urllib.parse.quote(name)}"


def _ss_uri(outbound: dict, name: str) -> str | None:
    settings = outbound.get("settings") or {}
    servers = settings.get("servers") or []
    if not servers:
        return None
    server = servers[0]
    address = (server.get("address") or "").strip()
    port = server.get("port")
    method = (server.get("method") or "").strip()
    password = (server.get("password") or "").strip()
    if not address or not port or not method or not password:
        return None
    userinfo = (
        base64.urlsafe_b64encode(f"{method}:{password}".encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )
    params: dict[str, str] = {}
    plugin = (server.get("plugin") or "").strip()
    _set(params, "plugin", plugin)
    query = ("?" + urllib.parse.urlencode(params)) if params else ""
    return f"ss://{userinfo}@{_authority(address, port)}{query}#{urllib.parse.quote(name)}"


def _hysteria2_uri(outbound: dict, name: str) -> str | None:
    settings = outbound.get("settings") or {}
    servers = settings.get("servers") or []
    if not servers:
        return None
    server = servers[0]
    address = (server.get("address") or "").strip()
    port = server.get("port")
    password = (server.get("password") or "").strip()
    if not address or not port or not password:
        return None
    stream = outbound.get("streamSettings") or {}
    tls = stream.get("tlsSettings") or {}
    params: dict[str, str] = {}
    _set(params, "sni", tls.get("serverName"))
    if tls.get("allowInsecure"):
        params["insecure"] = "1"
    obfs = (server.get("obfs") or "").strip()
    _set(params, "obfs", obfs)
    _set(params, "obfs-password", server.get("obfsPassword") or server.get("obfs-password"))
    query = urllib.parse.urlencode(params)
    return f"hysteria2://{password}@{_authority(address, port)}?{query}#{urllib.parse.quote(name)}"


def _tuic_uri(outbound: dict, name: str) -> str | None:
    settings = outbound.get("settings") or {}
    auth = settings.get("auth") or {}
    uuid = (auth.get("uuid") or "").strip()
    address = (settings.get("address") or "").strip()
    port = settings.get("port")
    if not address or not port or not uuid:
        return None
    stream = outbound.get("streamSettings") or {}
    tls = stream.get("tlsSettings") or {}
    params: dict[str, str] = {}
    _set(params, "sni", tls.get("serverName"))
    _set(params, "congestion_control", settings.get("congestionControl"))
    _set(params, "udp_relay_mode", settings.get("udpRelayMode"))
    if tls.get("allowInsecure"):
        params["allow_insecure"] = "1"
    password = (settings.get("password") or "").strip()
    userinfo = uuid if not password else f"{uuid}:{password}"
    query = urllib.parse.urlencode(params)
    return f"tuic://{userinfo}@{_authority(address, port)}?{query}#{urllib.parse.quote(name)}"


_BUILDERS = {
    "vless": _vless_uri,
    "vmess": _vmess_uri,
    "trojan": _trojan_uri,
    "ss": _ss_uri,
    "hysteria2": _hysteria2_uri,
    "tuic": _tuic_uri,
}


def _outbound_to_uri(outbound: dict, name: str) -> str | None:
    protocol = (outbound.get("protocol") or "").lower()
    if protocol == "shadowsocks":
        protocol = "ss"
    builder = _BUILDERS.get(protocol)
    if builder is None:
        return None
    try:
        return builder(outbound, name)
    except Exception:
        return None