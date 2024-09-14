import argparse
import calendar
from enum import Enum
import html
import math
import re
import sys
import tempfile
import time

from linkplay_cli.configure import prompt_user_to_choose_active_device, \
    load_configuration_from_file
from pathlib import Path

from bs4 import BeautifulSoup
from Crypto.Cipher import ARC4
from prettytable import PrettyTable

from linkplay_cli import config
from linkplay_cli.discovery import discover_linkplay_devices, is_valid_linkplay_device
from linkplay_cli.firmware_update import print_latest_version_and_release_date
from linkplay_cli.utils import perform_get_request, LinkplayCliGetRequestUnknownCommandException


class LinkplayCliCommandFailedException(Exception):
    pass


class LinkplayCliInvalidArgumentException(Exception):
    pass


class AlarmOperation(Enum):
    command = 0
    play = 1
    stop = 2


class AlarmTrigger(Enum):
    once = 1
    daily = 2
    weekly = 3
    monthly = 5


PLAYBACK_MODE_NUMBER_TO_NAME = {
    1: "Apple Music",
    10: "URL",
    31: "Spotify",
    40: "AUX",
    41: "Bluetooth",
}


class LinkplayCli:
    # Rotate calendar.day_name so that it will start with Sunday
    DAY_NAMES = list(calendar.day_name)[-1:] + list(calendar.day_name)[:-1]

    def __init__(self, verbose) -> None:
        self._verbose = verbose
        configuration = load_configuration_from_file()
        if configuration.active_device and is_valid_linkplay_device(configuration.active_device):
            self._device = configuration.active_device
        else:
            linkplay_devices = discover_linkplay_devices()
            self._device = prompt_user_to_choose_active_device(linkplay_devices)

    @staticmethod
    def verify_volume_argument(arg):
        match_result = re.match(r'^[-+]?(\d+)$', arg)
        if match_result is None:
            raise LinkplayCliInvalidArgumentException(f'Invalid argument "{arg}". See the command\'s help.')

        return arg

    @staticmethod
    def verify_date_argument(arg, fmt):
        try:
            time.strptime(arg, fmt)
        except ValueError:
            raise LinkplayCliInvalidArgumentException(f'Invalid argument "{arg}" for format "{fmt}".')

        return arg

    def _run_command(self, command, expect_json=False):
        return perform_get_request(f'{self._device.protocol}://{self._device.ip_address}:{self._device.port}/httpapi.asp',
                                   verbose=self._verbose,
                                   params={'command': command},
                                   expect_json=expect_json)

    @staticmethod
    def _convert_seconds_to_duration_string(seconds):
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)

        if hours > 0:
            return f'{hours}:{minutes:02}:{seconds:02}'
        else:
            return f'{minutes}:{seconds:02}'

    def _convert_ms_to_duration_string(self, ms):
        ms = int(ms)

        seconds, _ = divmod(ms, 1000)
        return self._convert_seconds_to_duration_string(seconds)

    @staticmethod
    def _decode_string(s, unescape_html=False):
        try:
            result = bytes.fromhex(s).decode('utf-8')
            return html.unescape(result) if unescape_html else result
        except ValueError:
            return s

    @staticmethod
    def _encode_string(s):
        return bytes(s, 'utf-8').hex()

    def now(self, args):
        UNICODE_LTR_MARK = u'\u200E'
        UNKNOWN_NAME_STRING = 'Unknown'

        player_status = self._get_player_status()

        status = player_status['status']
        artist = self._decode_string(player_status['Artist'], unescape_html=True) or UNKNOWN_NAME_STRING
        title = self._decode_string(player_status['Title'], unescape_html=True) or UNKNOWN_NAME_STRING

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

        if args.extra:
            album = self._decode_string(player_status['Album'], unescape_html=True)
            if album:
                output_string += f'\nAlbum: {album}'
            playback_mode = int(player_status['mode'])
            if playback_mode in PLAYBACK_MODE_NUMBER_TO_NAME:
                output_string += f'\nPlayback mode: {PLAYBACK_MODE_NUMBER_TO_NAME[playback_mode]}'

        print(output_string)

    def _run_command_expecting_ok_output(self, command):
        OK_MESSAGE = 'OK'

        output = self._run_command(command)
        if output != OK_MESSAGE:
            raise LinkplayCliCommandFailedException(f'Command {command} failed with output {output}.')

    def _get_player_status(self):
        return self._run_command('getPlayerStatusEx', expect_json=True)

    def pause(self, _):
        self._run_command_expecting_ok_output('setPlayerCmd:pause')
        print('Playback paused')

    def play(self, args):
        if args.url:
            self._run_command_expecting_ok_output(f'setPlayerCmd:play:{args.url}')
            print(f'Playing from {args.url}')
        else:
            self._run_command_expecting_ok_output('setPlayerCmd:resume')
            print('Playback resumed')

    def next(self, _):
        self._run_command_expecting_ok_output('setPlayerCmd:next')
        print('Switched to next track')

    def previous(self, _):
        self._run_command_expecting_ok_output('setPlayerCmd:prev')
        print('Switched to previous track')

    def seek(self, seek_args):
        new_position = seek_args.new_position
        time_parts = new_position.split(':')
        if len(time_parts) > 3:
            raise LinkplayCliInvalidArgumentException(f'Invalid argument "{new_position}". See the command\'s help.')
        if any([int(time_part) < 0 for time_part in time_parts]):
            raise LinkplayCliInvalidArgumentException(f'Invalid argument "{new_position}". Use positive integers only.')

        seconds_to_seek = 0
        multiplier = 1
        for time_part in reversed(time_parts):
            seconds_to_seek += int(time_part) * multiplier
            multiplier *= 60

        self._run_command_expecting_ok_output(f'setPlayerCmd:seek:{seconds_to_seek}')
        print(f'Position changed to {self._convert_seconds_to_duration_string(seconds_to_seek)}')

    def mute(self, _):
        self._run_command_expecting_ok_output('setPlayerCmd:mute:1')
        print('Muted')

    def unmute(self, _):
        self._run_command_expecting_ok_output('setPlayerCmd:mute:0')
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

        self._run_command_expecting_ok_output(f'setPlayerCmd:vol:{new_volume}')
        print(f'Volume: {orig_volume} -> {new_volume}{muted_string}')

    def raw(self, raw_args):
        print(self._run_command(raw_args.command))

    @staticmethod
    def _print_info_if_not_empty(info_name, value):
        if value not in ['', '0']:
            print(f'{info_name}: {value}')

    def _print_latest_version_and_release_date(self, model, hardware):
        update_server = self._run_command('GetUpdateServer')

        print_latest_version_and_release_date(update_server, model, hardware, self._verbose)

    @staticmethod
    def _parse_timezone(timezone_string):
        timezone = float(timezone_string)
        fractional_part, integer_part = math.modf(abs(timezone))
        fractional_string = f':{int(60 * fractional_part):02}' if fractional_part else ''
        integer_string = f'{int(integer_part):02}'
        sign_string = '+' if timezone >= 0 else '-'
        return f'{sign_string}{integer_string}{fractional_string}'

    def _status_to_time_string(self, status):
        timezone_string = self._parse_timezone(status['tz']) if 'tz' in status else ''
        return f'{status["date"]} {status["time"]}{timezone_string}'

    def _print_access_points(self):
        status = self._run_command('getStatusEx', expect_json=True)
        connected_ssid = self._decode_string(status['essid'])

        ap_list = self._run_command('wlanGetApListEx', expect_json=True)['aplist']

        table = PrettyTable()
        table.field_names = ['SSID', 'BSSID', 'RSSI', 'channel', 'Authentication', 'Encryption', 'Address if connected']
        for ap in ap_list:
            ssid = self._decode_string(ap['ssid'])
            bssid = ap['bssid'].upper()
            ip_address = status['apcli0'] if connected_ssid == ssid else ''
            table.add_row([ssid, bssid, ap['rssi'], ap['channel'], ap['auth'], ap['encry'], ip_address])

        print(table)

    def info(self, args):
        if args.wi_fi:
            self._print_access_points()
            return

        status = self._run_command('getStatusEx', expect_json=True)

        new_device_string = ''
        if args.set_device_name:
            self._run_command_expecting_ok_output(f'setHexDeviceName:{self._encode_string(args.set_device_name)}')
            new_device_string = f' -> {args.set_device_name}'

        model = status['project']
        hardware = status['hardware']

        print(f'Device name: {status['DeviceName']}{new_device_string}')
        print(f'Model: {model}')
        print(f'Device time: {self._status_to_time_string(status)}')
        self._print_info_if_not_empty('Wi-Fi IP address', status['apcli0'])
        self._print_info_if_not_empty('Wi-Fi SSID', self._decode_string(status['essid']))
        self._print_info_if_not_empty('Ethernet IP address', status['eth2'])
        print(f'UUID: {status["uuid"]}')
        print(f'Hardware: {hardware}')
        self._print_info_if_not_empty('MCU version', status['mcu_ver'])
        self._print_info_if_not_empty('DSP version', status['dsp_ver'])
        print(f'Firmware version: {status["firmware"]} (released {status["Release"]})')

        try:
            self._print_latest_version_and_release_date(model, hardware)
        except LinkplayCliGetRequestUnknownCommandException:
            pass

    def alarm_list(self, _):
        table = PrettyTable()
        table.field_names = ['Index', 'Operation', 'Trigger', 'Date', 'Time', 'Day', 'Path']
        for alarm_index in range(config.maximum_number_of_alarms):
            alarm = self._run_command(f'getAlarmClock:{alarm_index}', expect_json=True)

            day = alarm.get('day', '')
            if 'week_day' in alarm:
                day = LinkplayCli.DAY_NAMES[int(alarm['week_day'])]

            if alarm['enable'] == '1':
                table.add_row([alarm_index,
                               alarm['operation'],
                               alarm['trigger'],
                               alarm.get('date', ''),
                               alarm['time'],
                               day,
                               alarm['path']])

        if table.rows:
            print(table)
        else:
            print('No alarms')

    def alarm_stop(self, _):
        self._run_command_expecting_ok_output('alarmStop')
        print('Alarm stopped')

    def alarm_delete(self, args):
        self._run_command_expecting_ok_output(f'alarmDel:{args.index}')
        print(f'Alarm {args.index} deleted')

    def _verify_alarm_set_arguments(self, args):
        self.verify_date_argument(args.time, '%H%M%S')

        if args.once:
            self.verify_date_argument(args.year, '%Y')
            if not 2015 <= int(args.year) <= 2020:
                print('Note: Some devices prohibit one-time alarms not between 2015 and 2020 (inclusive).')
            self.verify_date_argument(args.month, '%m')
            self.verify_date_argument(args.day, '%d')
        elif args.weekly:
            self.verify_date_argument(args.day, '%A')
        elif args.monthly:
            self.verify_date_argument(args.day, '%d')

    def alarm_set(self, args):
        self._verify_alarm_set_arguments(args)

        optional_params = ''

        if args.once:
            optional_params += f':{args.year}{int(args.month):02}{int(args.day):02}'
        elif args.weekly:
            optional_params += f':0{LinkplayCli.DAY_NAMES.index(args.day.title())}'
        elif args.monthly:
            optional_params += f':{int(args.day):02}'

        if args.command:
            optional_params += f':{args.command}'
            operation = AlarmOperation['command'].value
        elif args.play:
            optional_params += f':{args.play}'
            operation = AlarmOperation['play'].value
        elif args.stop:
            operation = AlarmOperation['stop'].value

        if args.once:
            trigger = AlarmTrigger['once'].value
        elif args.daily:
            trigger = AlarmTrigger['daily'].value
        elif args.weekly:
            trigger = AlarmTrigger['weekly'].value
        elif args.monthly:
            trigger = AlarmTrigger['monthly'].value

        self._run_command_expecting_ok_output(
            f'setAlarmClock:{args.index}:{trigger}:{operation}:{args.time}{optional_params}')

        print('Alarm set.')

    def date(self, args):
        status = self._run_command('getStatusEx', expect_json=True)
        original_time_string = self._status_to_time_string(status)

        new_time_string = ''
        if args.set:
            self._run_command_expecting_ok_output(f'timeSync:{args.set}')
            status = self._run_command('getStatusEx', expect_json=True)
            new_time_string = f' -> {self._status_to_time_string(status)}'

        print(original_time_string + new_time_string)

    def getsyslog(self, args):
        download_page = self._run_command('getsyslog')  # The download URL is always the same, but needs to be refreshed
        download_url = f'http://{self._ip_address}/' + BeautifulSoup(download_page, 'lxml').find('a')['href']
        encrypted_log = perform_get_request(download_url, verbose=False, expect_bytes=True)

        output_file_dir = Path(args.output_dir or tempfile.gettempdir())
        output_file_dir.mkdir(parents=True, exist_ok=True)
        output_file_path = output_file_dir / ('sys.log-' + time.strftime('%Y%m%d%H%M%S'))

        with open(output_file_path, 'wb') as output_file:
            for chunk_start in range(0, len(encrypted_log), config.log_chunk_size):
                chunk = encrypted_log[chunk_start:chunk_start + config.log_chunk_size]
                cipher = ARC4.new(config.log_key)
                output_file.write(cipher.decrypt(chunk))

        print(f'Log file downloaded to {output_file_path}')


