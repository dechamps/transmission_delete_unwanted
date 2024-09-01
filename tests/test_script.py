import contextlib
import collections
import socket
import subprocess
import pathlib
import uuid
import backoff
import pytest
import torf
import transmission_rpc
import transmission_delete_unwanted.script


# TODO: this is ugly, racy and insecure. Ideally we should use an Unix socket for
# this, but transmission_rpc does not support Unix sockets (yet).
#
# Shamelessly stolen from https://stackoverflow.com/a/45690594
def find_free_port():
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@backoff.on_exception(
    backoff.expo, ConnectionRefusedError, factor=0.05, max_time=30, jitter=None
)
def _try_connect(address):
    socket.create_connection(address).close()


@pytest.fixture(name="transmission_url")
def _fixture_transmission_daemon(tmp_path):
    address = "127.0.0.1"
    config_dir = tmp_path / "transmission_config"
    config_dir.mkdir()
    download_dir = tmp_path / "transmission_download"
    download_dir.mkdir()
    rpc_port = find_free_port()
    daemon_process = subprocess.Popen([
        "transmission-daemon",
        "--foreground",
        "--config-dir",
        str(config_dir),
        "--rpc-bind-address",
        address,
        "--port",
        str(rpc_port),
        "--peerport",
        str(find_free_port()),
        "--download-dir",
        str(download_dir),
        "--log-level=debug",
    ])
    try:
        _try_connect((address, rpc_port))
        yield f"http://{address}:{rpc_port}"
    finally:
        # It would be cleaner to ask Transmission to shut itself down, but sadly
        # transmission_rpc does not support the relevant RPC command:
        #   https://github.com/trim21/transmission-rpc/issues/483
        daemon_process.terminate()
        daemon_process.wait()


@pytest.fixture(name="transmission_client")
def _fixture_transmission_client(transmission_url):
    with transmission_rpc.from_url(transmission_url) as transmission_client:
        yield transmission_client


Torrent = collections.namedtuple("Torrent", ["path", "torf", "transmission"])


@pytest.fixture(name="setup_torrent")
def _fixture_setup_torrent(transmission_client):
    download_dir = transmission_client.get_session().download_dir

    def _create_torrent():
        path = pathlib.Path(download_dir) / f"test_torrent_{uuid.uuid4()}"
        path.mkdir()
        with open(path / "test.txt", "w", encoding="utf-8") as file:
            file.write("test")
        torrent = torf.Torrent(path=path, private=True)
        torrent.generate()
        return Torrent(
            path=path,
            torf=torrent,
            transmission=transmission_client.add_torrent(torrent.dump()),
        )

    return _create_torrent


def test_noop(transmission_url, setup_torrent):
    torrent = setup_torrent()
    transmission_delete_unwanted.script.main([
        "--transmission-url",
        transmission_url,
        "--torrent-id",
        str(torrent.transmission.id),
    ])
    torrent.torf.verify(path=torrent.path)
