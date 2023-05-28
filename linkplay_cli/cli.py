import argparse
import asyncio
from http import HTTPStatus
import ipaddress
import re
import sys
from pathlib import Path

from async_upnp_client.search import async_search
import requests


class LinkplayCliCommandFailedException(Exception):
    pass


class LinkplayCliGetRequestFailedException(Exception):
    pass


class LinkplayCliInvalidVolumeArgumentException(Exception):
    pass


class LinkplayCliDeviceNotFoundException(Exception):
    pass


class LinkplayCli:
    OK_MESSAGE = 'OK'
    GET_REQUEST_TIMEOUT_SECONDS = 5
    UPNP_DISCOVER_TIMEOUT_SECONDS = 5
    UPNP_DEVICE_TYPE = 'urn:schemas-upnp-org:device:MediaRenderer:1'
    CACHE_FILE = Path.home() / '.linkplay_cached_device_address'

    def __init__(self, verbose, address=None) -> None:
        self._verbose = verbose
        self._ip_address = address or self._discover_address()

    @staticmethod
    def _is_speaker_ip_address(ip_address):
        if ip_address is None:
            return False

        response = requests.get(f'http://{ip_address}/httpapi.asp?command=setPlayerCmd',
                                timeout=LinkplayCli.GET_REQUEST_TIMEOUT_SECONDS)

        return response.status_code == HTTPStatus.OK

    def _discover_address(self):
        try:
            if LinkplayCli.CACHE_FILE.exists():
                cached_ip_address = ipaddress.IPv4Address(LinkplayCli.CACHE_FILE.read_text())
                if LinkplayCli._is_speaker_ip_address(cached_ip_address):
                    if self._verbose:
                        print(f'Using cached IP address {cached_ip_address}')
                    return cached_ip_address
        except ipaddress.AddressValueError:
            print('Cached IP address is corrupted. Rediscovering.')
        except requests.exceptions.RequestException:
            print('Connection failed. Rediscovering.')

        print('Starting device discovery...')
        linkplay_ip_addresses = []

        async def add_speaker_to_list(upnp_device):
            device_ip_address = upnp_device.get('_host')
            if not LinkplayCli._is_speaker_ip_address(device_ip_address):
                return

            linkplay_ip_addresses.append(device_ip_address)

        # Run synchronously, as our code is not async
        asyncio.new_event_loop().run_until_complete(async_search(
            search_target=LinkplayCli.UPNP_DEVICE_TYPE,
            timeout=LinkplayCli.UPNP_DISCOVER_TIMEOUT_SECONDS,
            async_callback=add_speaker_to_list
        ))

        if len(linkplay_ip_addresses) != 1:
            if self._verbose and linkplay_ip_addresses:
                print(f'Linkplay devices found: {linkplay_ip_addresses}')
            raise LinkplayCliDeviceNotFoundException(f'Found {len(linkplay_ip_addresses)} devices. '
                                                     'Please specify IP address manually.')

        ip_address = linkplay_ip_addresses[0]
        LinkplayCli.CACHE_FILE.write_text(ip_address)
        print(f'Discovered device at IP address {ip_address}. Caching for future use.')

        return ipaddress.IPv4Address(ip_address)

    @staticmethod
    def verify_volume_argument(arg):
        match_result = re.match(r'^[-+]?(\d+)$', arg)
        if match_result is None:
            raise LinkplayCliInvalidVolumeArgumentException(f'Invalid argument "{arg}". See the command\'s help.')

        return arg

    def _run_command(self, command, expect_json=False):
        params = {'command': command}
        response = requests.get(f'http://{self._ip_address}/httpapi.asp',
                                params=params,
                                timeout=LinkplayCli.GET_REQUEST_TIMEOUT_SECONDS)

        verbose_message = f'GET {response.request.url} returned {response.status_code}: {response.text}'

        if response.status_code != HTTPStatus.OK:
            raise LinkplayCliGetRequestFailedException(verbose_message)
        if self._verbose:
            print(verbose_message)

        if expect_json:
            return response.json()
        else:
            return response.text

    @staticmethod
    def _convert_ms_to_duration_string(ms):
        ms = int(ms)

        seconds, _ = divmod(ms, 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)

        if hours > 0:
            return f'{hours}:{minutes:02}:{seconds:02}'
        else:
            return f'{minutes}:{seconds:02}'

    @staticmethod
    def _decode_string(string):
        return bytes.fromhex(string).decode('utf-8')

    def now(self, _):
        UNICODE_LTR_MARK = u'\u200E'
        player_status = self._get_player_status()

        status = player_status['status']
        if int(player_status['curpos']) > int(player_status['totlen']):
            # There's a bug where the current position is some constant garbage value
            current_position_in_ms = '?:??'
        else:
            current_position_in_ms = self._convert_ms_to_duration_string(player_status['curpos'])
        total_length_in_ms = self._convert_ms_to_duration_string(player_status['totlen'])
        title = self._decode_string(player_status['Title'])
        artist = self._decode_string(player_status['Artist'])

        if status == 'play':
            status_string = '▶️'
        elif status == 'pause':
            status_string = '⏸'
        else:
            status_string = '⏹️'

        print(f'{status_string}  {artist} - {title} {UNICODE_LTR_MARK}[{current_position_in_ms}/{total_length_in_ms}]')

    def _run_player_command_expecting_ok_response(self, command):
        response = self._run_command(command)
        if response != LinkplayCli.OK_MESSAGE:
            raise LinkplayCliCommandFailedException(f'Command {command} failed with response {response}.')

    def _get_player_status(self):
        return self._run_command('getPlayerStatus', expect_json=True)

    def pause(self, _):
        self._run_player_command_expecting_ok_response('setPlayerCmd:pause')
        print('Playback paused')

    def play(self, _):
        self._run_player_command_expecting_ok_response('setPlayerCmd:resume')
        print('Playback resumed')

    def next(self, _):
        self._run_player_command_expecting_ok_response('setPlayerCmd:next')
        print('Switched to next track')

    def previous(self, _):
        self._run_player_command_expecting_ok_response('setPlayerCmd:prev')
        print('Switched to previous track')

    def mute(self, _):
        self._run_player_command_expecting_ok_response('setPlayerCmd:mute:1')
        print('Muted')

    def unmute(self, _):
        self._run_player_command_expecting_ok_response('setPlayerCmd:mute:0')
        print('Unmuted')

    def volume(self, volume_args):
        player_status = self._get_player_status()
        orig_volume = int(player_status['vol'])
        muted = player_status['mute'] == '1'

        muted_string = ' (muted)' if muted else ''

        volume_arg = volume_args.new_volume
        if volume_arg is None:
            print(f'Volume: {orig_volume}{muted_string}')
            return

        if volume_arg.startswith('+'):
            new_volume = min(100, orig_volume + int(volume_arg[1:]))
        elif volume_arg.startswith('-'):
            new_volume = max(0, orig_volume - int(volume_arg[1:]))
        else:
            # Negative input is interpreted as "decrease volume"
            new_volume = min(100, int(volume_arg))

        self._run_player_command_expecting_ok_response(f'setPlayerCmd:vol:{new_volume}')
        print(f'Volume: {orig_volume} -> {new_volume}{muted_string}')

    def raw(self, raw_args):
        print(self._run_command(raw_args.command))


