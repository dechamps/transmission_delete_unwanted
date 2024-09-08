import contextlib
import collections
import socket
import subprocess
import pathlib
import shutil
import uuid
import backoff
import torf
import pytest
import transmission_rpc


def _removeprefix(string, prefix):
    assert string.startswith(prefix)
    return string[len(prefix) :]


# TODO: this is ugly, racy and insecure. Ideally we should use an Unix socket for
# this, but transmission_rpc does not support Unix sockets (yet).
#
# Shamelessly stolen from https://stackoverflow.com/a/45690594
def _find_free_port():
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@backoff.on_exception(
    backoff.constant, ConnectionRefusedError, interval=0.1, max_time=30, jitter=None
)
def _try_connect(address):
    socket.create_connection(address).close()


@backoff.on_predicate(backoff.constant, interval=0.1, max_time=30, jitter=None)
def poll_until(predicate):
    return predicate()


@pytest.fixture(name="transmission_url", scope="session")
def _fixture_transmission_daemon(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("transmission-")
    address = "127.0.0.1"
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    download_dir = tmp_path / "download"
    download_dir.mkdir()
    rpc_port = _find_free_port()
    try:
        with subprocess.Popen([
            "transmission-daemon",
            "--foreground",
            "--config-dir",
            str(config_dir),
            "--rpc-bind-address",
            address,
            "--port",
            str(rpc_port),
            "--peerport",
            str(_find_free_port()),
            "--download-dir",
            str(download_dir),
            "--log-level=debug",
        ]) as daemon_process:
            try:
                _try_connect((address, rpc_port))
                yield f"http://{address}:{rpc_port}"
            finally:
                # It would be cleaner to ask Transmission to shut itself down, but sadly
                # transmission_rpc does not support the relevant RPC command:
                #   https://github.com/trim21/transmission-rpc/issues/483
                daemon_process.terminate()
    finally:
        shutil.rmtree(download_dir)
        shutil.rmtree(config_dir)


@pytest.fixture(name="transmission_client")
def _fixture_transmission_client(transmission_url):
    with transmission_rpc.from_url(transmission_url) as transmission_client:
        yield transmission_client


Torrent = collections.namedtuple("Torrent", ["path", "torf", "transmission"])


@pytest.fixture(name="verify_torrent")
def _fixture_verify_torrent(transmission_client):
    def verify_torrent(torrent_id, request=True):
        if request:
            transmission_client.verify_torrent(torrent_id)
        poll_until(
            lambda: transmission_client.get_torrent(
                torrent_id, arguments=["status"]
            ).status
            != transmission_rpc.Status.CHECKING
        )

    return verify_torrent


TorrentFile = collections.namedtuple(
    "TorrentFile", ["contents", "wanted"], defaults=[True]
)


@pytest.fixture(name="setup_torrent")
def _fixture_setup_torrent(transmission_client, verify_torrent):
    download_dir = transmission_client.get_session().download_dir

    paths = []
    transmission_torrent_ids = []

    def create_torrent(
        files,
        piece_size=16384,
        before_add=None,
    ):
        path = pathlib.Path(download_dir) / f"test_torrent_{uuid.uuid4()}"
        path.mkdir()
        paths.append(path)
        for file_name, torrent_file in files.items():
            file_path = path / file_name
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "wb") as file:
                file.write(torrent_file.contents)
        torf_torrent = torf.Torrent(path=path, piece_size=piece_size, private=True)
        torf_torrent.generate()
        torf_torrent._path = None  # https://github.com/rndusr/torf/issues/46 pylint:disable=protected-access

        if before_add is not None:
            before_add(path)

        unwanted_files = [
            file_index
            for file_index, file in enumerate(torf_torrent.files)
            if not files[_removeprefix(str(file), f"{torf_torrent.name}/")].wanted
        ]
        transmission_torrent = transmission_client.add_torrent(
            torf_torrent.dump(), files_unwanted=unwanted_files
        )
        transmission_torrent_ids.append(transmission_torrent.id)

        transmission_info = transmission_client.get_torrent(
            transmission_torrent.id,
            arguments=[
                "hashString",
                "wanted",
            ],
        )
        assert transmission_info.info_hash == torf_torrent.infohash

        files_wanted = [True] * len(torf_torrent.files)
        for unwanted_file_index in unwanted_files:
            files_wanted[unwanted_file_index] = False
        assert transmission_info.wanted == files_wanted

        verify_torrent(transmission_torrent.id, request=False)

        return Torrent(
            path=path,
            torf=torf_torrent,
            transmission=transmission_torrent,
        )

    yield create_torrent

    if len(transmission_torrent_ids) > 0:
        transmission_client.remove_torrent(transmission_torrent_ids)
    for path in paths:
        shutil.rmtree(path)
