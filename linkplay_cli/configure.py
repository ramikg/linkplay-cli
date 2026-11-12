import pickle
from dataclasses import dataclass
from typing import List, Optional

from prettytable import PrettyTable

from linkplay_cli import config
from linkplay_cli.device import Device
from linkplay_cli.discovery import LinkplayCliDeviceNotFoundException


@dataclass
class Configuration:
    devices: List[Device]
    # The default device
    active_device: Optional[Device]


def save_configuration_to_file(devices: List[Device], default_device: Device) -> None:
    with open(config.configuration_file_path, 'wb') as configuration_file:
        configuration = Configuration(devices=devices, active_device=default_device)
        pickle.dump(configuration, configuration_file)


def load_configuration_from_file() -> Configuration:
    try:
        with open(config.configuration_file_path, 'rb') as configuration_file:
            configuration = pickle.load(configuration_file)
        return configuration
    except FileNotFoundError:
        return Configuration(devices=[], active_device=None)


def find_device_by_name_or_ip(devices: List[Device], name_or_ip: str) -> Optional[Device]:
    matches = [device for device in devices if name_or_ip in (device.name, str(device.ip_address))]
    if len(matches) > 1:
        raise LinkplayCliDeviceNotFoundException(
            f'Multiple devices match "{name_or_ip}": {", ".join(f"{d.name} ({d.ip_address})" for d in matches)}')
    return matches[0] if matches else None


def prompt_user_to_choose_default_device(devices: List[Device], default_device: Optional[Device] = None) -> Device:
    if not devices:
        raise LinkplayCliDeviceNotFoundException('No devices to choose from.')

    if len(devices) == 1:
        print('Only one device available.')
        choice_index = 0
    else:
        table = PrettyTable()
        table.field_names = ['', 'Device name', 'Model', 'IP address', 'Port', 'Protocol']
        for device_index, device in enumerate(devices):
            table.add_row([device_index, device.name, device.model, device.ip_address, device.port, device.protocol])
        table_lines = table.get_string().splitlines()
        for device_index, device in enumerate(devices):
            if default_device and device.ip_address == default_device.ip_address:
                # Skip the top border, header and header separator
                table_lines[3 + device_index] += ' <-- default'
        print('\n'.join(table_lines))

        choice = input(f'Choose a default device (0–{len(devices) - 1}): ')
        if choice.isdigit() and 0 <= int(choice) <= len(devices) - 1:
            choice_index = int(choice)
        else:
            raise LinkplayCliDeviceNotFoundException('Invalid choice. Default device unchanged.')

    save_configuration_to_file(devices, devices[choice_index])
    print(f'Choosing {devices[choice_index]}.')
    return devices[choice_index]
