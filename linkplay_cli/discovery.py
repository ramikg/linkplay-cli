import asyncio
import ipaddress

from async_upnp_client.search import async_search
import requests

from linkplay_cli import config
from linkplay_cli.utils import perform_get_request, LinkplayCliGetRequestFailedException


class LinkplayCliDeviceNotFoundException(Exception):
    pass


UPNP_DEVICE_TYPE = 'urn:schemas-upnp-org:device:MediaRenderer:1'


def _is_linkplay_ip_address(ip_address):
    if ip_address is None:
        return False

    try:
        perform_get_request(f'http://{ip_address}/httpapi.asp?command=setPlayerCmd', verbose=False)
        return True
    except (requests.exceptions.RequestException, LinkplayCliGetRequestFailedException):
        return False


def discover_linkplay_address(verbose):
    try:
        if config.cache_file_path.exists():
            cached_ip_address = ipaddress.IPv4Address(config.cache_file_path.read_text())
            if _is_linkplay_ip_address(cached_ip_address):
                if verbose:
                    print(f'Using cached IP address {cached_ip_address}')
                return cached_ip_address
    except ipaddress.AddressValueError:
        print('Cached IP address is corrupted. Rediscovering.')
    except requests.exceptions.RequestException:
        print('Connection failed. Rediscovering.')

    print('Starting device discovery...')
    linkplay_ip_addresses = []

    async def add_linkplay_device_to_list(upnp_device):
        device_ip_address = upnp_device.get('_host')
        if not _is_linkplay_ip_address(device_ip_address):
            return

        linkplay_ip_addresses.append(device_ip_address)

    # Run synchronously, as our code is not async
    asyncio.new_event_loop().run_until_complete(async_search(
        search_target=UPNP_DEVICE_TYPE,
        timeout=config.upnp_discover_timeout_message,
        async_callback=add_linkplay_device_to_list
    ))

    if len(linkplay_ip_addresses) != 1:
        if verbose and linkplay_ip_addresses:
            print(f'Linkplay devices found: {linkplay_ip_addresses}')
        raise LinkplayCliDeviceNotFoundException(f'Found {len(linkplay_ip_addresses)} devices. '
                                                 'Please specify IP address manually.')

    ip_address = linkplay_ip_addresses[0]
    config.cache_file_path.write_text(ip_address)
    print(f'Discovered device at IP address {ip_address}. Caching for future use.')

    return ipaddress.IPv4Address(ip_address)
