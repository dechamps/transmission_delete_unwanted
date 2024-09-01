import base64
import contextlib
import collections
import enum
import socket
import struct
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


@backoff.on_predicate(backoff.expo, factor=0.05, max_time=30, jitter=None)
def _poll_until(predicate):
    return predicate()


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


def _to_pieces_array(transmission_torrent):
    pieces_bitfield = base64.b64decode(transmission_torrent.pieces)
    piece_count = transmission_torrent.piece_count
    assert len(pieces_bitfield) == -(-piece_count // 8)
    return [
        byte & (1 << (bitpos - 1)) != 0
        for bitpos in range(8, 0, -1)
        for byte in pieces_bitfield
    ][: transmission_torrent.piece_count]


_MIN_PIECE_SIZE = 16384  # BEP-0052


@pytest.fixture(name="setup_torrent")
def _fixture_setup_torrent(transmission_client):
    download_dir = transmission_client.get_session().download_dir

    def create_torrent(files, piece_size):
        path = pathlib.Path(download_dir) / f"test_torrent_{uuid.uuid4()}"
        path.mkdir()
        for file_name, file_contents in files.items():
            with open(path / file_name, "wb") as file:
                file.write(file_contents)
        torf_torrent = torf.Torrent(path=path, piece_size=piece_size, private=True)
        torf_torrent.generate()
        transmission_torrent = transmission_client.add_torrent(torf_torrent.dump())

        def get_torrent(arguments):
            return transmission_client.get_torrent(
                transmission_torrent.id, arguments=arguments
            )

        transmission_info = get_torrent([
            "hashString",
            "wanted",
        ])
        assert transmission_info.info_hash == torf_torrent.infohash
        assert all(transmission_info.wanted)

        _poll_until(
            lambda: get_torrent(["status"]).status != transmission_rpc.Status.CHECKING
        )
        transmission_info = get_torrent([
            "status",
            "percentComplete",
            "percentDone",
            "leftUntilDone",
            "pieceCount",
            "pieces",
        ])
        assert transmission_info.status == transmission_rpc.Status.SEEDING
        assert transmission_info.percent_complete == 1
        assert transmission_info.percent_done == 1
        assert transmission_info.left_until_done == 0
        assert all(_to_pieces_array(transmission_info))

        return Torrent(
            path=path,
            torf=torf_torrent,
            transmission=transmission_torrent,
        )

    return create_torrent


@pytest.fixture(name="transmission_delete_unwanted")
def _fixture_transmission_delete_unwanted(transmission_url):
    return lambda *kargs: transmission_delete_unwanted.script.main(
        ["--transmission-url", transmission_url] + list(kargs)
    )


_TorrentIdKind = enum.Enum("TorrentIdKind", ["TRANSMISSION_ID", "HASH"])


@pytest.fixture(
    name="transmission_delete_unwanted_torrent",
    params=[_TorrentIdKind.TRANSMISSION_ID, _TorrentIdKind.HASH],
)
def _fixture_transmission_delete_unwanted_torrent(
    request, transmission_delete_unwanted
):
    return lambda torrent, *kargs: transmission_delete_unwanted(
        "--torrent-id",
        {
            _TorrentIdKind.TRANSMISSION_ID: str(torrent.transmission.id),
            _TorrentIdKind.HASH: torrent.torf.infohash,
        }[request.param],
    )


def test_noop_onefile_onepiece(transmission_delete_unwanted_torrent, setup_torrent):
    torrent = setup_torrent(files={"test.txt": b"0000"}, piece_size=_MIN_PIECE_SIZE)
    assert torrent.torf.pieces == 1
    transmission_delete_unwanted_torrent(torrent)
    torrent.torf.verify(path=torrent.path)


def test_noop_multifile_onepiece(transmission_delete_unwanted_torrent, setup_torrent):
    torrent = setup_torrent(
        files={"test0.txt": b"0000", "test1.txt": b"0000", "test3.txt": b"0000"},
        piece_size=_MIN_PIECE_SIZE,
    )
    assert torrent.torf.pieces == 1
    transmission_delete_unwanted_torrent(torrent)
    torrent.torf.verify(path=torrent.path)


def test_noop_onefile_multipiece(transmission_delete_unwanted_torrent, setup_torrent):
    torrent = setup_torrent(
        files={"test.txt": b"x" * _MIN_PIECE_SIZE * 4},
        piece_size=_MIN_PIECE_SIZE,
    )
    assert torrent.torf.pieces == 4
    transmission_delete_unwanted_torrent(torrent)
    torrent.torf.verify(path=torrent.path)


def test_noop_multifile_multipiece_aligned(
    transmission_delete_unwanted_torrent, setup_torrent
):
    torrent = setup_torrent(
        files={
            "test0.txt": b"0" * _MIN_PIECE_SIZE,
            "test1.txt": b"0" * _MIN_PIECE_SIZE,
            "test2.txt": b"0" * _MIN_PIECE_SIZE,
        },
        piece_size=_MIN_PIECE_SIZE,
    )
    assert torrent.torf.pieces == 3
    transmission_delete_unwanted_torrent(torrent)
    torrent.torf.verify(path=torrent.path)


def test_noop_multifile_multipiece_unaligned(
    transmission_delete_unwanted_torrent, setup_torrent
):
    torrent = setup_torrent(
        files={
            "test0.txt": b"0" * (_MIN_PIECE_SIZE + 1),
            "test1.txt": b"0" * _MIN_PIECE_SIZE,
            "test2.txt": b"0" * _MIN_PIECE_SIZE,
        },
        piece_size=_MIN_PIECE_SIZE,
    )
    assert torrent.torf.pieces == 4
    transmission_delete_unwanted_torrent(torrent)
    torrent.torf.verify(path=torrent.path)
