from dataclasses import dataclass
from typing import Literal

UNKNOWN_NAME_STRING = 'Unknown'

PLAYBACK_MODE_NUMBER_TO_NAME = {
    -1: 'None',
    1: 'Apple Music',
    10: 'URL',
    31: 'Spotify',
    40: 'AUX',
    41: 'Bluetooth',
}


@dataclass
class PlayerStatus:
    status_emoji: Literal['▶️', '⏸', '⏹️']
    total_length_string: str
    current_position_string: str
    playback_mode_string: str
    artist: str
    title: str
    album: str
    volume: int
    is_muted: bool
