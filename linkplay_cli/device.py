import ipaddress
from dataclasses import dataclass
from typing import Literal, TypeAlias

RequestProtocol: TypeAlias = Literal["http", "https"]

@dataclass
class Device:
    ip_address: ipaddress.IPv4Address
    port: int
    protocol: RequestProtocol
    model: str
    name: str
    tcp_uart_port: int
