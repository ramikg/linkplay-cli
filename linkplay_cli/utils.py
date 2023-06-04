from http import HTTPStatus

import requests

from linkplay_cli import config


class LinkplayCliGetRequestFailedException(Exception):
    pass


def perform_get_request(url, verbose, params=None, expect_json=False, expect_bytes=False):
    response = requests.get(url, params=params, timeout=config.get_request_timeout_seconds)

    verbose_message = f'GET {response.request.url} returned {response.status_code}: {response.text}'

    if response.status_code != HTTPStatus.OK:
        raise LinkplayCliGetRequestFailedException(verbose_message)
    if verbose:
        print(verbose_message)

    if expect_json:
        return response.json()
    elif expect_bytes:
        return response.content
    else:
        return response.text