def _parse_args():
    main_parser = argparse.ArgumentParser(epilog='For more information about a given command, use "<command> -h"')

    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument('--ip-address', type=ipaddress.IPv4Address, help='The IP address of the device')
    common_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose mode')

    subparsers = main_parser.add_subparsers(
        description='Note that some commands do not work in some scenarios (e.g. when playing from YouTube)',
        help='Command')

    now_parser = subparsers.add_parser('now', parents=[common_parser], help='Show what\'s playing now')
    now_parser.set_defaults(func=LinkplayCli.now)

    pause_parser = subparsers.add_parser('pause', parents=[common_parser], help='Pause current track')
    pause_parser.set_defaults(func=LinkplayCli.pause)

    play_parser = subparsers.add_parser('play', parents=[common_parser], help='Resume current track')
    play_parser.set_defaults(func=LinkplayCli.play)

    next_parser = subparsers.add_parser('next', parents=[common_parser], help='Play next track')
    next_parser.set_defaults(func=LinkplayCli.next)

    previous_parser = subparsers.add_parser('previous', parents=[common_parser], help='Play previous track')
    previous_parser.set_defaults(func=LinkplayCli.previous)

    raw_parser = subparsers.add_parser('volume', parents=[common_parser], help='Set/get current volume')
    raw_parser.set_defaults(func=LinkplayCli.volume)
    raw_parser.add_argument('new_volume', type=LinkplayCli.verify_volume_argument, nargs='?',
                            help='+<num>/-<num> to increase/decrease volume by num; '
                                 '<num> to set volume to num; '
                                 'omit to show volume')

    previous_parser = subparsers.add_parser('mute', parents=[common_parser], help='Mute')
    previous_parser.set_defaults(func=LinkplayCli.mute)

    previous_parser = subparsers.add_parser('unmute', parents=[common_parser], help='Unmute')
    previous_parser.set_defaults(func=LinkplayCli.unmute)

    raw_parser = subparsers.add_parser('raw', parents=[common_parser], help='Execute a raw Linkplay command')
    raw_parser.set_defaults(func=LinkplayCli.raw)
    raw_parser.add_argument('command', help='The LinkPlay API command to execute')

    if len(sys.argv) < 2:
        main_parser.print_help()
        sys.exit(0)

    return main_parser.parse_args()


def main():
    args = _parse_args()

    cli = LinkplayCli(args.verbose, args.ip_address)
    args.func(cli, args)


if __name__ == '__main__':
    main()