def _add_alarm_arg_subparsers(top_subparsers, common_parser):
    parent_subparser = top_subparsers.add_parser('alarm', parents=[common_parser], help='Control alarm clocks')
    parent_subparser.set_defaults(func=lambda *args: parent_subparser.print_help())
    alarm_subparsers = parent_subparser.add_subparsers(title='Alarm subcommands')

    subparser = alarm_subparsers.add_parser('list', parents=[common_parser], help='List existing alarms')
    subparser.set_defaults(func=LinkplayCli.alarm_list)

    subparser = alarm_subparsers.add_parser('set', parents=[common_parser],
                                            help='Set alarm (optionally overwriting an existing one)')
    subparser.set_defaults(func=LinkplayCli.alarm_set)
    subparser.add_argument('--index', required=True, type=int,
                           choices=range(config.maximum_number_of_alarms),
                           help='The alarm index')

    triggers = subparser.add_mutually_exclusive_group(required=True)
    triggers.add_argument('--once', action='store_true',
                          help='Set up a one-time alarm')
    triggers.add_argument('--daily', action='store_true',
                          help='Set up a daily alarm')
    triggers.add_argument('--weekly', action='store_true',
                          help='Set up a weekly alarm')
    triggers.add_argument('--monthly', action='store_true',
                          help='Set up a monthly alarm')

    operations = subparser.add_mutually_exclusive_group(required=True)
    operations.add_argument('--command',
                            help='Execute a command when the alarm is triggered')
    operations.add_argument('--play', metavar='URL',
                            help='Play a URL when the alarm is triggered')
    operations.add_argument('--stop', action='store_true',
                            help='Stop what\'s playing when the alarm is triggered')

    subparser.add_argument('--time', metavar='HHMMSS', required=True,
                           help='Alarm time')
    subparser.add_argument('--year', metavar='YYYY',
                           help='Alarm year (where relevant)')
    subparser.add_argument('--month', metavar='MM',
                           help='Alarm month (where relevant)')
    subparser.add_argument('--day',
                           help='Alarm day. Format: '
                           'Day name (for weekly alarms. E.g. "monday") or number (for other alarms. E.g. "13")')

    subparser = alarm_subparsers.add_parser('stop', parents=[common_parser], help='Stop the alarm')
    subparser.set_defaults(func=LinkplayCli.alarm_stop)

    subparser = alarm_subparsers.add_parser('delete', parents=[common_parser], help='Delete alarm')
    subparser.set_defaults(func=LinkplayCli.alarm_delete)
    subparser.add_argument('--index', help='The index of the alarm to delete')


