import argparse
import ipaddress
import re
import sys
import time
from pathlib import Path

from Crypto.Cipher import ARC4

from linkplay_cli import config
from linkplay_cli.discovery import discover_linkplay_address
from linkplay_cli.firmware_update import print_latest_version_and_release_date
from linkplay_cli.utils import perform_get_request


class LinkplayCliCommandFailedException(Exception):
    pass


class LinkplayCliInvalidVolumeArgumentException(Exception):
    pass


class LinkplayCli:
    def __init__(self, verbose, address=None) -> None:
        self._verbose = verbose
        self._ip_address = address or discover_linkplay_address(verbose)

    @staticmethod
    def verify_volume_argument(arg):
        match_result = re.match(r'^[-+]?(\d+)$', arg)
        if match_result is None:
            raise LinkplayCliInvalidVolumeArgumentException(f'Invalid argument "{arg}". See the command\'s help.')

        return arg

    def _run_command(self, command, expect_json=False):
        return perform_get_request(f'http://{self._ip_address}/httpapi.asp',
                                   verbose=self._verbose,
                                   params={'command': command},
                                   expect_json=expect_json)

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

    def now(self, args):
        UNICODE_LTR_MARK = u'\u200E'
        player_status = self._get_player_status()

        status = player_status['status']
        title = self._decode_string(player_status['Title'])
        artist = self._decode_string(player_status['Artist'])

        if status == 'play':
            status_string = '▶️'
        elif status == 'pause':
            status_string = '⏸'
        else:
            status_string = '⏹️'

        output_string = f'{status_string}  {artist} - {title}'
        if not args.no_time:
            if int(player_status['curpos']) > int(player_status['totlen']):
                # There's a bug where the current position is some constant garbage value
                current_position_in_ms = '?:??'
            else:
                current_position_in_ms = self._convert_ms_to_duration_string(player_status['curpos'])
            total_length_in_ms = self._convert_ms_to_duration_string(player_status['totlen'])

            output_string += f' {UNICODE_LTR_MARK}[{current_position_in_ms}/{total_length_in_ms}]'

        print(output_string)

    def _run_player_command_expecting_ok_output(self, command):
        OK_MESSAGE = 'OK'

        output = self._run_command(command)
        if output != OK_MESSAGE:
            raise LinkplayCliCommandFailedException(f'Command {command} failed with output {output}.')

    def _get_player_status(self):
        return self._run_command('getPlayerStatus', expect_json=True)

    def pause(self, _):
        self._run_player_command_expecting_ok_output('setPlayerCmd:pause')
        print('Playback paused')

    def play(self, _):
        self._run_player_command_expecting_ok_output('setPlayerCmd:resume')
        print('Playback resumed')

    def next(self, _):
        self._run_player_command_expecting_ok_output('setPlayerCmd:next')
        print('Switched to next track')

    def previous(self, _):
        self._run_player_command_expecting_ok_output('setPlayerCmd:prev')
        print('Switched to previous track')

    def mute(self, _):
        self._run_player_command_expecting_ok_output('setPlayerCmd:mute:1')
        print('Muted')

    def unmute(self, _):
        self._run_player_command_expecting_ok_output('setPlayerCmd:mute:0')
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

        self._run_player_command_expecting_ok_output(f'setPlayerCmd:vol:{new_volume}')
        print(f'Volume: {orig_volume} -> {new_volume}{muted_string}')

    def raw(self, raw_args):
        print(self._run_command(raw_args.command))

    @staticmethod
    def _print_info_if_not_empty(info_name, value):
        if value:
            print(f'{info_name}: {value}')

    def _print_latest_version_and_release_date(self, model, hardware):
        update_server = self._run_command('GetUpdateServer')

        print_latest_version_and_release_date(update_server, model, hardware, self._verbose)

    def info(self, _):
        status = self._run_command('getStatus', expect_json=True)

        model = status["project"]
        hardware = status["hardware"]

        print(f'Device name: {status["DeviceName"]}')
        print(f'Model: {model}')
        self._print_info_if_not_empty('Wireless IP address', status["apcli0"])
        self._print_info_if_not_empty('Ethernet IP address', status["eth2"])
        print(f'UUID: {status["uuid"]}')
        print(f'Hardware: {hardware}')
        self._print_info_if_not_empty('MCU version', status["mcu_ver"])
        self._print_info_if_not_empty('DSP version', status["dsp_ver"])
        self._print_info_if_not_empty('DSP version', status["dsp_ver"])
        print(f'Firmware version: {status["firmware"]} (released {status["Release"]})')

        self._print_latest_version_and_release_date(model, hardware)

    def getsyslog(self, args):
        encrypted_log = perform_get_request(f'http://{self._ip_address}/data/sys.log', verbose=self._verbose)

        output_file_path = args.output_file or Path.cwd() / ('sys.log-' + time.strftime('%Y%m%d%H%M%S'))

        with open(output_file_path, 'wb') as output_file:
            for chunk_start in range(0, len(encrypted_log), config.log_chunk_size):
                chunk = encrypted_log[chunk_start:chunk_start + config.log_chunk_size]
                cipher = ARC4.new(config.log_key)
                output_file.write(cipher.decrypt(chunk))


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
    now_parser.add_argument('--no-time', action='store_true', help='Don\'t display the current position and length')

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

    info_parser = subparsers.add_parser('info', parents=[common_parser], help='Get basic device information')
    info_parser.set_defaults(func=LinkplayCli.info)

    getsyslog_parser = subparsers.add_parser('getsyslog', parents=[common_parser], help='Download device log file')
    getsyslog_parser.set_defaults(func=LinkplayCli.getsyslog)
    getsyslog_parser.add_argument('--output-file', help='Output path. Defaults to "sys.log-<timestamp>"')

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
