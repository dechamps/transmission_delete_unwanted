import io
import random
import pytest
from transmission_delete_unwanted_tests.conftest import TorrentFile
import transmission_delete_unwanted.mark_unwanted


@pytest.fixture(name="run")
def _fixture_run(transmission_url, monkeypatch):
    def _run(*kargs, stdin, **kwargs):
        with monkeypatch.context() as patch:
            patch.setattr("sys.stdin", io.StringIO(stdin))
            return transmission_delete_unwanted.mark_unwanted.run(
                ["--transmission-url", transmission_url] + list(kargs), **kwargs
            )

    return _run


def test_noop(run):
    run(stdin="")


def test_noop_torrent(run, setup_torrent, get_files_wanted):
    torrent = setup_torrent(
        files={
            "test0.txt": TorrentFile(random.randbytes(4)),
            "test1.txt": TorrentFile(random.randbytes(4)),
        }
    )
    assert get_files_wanted(torrent.transmission.id) == {
        "test0.txt": True,
        "test1.txt": True,
    }
    run(stdin="")
    assert get_files_wanted(torrent.transmission.id) == {
        "test0.txt": True,
        "test1.txt": True,
    }


def test_unmark(run, setup_torrent, get_files_wanted):
    torrent1 = setup_torrent(
        files={
            "test0.txt": TorrentFile(random.randbytes(4)),
            "test1.txt": TorrentFile(random.randbytes(4)),
        }
    )
    torrent2 = setup_torrent(
        files={
            "test0.txt": TorrentFile(random.randbytes(4)),
            "test1.txt": TorrentFile(random.randbytes(4)),
        }
    )
    run(stdin=f"{torrent1.torf.name}/test1.txt")
    assert get_files_wanted(torrent1.transmission.id) == {
        "test0.txt": True,
        "test1.txt": False,
    }
    assert get_files_wanted(torrent2.transmission.id) == {
        "test0.txt": True,
        "test1.txt": True,
    }


def test_unmark_multiple(run, setup_torrent, get_files_wanted):
    torrent1 = setup_torrent(
        files={
            "test0.txt": TorrentFile(random.randbytes(4)),
            "test1.txt": TorrentFile(random.randbytes(4)),
        }
    )
    torrent2 = setup_torrent(
        files={
            "test0.txt": TorrentFile(random.randbytes(4)),
            "test1.txt": TorrentFile(random.randbytes(4)),
        }
    )
    run(stdin=f"{torrent1.torf.name}/test1.txt\n{torrent2.torf.name}/test0.txt")
    assert get_files_wanted(torrent1.transmission.id) == {
        "test0.txt": True,
        "test1.txt": False,
    }
    assert get_files_wanted(torrent2.transmission.id) == {
        "test0.txt": False,
        "test1.txt": True,
    }