def _parse_args():
    main_parser = argparse.ArgumentParser(epilog='For more information about a given command, use "<command> -h"')

    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose mode')

    subparsers = main_parser.add_subparsers(
        description='Note that some commands do not work in some scenarios (e.g. when playing from YouTube)'
    )

    subparser = subparsers.add_parser('now', parents=[common_parser], help='Show what\'s playing now')
    subparser.set_defaults(func=LinkplayCli.now)
    subparser.add_argument('--no-time', action='store_true', help='Don\'t display the current position and length')
    subparser.add_argument('--extra', action='store_true', help='Display additional information')

    subparser = subparsers.add_parser('pause', parents=[common_parser], help='Pause current track')
    subparser.set_defaults(func=LinkplayCli.pause)

    subparser = subparsers.add_parser('play', parents=[common_parser], help='Resume current track or play from URL')
    subparser.set_defaults(func=LinkplayCli.play)
    subparser.add_argument('--url', help='URL to play from')

    subparser = subparsers.add_parser('next', parents=[common_parser], help='Play next track')
    subparser.set_defaults(func=LinkplayCli.next)

    subparser = subparsers.add_parser('previous', parents=[common_parser], help='Play previous track')
    subparser.set_defaults(func=LinkplayCli.previous)

    subparser = subparsers.add_parser('seek', parents=[common_parser], help='Seek to a specific track position')
    subparser.set_defaults(func=LinkplayCli.seek)
    subparser.add_argument('new_position',
                           help='Acceptable formats: '
                                '"<hours>:<minutes>:<seconds>" or "<minutes>:<seconds>" or "<seconds>".\n'
                                'E.g.: "4:21" or (equivalently) "261"')

    subparser = subparsers.add_parser('volume', parents=[common_parser], help='Set/get current volume')
    subparser.set_defaults(func=LinkplayCli.volume)
    subparser.add_argument('new_volume', type=LinkplayCli.verify_volume_argument, nargs='?',
                           help='+<num>/-<num> to increase/decrease volume by num; '
                                '<num> to set volume to num; '
                                'omit to show volume')

    subparser = subparsers.add_parser('mute', parents=[common_parser], help='Mute')
    subparser.set_defaults(func=LinkplayCli.mute)

    subparser = subparsers.add_parser('unmute', parents=[common_parser], help='Unmute')
    subparser.set_defaults(func=LinkplayCli.unmute)

    subparser = subparsers.add_parser('info', parents=[common_parser], help='Get basic device information')
    subparser.set_defaults(func=LinkplayCli.info)
    subparser.add_argument('--wi-fi', action='store_true', help='List available Wi-Fi access points')
    subparser.add_argument('--set-device-name', help='Set device name')

    subparser = subparsers.add_parser('date', parents=[common_parser], help='Print and set device date and time')
    subparser.set_defaults(func=LinkplayCli.date)
    subparser.add_argument('--set', metavar='YYYYMMDDHHMMSS',
                           type=lambda d: LinkplayCli.verify_date_argument(d, '%Y%m%d%H%M%S'),
                           help='Set the date and time')

    subparser = subparsers.add_parser('getsyslog', parents=[common_parser], help='Download device log file')
    subparser.set_defaults(func=LinkplayCli.getsyslog)
    subparser.add_argument('--output-dir', help='Output directory. Defaults to gettempdir()')

    _add_alarm_arg_subparsers(subparsers, common_parser)

    subparser = subparsers.add_parser('raw', parents=[common_parser], help='Execute a raw Linkplay command')
    subparser.set_defaults(func=LinkplayCli.raw)
    subparser.add_argument('command', help='The Linkplay API command to execute')

    subparser = subparsers.add_parser('rediscover', parents=[common_parser],
                                      help='Rediscover Linkplay devices and choose an active device')
    subparser.add_subparsers(dest='rediscover')

    if len(sys.argv) < 2:
        main_parser.print_help()
        sys.exit(0)

    return main_parser.parse_args()


def main():
    args = _parse_args()

    if hasattr(args, 'rediscover'):
        linkplay_devices = discover_linkplay_devices()
        prompt_user_to_choose_active_device(linkplay_devices)
    else:
        cli = LinkplayCli(args.verbose)
        args.func(cli, args)


if __name__ == '__main__':
    main()
