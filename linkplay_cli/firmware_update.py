import base64
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup
from Crypto.Cipher import AES

from linkplay_cli import config
from linkplay_cli.utils import perform_get_request, LinkplayCliGetRequestFailedException


@dataclass
class OtaProject:
    project_name: str
    uuid_prefix: str
    access_key: str
    secret_key: str

    @property
    def project_id(self):
        return hashlib.sha256(
            f'{self.access_key}{self.uuid_prefix}_{self.project_name}'.encode()
        ).hexdigest()


UUID_PREFIX_LENGTH = 8

OTA_CHECK_SERVERS = [
    'https://wiimhome-ota-gva.linkplay.com/check',
    'https://cloud-ota-gva.linkplay.com/check',
]

# Each project returns the images it actually has.
OTA_IMAGE_NAMES = ['all_in_one_secure', 'mcu', 'gc4a_zip']

OTA_PROJECTS = [
    OtaProject(project_name='ADDON_C10_MkII',
               uuid_prefix='FF98F073',
               access_key='c0c167ab52bd4dcea4cea270804d7033',
               secret_key='9408ff12f54f44dca37bb59bb4a261f2f3c757f73d4c4ea2a58818d006c47d46'),
    OtaProject(project_name='Audiopro-C20',
               uuid_prefix='FF98F0D9',
               access_key='36c10d3589654089b92e9da5cc5e41e8',
               secret_key='d79424d543aa40768c9791fcb4868939b12d55025e914e5cba29642268e08dd1'),
    OtaProject(project_name='AudioPro_C20_W',
               uuid_prefix='FF98FFFE',
               access_key='e85e627c58bd468999d82b03ae5d2951',
               secret_key='bdb9baf1c1b84045af3458534d8871d9725f5b3bef504fc58db36abddf174440'),
]
UUID_PREFIX_TO_OTA_PROJECT = {project.uuid_prefix: project for project in OTA_PROJECTS}


class LinkplayCliFirmwareUpdateNotFoundException(Exception):
    pass


def _url_to_xml_soup(url):
    response = perform_get_request(url)
    return BeautifulSoup(response, 'xml')


def _find_product_url(update_server_url, model, hardware):
    products_soup = _url_to_xml_soup(update_server_url + '/products.xml')

    matching_product_urls = set()
    for product in products_soup.find_all('product'):
        try:
            if model == product.productid.getText() and hardware == product.hardwareversion.getText():
                matching_product_urls.add(getattr(product, 'major-url').getText())
        except AttributeError:
            continue

    if len(matching_product_urls) != 1:
        raise LinkplayCliFirmwareUpdateNotFoundException(f'Product URLs found: {matching_product_urls}')

    return matching_product_urls.pop()


def _find_version_file_url(update_server_url, model, hardware):
    product_url = _find_product_url(update_server_url, model, hardware)
    product_soup = _url_to_xml_soup(product_url)

    return getattr(product_soup.product, 'ver-url').getText()


def print_latest_version_and_release_date(update_server_url, model, hardware):
    VERSION_FILE_VERSION_LINE = 0
    VERSION_FILE_RELEASE_DATE_LINE = 5
    HARDWARE_PREFIX = 'WiiMu-'

    try:
        version_file_url = _find_version_file_url(update_server_url, model, HARDWARE_PREFIX + hardware)
        version_file_lines = perform_get_request(version_file_url).splitlines()
    except (AttributeError, LinkplayCliGetRequestFailedException, LinkplayCliFirmwareUpdateNotFoundException) as e:
        logging.debug(f'Failed retrieving version file from server: {e}, {update_server_url}')
        return

    try:
        version = version_file_lines[VERSION_FILE_VERSION_LINE].split('.', maxsplit=1)[1]
        release_date = version_file_lines[VERSION_FILE_RELEASE_DATE_LINE]
    except (AttributeError, IndexError, LinkplayCliGetRequestFailedException) as e:
        logging.debug(f'Failed parsing version file: {e}, {version_file_lines}')
        return

    print(f'Latest firmware version: {version} (released {release_date})')


def _generate_random_mac():
    return ':'.join(f'{byte:02X}' for byte in os.urandom(6))


def _ota_check(server, ota_project):
    nonce = os.urandom(8).hex()
    timestamp = str(int(time.time() * 1000))
    body = json.dumps({
        'projectId': ota_project.project_id,
        'macAddr': _generate_random_mac(),
        'imgList': [{'imgName': image_name} for image_name in OTA_IMAGE_NAMES],
    })
    sign = hashlib.sha256(
        f'{ota_project.secret_key}accessKey={ota_project.access_key}&nonce={nonce}'
        f'&projectId={ota_project.project_id}&timestamp={timestamp}&secretKey={ota_project.secret_key}'.encode()
    ).hexdigest().upper()
    headers = {'accessKey': ota_project.access_key, 'nonce': nonce, 'projectId': ota_project.project_id,
               'timestamp': timestamp, 'sign': sign}
    response = requests.post(server, data=body, headers=headers, timeout=config.http_request_timeout_seconds)
    ciphertext = base64.b64decode(response.text.strip().strip('"'))
    key = hashlib.md5(ota_project.secret_key.encode()).hexdigest().upper().encode()
    plaintext = AES.new(key, AES.MODE_CBC, nonce.encode()).decrypt(ciphertext)
    return json.loads(plaintext[:-plaintext[-1]])


def print_latest_version_and_release_date_from_ota_check(uuid):
    uuid_prefix = uuid[:UUID_PREFIX_LENGTH].upper()
    ota_project = UUID_PREFIX_TO_OTA_PROJECT.get(uuid_prefix)
    if ota_project is None:
        logging.debug(f'No OTA project known for UUID prefix {uuid_prefix}')
        return False

    for server in OTA_CHECK_SERVERS:
        try:
            result = _ota_check(server, ota_project)
            print(f"Latest firmware version: {result['version']}")
            return True
        except (requests.exceptions.RequestException, ValueError, KeyError, IndexError) as e:
            logging.debug(f'OTA check failed ({server}): {e}')

    return False
