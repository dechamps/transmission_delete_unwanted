from contextlib import closing
import socket
import subprocess
import backoff
import pytest
import transmission_delete_unwanted.script


# TODO: this is ugly, racy and insecure. Ideally we should use an Unix socket for
# this, but transmission_rpc does not support Unix sockets (yet).
#
# Shamelessly stolen from https://stackoverflow.com/a/45690594
def find_free_port():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@backoff.on_exception(
    backoff.expo, ConnectionRefusedError, factor=0.05, max_time=30, jitter=None
)
def _try_connect(address):
    socket.create_connection(address).close()


@pytest.fixture(name="transmission_url")
def _fixture_transmission_daemon(tmp_path):
    transmission_address = "127.0.0.1"
    transmission_config_dir = tmp_path / "transmission_config"
    transmission_config_dir.mkdir()
    transmission_download_dir = tmp_path / "transmission_download"
    transmission_download_dir.mkdir()
    rpc_port = find_free_port()
    transmission_daemon_process = subprocess.Popen([
        "transmission-daemon",
        "--foreground",
        "--config-dir",
        str(transmission_config_dir),
        "--rpc-bind-address",
        transmission_address,
        "--port",
        str(rpc_port),
        "--peerport",
        str(find_free_port()),
        "--download-dir",
        str(transmission_download_dir),
        "--log-level=debug",
    ])
    try:
        _try_connect((transmission_address, rpc_port))
        yield f"http://{transmission_address}:{rpc_port}"
    finally:
        # It would be cleaner to ask Transmission to shut itself down, but sadly
        # transmission_rpc does not support the relevant RPC command:
        #   https://github.com/trim21/transmission-rpc/issues/483
        transmission_daemon_process.terminate()
        transmission_daemon_process.wait()


def test_connect(transmission_url):
    transmission_delete_unwanted.script.main([
        "--transmission-url",
        transmission_url,
        "--torrent-id",
        "295184e2e91c10c2b1c35c2890a8394ff53d3be7",
    ])
