from typing import Dict, Optional


def build_proxy_url(settings: Optional[dict]) -> Optional[str]:
    if not settings:
        return None

    proxy_type = (settings.get("proxy_server_type") or "").strip().lower()
    proxy_addr = (settings.get("proxy_server_addr") or "").strip()
    proxy_port = (settings.get("proxy_server_port") or "").strip()

    if proxy_type in ("", "none"):
        return None

    scheme_map = {
        "https": "https",
        "socks4": "socks4",
        "socks5": "socks5",
    }
    scheme = scheme_map.get(proxy_type)
    if not scheme or not proxy_addr or not proxy_port:
        return None

    return f"{scheme}://{proxy_addr}:{proxy_port}"


def build_requests_proxies(proxy_url: Optional[str]) -> Dict[str, str]:
    if not proxy_url:
        return {}
    return {
        "http": proxy_url,
        "https": proxy_url,
    }
