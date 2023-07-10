from http import HTTPStatus
import warnings

from linkplay_cli import config


def _supress_openssl_warning_when_importing_requests():
    """
    Invoking the CLI on a system without OpenSSL (e.g. one with LibreSSL) may result in a warning we'd like to supress.
    This warning is raised when importing urllib3 >= 2.0.3 (which the requests library may do).
    """
    with warnings.catch_warnings(record=True) as caught_warnings:
        from urllib3.exceptions import NotOpenSSLWarning

    for w in caught_warnings:
        if w.category is NotOpenSSLWarning:
            continue
        else:
            warnings.warn(message=w.message, category=w.category, source=w.source)


_supress_openssl_warning_when_importing_requests()
import requests


class LinkplayCliGetRequestFailedException(Exception):
    pass


def perform_get_request(url, verbose, params=None, expect_json=False, expect_bytes=False):
    try:
        response = requests.get(url, params=params, timeout=config.get_request_timeout_seconds)
    except requests.exceptions.RequestException as e:
        raise LinkplayCliGetRequestFailedException(str(e))

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
