import logging
import re
from http import HTTPStatus
from typing import Optional

import requests
from async_upnp_client.aiohttp import AiohttpRequester
from async_upnp_client.client import UpnpDevice, UpnpAction
from async_upnp_client.client_factory import UpnpFactory
from bs4 import BeautifulSoup

from linkplay_cli.player_status import PlayerStatus, PLAYBACK_MODE_NUMBER_TO_NAME, UNKNOWN_NAME_STRING
from linkplay_cli.utils import run_async_function_synchronously, player_status_string_to_emoji

PLAYLIST_ID_IN_TRACK_SOURCE_REGEX = r'spotify:playlist:(?P<playlist_id>[a-zA-Z0-9]+)'


class Upnp:
    def __init__(self, upnp_location: str):
        self._requester = AiohttpRequester()
        self._factory = UpnpFactory(self._requester)
        self._device: UpnpDevice = run_async_function_synchronously(self._factory.async_create_device(upnp_location))
        self._av_transport = self._device.service_id('urn:upnp-org:serviceId:AVTransport')

    @staticmethod
    def _call_action_synchronously(action: UpnpAction):
        return run_async_function_synchronously(action.async_call(InstanceID=0))

    @staticmethod
    def _trim_duration_string(duration_string: str) -> str:
        return duration_string.removeprefix('00:0').removeprefix('00:')

    @staticmethod
    def _get_playlist_owner(track_source: str) -> Optional[str]:
        match_result = re.match(PLAYLIST_ID_IN_TRACK_SOURCE_REGEX, track_source)
        if not match_result:
            logging.debug(f'Failed parsing TrackSource: {track_source}')
            return None
        playlist_id = match_result.group('playlist_id')

        try:
            playlist_response = requests.get(f'https://open.spotify.com/playlist/{playlist_id}')
        except requests.exceptions.RequestException as e:
            logging.debug(f'Spotify playlist request failed with the following exception: {e}')
            return None
        if playlist_response.status_code != HTTPStatus.OK:
            logging.debug(f'Spotify playlist request failed with status code {playlist_response.status_code}')
            return None

        soup = BeautifulSoup(playlist_response.text, 'html.parser')
        og_description = soup.find('meta', property='og:description')
        if not og_description or not og_description.get('content'):
            logging.debug(f'Failed getting Open Graph description: {og_description}')
            return None

        soup_match_result = re.match(r'Playlist · (?P<owner>[\w\s]+) ·', og_description['content'])
        if not match_result:
            logging.debug(f'Failed parsing Open Graph description: {og_description["content"]}')
            return None

        return soup_match_result.group('owner')


    def get_player_status(self):
        get_info_ex_action = self._av_transport.action('GetInfoEx')
        info = self._call_action_synchronously(get_info_ex_action)
        logging.debug(info)

        track_metadata = info['TrackMetaData']
        track_metadata_xml_soup = BeautifulSoup(track_metadata, 'xml')

        artist_element = track_metadata_xml_soup.find('upnp:artist')
        artist = artist_element.get_text() if artist_element else UNKNOWN_NAME_STRING
        title_element = track_metadata_xml_soup.find('dc:title')
        title = title_element.get_text() if title_element else UNKNOWN_NAME_STRING
        album_element = track_metadata_xml_soup.find('upnp:album')
        album = album_element.get_text() if album_element else UNKNOWN_NAME_STRING
        playlist_element = track_metadata_xml_soup.find('song:subid')
        playlist_name = playlist_element.get_text() if playlist_element else None
        playlist_owner = self._get_playlist_owner(info['TrackSource']) if playlist_name else None
        playlist_string = f"{playlist_name} by {playlist_owner}" if playlist_owner else playlist_name

        playback_mode = int(info['PlayType'])
        if playback_mode in PLAYBACK_MODE_NUMBER_TO_NAME:
            playback_mode_string = PLAYBACK_MODE_NUMBER_TO_NAME[playback_mode]
        else:
            playback_mode_string = UNKNOWN_NAME_STRING

        return PlayerStatus(
            status_emoji=player_status_string_to_emoji(info['CurrentTransportState']),
            total_length_string=self._trim_duration_string(info['TrackDuration']),
            current_position_string=self._trim_duration_string(info['RelTime']),
            playback_mode_string=playback_mode_string,
            artist=artist,
            title=title,
            album=album,
            playlist=playlist_string,
            volume=int(info['CurrentVolume']),
            is_muted=False,  # GetInfoEx doesn't return this information.
        )
