"""Helpers for choosing which address a config entry stores for a BTClock.

The integration stores the device's IPv4 address rather than its
`btclock-xxxx.local` name: resolving `.local` needs a working mDNS round
trip on every connect, which fails or stalls on networks where multicast
is unreliable (the device then looks offline although it answers on its
IP). Zeroconf rediscovery keeps the stored IP current when DHCP hands out
a new one. A DNS name the user typed in deliberately is left alone.
"""

from __future__ import annotations

from ipaddress import IPv4Address, ip_address


def usable_ipv4(value: object) -> str | None:
    """Return `value` as an IPv4 string if a client can reach the device on it.

    Rejects IPv6 (BTClock firmware has it compiled out), and loopback,
    link-local, multicast and unspecified addresses.
    """
    try:
        addr = ip_address(str(value))
    except ValueError:
        return None
    if not isinstance(addr, IPv4Address):
        return None
    if (
        addr.is_unspecified
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
    ):
        return None
    return str(addr)


def is_mdns_host(host: str | None) -> bool:
    """Return True for a multicast-DNS name such as `btclock-9d5530.local`."""
    return bool(host) and host.rstrip(".").lower().endswith(".local")


def is_auto_managed_host(host: str | None) -> bool:
    """Return True when a freshly discovered IP may replace the stored host.

    That is an IP address or a `.local` name; a regular DNS name the user
    chose (e.g. `btclock.example.lan`) is kept as-is.
    """
    return is_mdns_host(host) or usable_ipv4(host) is not None
