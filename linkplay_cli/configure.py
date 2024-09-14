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
    active_device: Optional[Device]

def save_configuration_to_file(devices: List[Device], active_device: Device) -> None:
    with open(config.configuration_file_path, 'wb') as configuration_file:
        configuration = Configuration(devices=devices, active_device=active_device)
        pickle.dump(configuration, configuration_file)

def load_configuration_from_file() -> Configuration:
    try:
        with open(config.configuration_file_path, 'rb') as configuration_file:
            configuration = pickle.load(configuration_file)
        return configuration
    except FileNotFoundError:
        return Configuration(devices=[], active_device=None)


def prompt_user_to_choose_active_device(devices: List[Device]) -> Device:
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
        print(table)

        choice = input(f'Choose a device (0–{len(devices) - 1}): ')
        if choice.isdigit() and 0 <= int(choice) <= len(devices) - 1:
            choice_index = int(choice)
        else:
            print('Invalid choice. Active device unchanged.')
            raise LinkplayCliDeviceNotFoundException('Invalid device choice.')

    save_configuration_to_file(devices, devices[choice_index])
    print(f'Choosing {devices[choice_index]}.')
    return devices[choice_index]
