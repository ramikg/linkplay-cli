from bs4 import BeautifulSoup
import requests

from linkplay_cli.utils import perform_get_request


class LinkplayCliFirmwareUpdateNotFoundException(Exception):
    pass


def _url_to_xml_soup(url):
    response = perform_get_request(url, verbose=False)
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


def print_latest_version_and_release_date(update_server_url, model, hardware, verbose):
    VERSION_FILE_VERSION_LINE = 0
    VERSION_FILE_RELEASE_DATE_LINE = 5
    HARDWARE_PREFIX = 'WiiMu-'

    try:
        version_file_url = _find_version_file_url(update_server_url, model, HARDWARE_PREFIX + hardware)
        version_file_lines = perform_get_request(version_file_url, verbose=verbose).splitlines()
    except (AttributeError, requests.exceptions.RequestException, LinkplayCliFirmwareUpdateNotFoundException) as e:
        if verbose:
            print(f'Failed retrieving version file from server: {e}, {update_server_url}')
        return

    try:
        version = version_file_lines[VERSION_FILE_VERSION_LINE].split('.', maxsplit=1)[1]
        release_date = version_file_lines[VERSION_FILE_RELEASE_DATE_LINE]
    except (AttributeError, IndexError, requests.exceptions.RequestException) as e:
        if verbose:
            print(f'Failed parsing version file: {e}, {version_file_lines}')
        return

    print(f'Latest firmware version: {version} (released {release_date})')
