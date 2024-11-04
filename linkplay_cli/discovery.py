import asyncio
from ipaddress import IPv4Address
from typing import List

from async_upnp_client.search import async_search

from linkplay_cli import config
from linkplay_cli.device import Device, RequestProtocol
from linkplay_cli.utils import perform_get_request, LinkplayCliGetRequestFailedException


class LinkplayCliDeviceNotFoundException(Exception):
    pass


UPNP_DEVICE_TYPE = 'urn:schemas-upnp-org:device:MediaRenderer:1'


def _get_linkplay_device_status(ip_address: IPv4Address, port: int, protocol: RequestProtocol):
    return perform_get_request(
        f'{protocol}://{ip_address}:{port}/httpapi.asp?command=getStatusEx',
        expect_json=True,
        verbose=False)


def _get_valid_linkplay_device_configuration_from_ip_address(ip_address: IPv4Address) -> Device | None:
    for http_port in config.http_ports:
        try:
            status = _get_linkplay_device_status(ip_address, http_port, 'http')
            return Device(ip_address=ip_address, port=http_port, protocol='http',
                          model=status['project'], name=status['DeviceName'],
                          tcp_uart_port=int(status.get('uart_pass_port', config.default_tcp_uart_port)))
        except LinkplayCliGetRequestFailedException:
            pass

    for tls_port in config.tls_ports:
        try:
            status = _get_linkplay_device_status(ip_address, tls_port, 'https')
            return Device(ip_address=ip_address, port=tls_port, protocol='https',
                          model=status['project'], name=status['DeviceName'],
                          tcp_uart_port=int(status.get('uart_pass_port', config.default_tcp_uart_port)))
        except LinkplayCliGetRequestFailedException:
            pass

    return None


def is_valid_linkplay_device(device: Device) -> bool:
    try:
        _get_linkplay_device_status(device.ip_address, device.port, device.protocol)
        return True
    except LinkplayCliGetRequestFailedException:
        return False


def discover_linkplay_devices() -> List[Device]:
    print('Starting device discovery...')
    linkplay_devices: List[Device] = []

    async def add_linkplay_device_to_list(upnp_device):
        device_ip_address = upnp_device.get('_host')
        potential_linkplay_device = _get_valid_linkplay_device_configuration_from_ip_address(device_ip_address)
        if not potential_linkplay_device:
            return

        linkplay_devices.append(potential_linkplay_device)

    # Run synchronously, as our code is not async
    asyncio.new_event_loop().run_until_complete(async_search(
        search_target=UPNP_DEVICE_TYPE,
        timeout=config.upnp_discover_timeout_message,
        async_callback=add_linkplay_device_to_list
    ))

    if not linkplay_devices:
        raise LinkplayCliDeviceNotFoundException('Linkplay devices not found.')

    return linkplay_devices
