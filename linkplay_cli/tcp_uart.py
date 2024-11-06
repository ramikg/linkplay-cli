import re
import socket
from ipaddress import IPv4Address

from construct import Bytes, Checksum, Const, Int32ul, len_, Padding, Tell, this, Rebuild, Struct, Pointer

from linkplay_cli.utils import LinkplayCliGetRequestUnknownCommandException

TCP_UART_MAGIC = bytes.fromhex('18961820')
NUMBER_OF_RESPONSE_BYTES_TO_READ = 4096
TCP_UART_UNKNOWN_COMMAND_RESPONSE = b'AXX+UNKNOWN'

TCP_UART_MESSAGE_STRUCT = Struct(
    'magic' / Const(TCP_UART_MAGIC, Bytes(4)),
    'length' / Rebuild(Int32ul, len_(this.payload)),
    'offset_of_checksum' / Tell,
    'checksum' / Padding(4), # Placeholder
    'reserved' / Padding(8),
    'payload' / Bytes(this.length),
    'checksum' / Pointer(this.offset_of_checksum, Checksum(Int32ul, sum, this.payload)),
)


class TcpUart:
    def __init__(self, ip_address: IPv4Address, port: int, verbose: bool):
        self._ip_address = ip_address
        self._port = port
        self._verbose = verbose
        self._socket = socket.create_connection((str(self._ip_address), self._port))

    def __del__(self):
        if self._socket:
            self._socket.shutdown(socket.SHUT_RDWR)
            self._socket.close()

    def run_command(self, command):
        if self._verbose:
            print(command)

        self._socket.sendall(TCP_UART_MESSAGE_STRUCT.build(dict(payload=bytes(command, 'utf-8'))))
        response_bytes = self._socket.recv(NUMBER_OF_RESPONSE_BYTES_TO_READ)
        response = TCP_UART_MESSAGE_STRUCT.parse(response_bytes)
        if self._verbose:
            print(response.payload)

        if response.payload.startswith(TCP_UART_UNKNOWN_COMMAND_RESPONSE):
            raise LinkplayCliGetRequestUnknownCommandException(response.payload)

        return response.payload

    @staticmethod
    def _extract_number_from_output(output):
        match_result = re.match(rb'AXX\+\w\w\w\+(?P<number>\d\d\d)', output)
        return int(match_result.group('number'))

    def get_volume(self):
        response = self.run_command(f'MCU+VOL+GET')
        return self._extract_number_from_output(response)

    def set_volume(self, volume):
        command = f'MCU+VOL+{volume:03}'
        response = self.run_command(command)
        return self._extract_number_from_output(response)
