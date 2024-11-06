import asyncio
from http import HTTPStatus
import urllib.parse
import warnings
from typing import Literal

import urllib3
from urllib3.exceptions import InsecureRequestWarning

from linkplay_cli import config


UNKNOWN_COMMAND_STRING = "unknown command"


def _supress_openssl_warning_when_importing_requests():
    """
    Invoking the CLI on a system without OpenSSL (e.g. one with LibreSSL) may result in a warning we'd like to supress.
    This warning is raised when importing urllib3 >= 2.0.3 (which the requests library may do).
    """
    with warnings.catch_warnings(record=True) as caught_warnings:
        try:
            from urllib3.exceptions import NotOpenSSLWarning
        except ImportError:
            return

    for w in caught_warnings:
        if w.category is NotOpenSSLWarning:
            continue
        else:
            warnings.warn(message=w.message, category=w.category, source=w.source)


_supress_openssl_warning_when_importing_requests()
import requests
urllib3.disable_warnings(InsecureRequestWarning)


class LinkplayCliGetRequestFailedException(Exception):
    pass


class LinkplayCliGetRequestUnknownCommandException(Exception):
    pass


def perform_get_request(url, verbose, params=None, expect_json=False, expect_bytes=False):
    try:
        response = requests.get(url, params=params, timeout=config.get_request_timeout_seconds, cert=str(config.client_certificate_path), verify=False)
    except requests.exceptions.RequestException as e:
        raise LinkplayCliGetRequestFailedException(str(e))

    verbose_message = f'GET {urllib.parse.unquote(response.request.url)} returned {response.status_code}: {response.text}'

    if response.status_code != HTTPStatus.OK:
        raise LinkplayCliGetRequestFailedException(verbose_message)
    if response.text.lower() == UNKNOWN_COMMAND_STRING:
        raise LinkplayCliGetRequestUnknownCommandException(verbose_message)
    if verbose:
        print(verbose_message)

    response.encoding = 'utf-8'
    if expect_json:
        return response.json()
    elif expect_bytes:
        return response.content
    else:
        return response.text

def run_async_function_synchronously(future):
    return asyncio.new_event_loop().run_until_complete(future)

def player_status_string_to_emoji(status: str) -> Literal['▶️', '⏸', '⏹️']:
    if status in ['play', 'PLAYING']:
        return '▶️'
    elif status == ['pause', 'PAUSED_PLAYBACK']:
        return '⏸'
    else:
        return '⏹️'
