import random
import pytest
from transmission_delete_unwanted_tests.conftest import TorrentFile
import transmission_delete_unwanted.mark_unwanted


@pytest.fixture(name="run")
def _fixture_run(transmission_url):
    return lambda *kargs, **kwargs: transmission_delete_unwanted.mark_unwanted.run(
        ["--transmission-url", transmission_url] + list(kargs), **kwargs
    )


@pytest.fixture(name="get_files_wanted")
def _fixture_get_files_wanted(transmission_client):
    def get_files_wanted(torrent_id):
        torrent_info = transmission_client.get_torrent(
            torrent_id, arguments=["files", "wanted"]
        )
        return {
            file["name"]: wanted
            for file, wanted in zip(
                torrent_info.fields["files"], torrent_info.wanted, strict=True
            )
        }

    return get_files_wanted


def test_noop(run):
    run()


def test_noop_torrent(run, setup_torrent, get_files_wanted):
    torrent = setup_torrent(
        files={
            "test0.txt": TorrentFile(random.randbytes(4)),
            "test1.txt": TorrentFile(random.randbytes(4)),
        }
    )
    assert get_files_wanted(torrent.transmission.id) == {
        f"{torrent.torf.name}/test0.txt": True,
        f"{torrent.torf.name}/test1.txt": True,
    }
    run()
    assert get_files_wanted(torrent.transmission.id) == {
        f"{torrent.torf.name}/test0.txt": True,
        f"{torrent.torf.name}/test1.txt": True,
    }
