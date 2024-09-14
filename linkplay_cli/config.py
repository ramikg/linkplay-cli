from pathlib import Path

get_request_timeout_seconds = 5
upnp_discover_timeout_message = 5
configuration_file_path = Path.home() / '.linkplaycli.config'
client_certificate_path = Path(__file__).parent / 'linkplay_client.pem'
log_key = b'wiimulogsecure\x00\x00'
log_chunk_size = 10240
maximum_number_of_alarms = 3
http_ports = [80]
tls_ports = [4443]
