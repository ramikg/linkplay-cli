from pathlib import Path

get_request_timeout_seconds = 5
upnp_discover_timeout_message = 5
cache_file_path = Path.home() / '.linkplay_cached_device_address'
log_key = b'wiimulogsecure\x00\x00'
log_chunk_size = 10240
maximum_number_of_alarms = 3
