import enum
import random
import pytest
import transmission_rpc
from transmission_delete_unwanted_tests.conftest import TorrentFile, poll_until
import transmission_delete_unwanted.delete_unwanted
import transmission_delete_unwanted.pieces


@pytest.fixture(name="assert_torrent_status")
def _fixture_assert_torrent_status(transmission_client):
    def assert_torrent_status(
        torrent_id,
        expect_completed=True,
        expect_pieces=None,
    ):
        transmission_info = transmission_client.get_torrent(
            torrent_id,
            arguments=[
                "status",
                "percentComplete",
                "percentDone",
                "leftUntilDone",
                "pieceCount",
                "pieces",
            ],
        )
        pieces = transmission_delete_unwanted.pieces.to_array(
            transmission_info.pieces, transmission_info.piece_count
        )
        if expect_completed:
            assert transmission_info.status == transmission_rpc.Status.SEEDING
            assert transmission_info.percent_done == 1
            assert transmission_info.left_until_done == 0
            assert expect_pieces is not None or all(pieces)
        else:
            assert transmission_info.status == transmission_rpc.Status.DOWNLOADING
            assert transmission_info.percent_complete < 1
            assert transmission_info.percent_done < 1
            assert transmission_info.left_until_done > 0
            assert expect_pieces is not None or not all(pieces)
        if expect_pieces is not None:
            assert pieces == expect_pieces

    return assert_torrent_status


_MIN_PIECE_SIZE = 16384  # BEP-0052


@pytest.fixture(name="run")
def _fixture_run(transmission_url):
    return lambda *kargs, **kwargs: transmission_delete_unwanted.delete_unwanted.run(
        ["--transmission-url", transmission_url] + list(kargs), **kwargs
    )


_TorrentIdKind = enum.Enum("TorrentIdKind", ["TRANSMISSION_ID", "HASH"])


@pytest.fixture(
    name="run_with_torrent",
    params=[_TorrentIdKind.TRANSMISSION_ID, _TorrentIdKind.HASH],
)
def _fixture_run_with_torrent(request, run):
    return lambda torrent, *kargs, **kwargs: run(
        "--torrent-id",
        {
            _TorrentIdKind.TRANSMISSION_ID: str(torrent.transmission.id),
            _TorrentIdKind.HASH: torrent.torf.infohash,
        }[request.param],
        *kargs,
        **kwargs,
    )


def _check_file_tree(root, files_contents):
    files_contents = {
        root / file_name: file_content
        for file_name, file_content in files_contents.items()
    }
    for directory_path, _, file_names in root.walk():
        for file_name in file_names:
            file_path = directory_path / file_name
            file_contents = files_contents.get(file_path)
            assert file_contents is not None, f"Did not expect to find {file_path}"
            del files_contents[file_path]

            with open(file_path, "rb") as file:
                assert file.read() == file_contents, f"Contents mismatch in {file_path}"

    assert len(files_contents) == 0, f"Files not found: {list(files_contents.keys())}"


def test_noop_onefile_onepiece(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
    verify_torrent,
):
    torrent = setup_torrent(
        files={"test.txt": TorrentFile(random.randbytes(4))}, piece_size=_MIN_PIECE_SIZE
    )
    assert torrent.torf.pieces == 1
    assert_torrent_status(torrent.transmission.id)
    run_with_torrent(torrent)
    verify_torrent(torrent.transmission.id)
    assert_torrent_status(torrent.transmission.id)


def test_noop_multifile_onepiece(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
    verify_torrent,
):
    torrent = setup_torrent(
        files={
            "test0.txt": TorrentFile(random.randbytes(4)),
            "test1.txt": TorrentFile(random.randbytes(4)),
            "test3.txt": TorrentFile(random.randbytes(4)),
        },
        piece_size=_MIN_PIECE_SIZE,
    )
    assert torrent.torf.pieces == 1
    assert_torrent_status(torrent.transmission.id)
    run_with_torrent(torrent)
    verify_torrent(torrent.transmission.id)
    assert_torrent_status(torrent.transmission.id)


def test_noop_multifile_onepiece_unwanted(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
    verify_torrent,
):
    torrent = setup_torrent(
        files={
            "test0.txt": TorrentFile(random.randbytes(4)),
            "test1.txt": TorrentFile(random.randbytes(4), wanted=False),
            "test3.txt": TorrentFile(random.randbytes(4)),
        },
        piece_size=_MIN_PIECE_SIZE,
    )
    assert torrent.torf.pieces == 1
    assert_torrent_status(torrent.transmission.id)
    run_with_torrent(torrent)
    verify_torrent(torrent.transmission.id)
    assert_torrent_status(torrent.transmission.id)


def test_noop_onefile_multipiece(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
    verify_torrent,
):
    torrent = setup_torrent(
        files={"test.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE * 4))},
        piece_size=_MIN_PIECE_SIZE,
    )
    assert torrent.torf.pieces == 4
    assert_torrent_status(torrent.transmission.id)
    run_with_torrent(torrent)
    verify_torrent(torrent.transmission.id)
    assert_torrent_status(torrent.transmission.id)


def test_noop_multifile_multipiece_aligned(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
    verify_torrent,
):
    torrent = setup_torrent(
        files={
            "test0.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE)),
            "test1.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE)),
            "test2.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE)),
        },
        piece_size=_MIN_PIECE_SIZE,
    )
    assert torrent.torf.pieces == 3
    assert_torrent_status(torrent.transmission.id)
    run_with_torrent(torrent)
    verify_torrent(torrent.transmission.id)
    assert_torrent_status(torrent.transmission.id)


def test_noop_multifile_multipiece_aligned_incomplete(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
    verify_torrent,
):
    torrent = setup_torrent(
        files={
            "test0.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE)),
            "test1.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE)),
            "test2.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE)),
        },
        piece_size=_MIN_PIECE_SIZE,
        before_add=lambda path: (path / "test1.txt").unlink(),
    )
    assert torrent.torf.pieces == 3

    def check_torrent_status():
        assert_torrent_status(
            torrent.transmission.id,
            expect_completed=False,
            expect_pieces=[True, False, True],
        )

    check_torrent_status()
    run_with_torrent(torrent)
    verify_torrent(torrent.transmission.id)
    check_torrent_status()


def test_noop_multifile_multipiece_aligned_incomplete_unwanted(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
    verify_torrent,
):
    torrent = setup_torrent(
        files={
            "test0.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE)),
            "test1.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE), wanted=False),
            "test2.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE)),
        },
        piece_size=_MIN_PIECE_SIZE,
        before_add=lambda path: (path / "test1.txt").unlink(),
    )
    assert torrent.torf.pieces == 3

    def check_torrent_status():
        assert_torrent_status(
            torrent.transmission.id,
            expect_completed=True,
            expect_pieces=[True, False, True],
        )

    check_torrent_status()
    run_with_torrent(torrent)
    verify_torrent(torrent.transmission.id)
    check_torrent_status()


@pytest.mark.parametrize("shift_bytes", [1, _MIN_PIECE_SIZE // 2, _MIN_PIECE_SIZE - 1])
def test_noop_multifile_multipiece_unaligned_incomplete(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
    verify_torrent,
    shift_bytes,
):
    torrent = setup_torrent(
        files={
            "test0.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE + shift_bytes)),
            "test1.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE)),
            "test2.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE)),
        },
        piece_size=_MIN_PIECE_SIZE,
        before_add=lambda path: (path / "test1.txt").unlink(),
    )
    assert torrent.torf.pieces == 4

    def check_torrent_status():
        assert_torrent_status(
            torrent.transmission.id,
            expect_completed=False,
            expect_pieces=[True, False, False, True],
        )

    check_torrent_status()
    run_with_torrent(torrent)
    verify_torrent(torrent.transmission.id)
    check_torrent_status()


@pytest.mark.parametrize("shift_bytes", [1, _MIN_PIECE_SIZE // 2, _MIN_PIECE_SIZE - 1])
def test_noop_multifile_multipiece_unaligned_incomplete_unwanted(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
    verify_torrent,
    shift_bytes,
):
    torrent = setup_torrent(
        files={
            "test0.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE + shift_bytes)),
            "test1.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE), wanted=False),
            "test2.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE)),
        },
        piece_size=_MIN_PIECE_SIZE,
        before_add=lambda path: (path / "test1.txt").unlink(),
    )
    assert torrent.torf.pieces == 4

    def check_torrent_status():
        assert_torrent_status(
            torrent.transmission.id,
            expect_completed=False,
            expect_pieces=[True, False, False, True],
        )

    check_torrent_status()
    # Should be a no-op because there is no piece that doesn't overlap with a wanted
    # file.
    run_with_torrent(torrent)
    verify_torrent(torrent.transmission.id)
    check_torrent_status()


def test_delete_aligned(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
    verify_torrent,
):
    test0contents = random.randbytes(_MIN_PIECE_SIZE)
    test2contents = random.randbytes(_MIN_PIECE_SIZE)
    torrent = setup_torrent(
        files={
            "test0.txt": TorrentFile(test0contents),
            "test1.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE), wanted=False),
            "test2.txt": TorrentFile(test2contents),
        },
        piece_size=_MIN_PIECE_SIZE,
    )
    assert torrent.torf.pieces == 3
    assert_torrent_status(torrent.transmission.id)
    run_with_torrent(torrent)
    _check_file_tree(
        torrent.path,
        {"test0.txt": test0contents, "test2.txt": test2contents},
    )
    verify_torrent(torrent.transmission.id)
    assert_torrent_status(
        torrent.transmission.id,
        expect_pieces=[True, False, True],
    )


def test_delete_dryrun(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
    verify_torrent,
):
    torrent = setup_torrent(
        files={
            "test0.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE)),
            "test1.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE), wanted=False),
            "test2.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE)),
        },
        piece_size=_MIN_PIECE_SIZE,
    )
    assert torrent.torf.pieces == 3
    assert_torrent_status(torrent.transmission.id)
    run_with_torrent(torrent, "--dry-run")
    verify_torrent(torrent.transmission.id)
    assert_torrent_status(torrent.transmission.id)


def test_delete_aligned_incomplete(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
    verify_torrent,
):
    def corrupt_middle_piece(path):
        with open(path / "test1.txt", "r+b") as file:
            file.seek(_MIN_PIECE_SIZE)
            file.write(b"x" * _MIN_PIECE_SIZE)

    test0contents = random.randbytes(_MIN_PIECE_SIZE)
    test2contents = random.randbytes(_MIN_PIECE_SIZE)
    torrent = setup_torrent(
        files={
            "test0.txt": TorrentFile(test0contents),
            "test1.txt": TorrentFile(
                random.randbytes(_MIN_PIECE_SIZE * 3), wanted=False
            ),
            "test2.txt": TorrentFile(test2contents),
        },
        piece_size=_MIN_PIECE_SIZE,
        before_add=corrupt_middle_piece,
    )
    assert torrent.torf.pieces == 5
    assert_torrent_status(
        torrent.transmission.id,
        expect_pieces=[True, True, False, True, True],
    )
    run_with_torrent(torrent)
    _check_file_tree(
        torrent.path,
        {"test0.txt": test0contents, "test2.txt": test2contents},
    )
    verify_torrent(torrent.transmission.id)
    assert_torrent_status(
        torrent.transmission.id,
        expect_pieces=[True, False, False, False, True],
    )


@pytest.mark.parametrize("shift_bytes", [1, _MIN_PIECE_SIZE // 2, _MIN_PIECE_SIZE - 1])
def test_trim_beginaligned(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
    verify_torrent,
    shift_bytes,
):
    test0contents = random.randbytes(_MIN_PIECE_SIZE + shift_bytes)
    test1contents = random.randbytes(1)
    torrent = setup_torrent(
        files={
            "test0.txt": TorrentFile(test0contents, wanted=False),
            "test1.txt": TorrentFile(test1contents),
        },
        piece_size=_MIN_PIECE_SIZE,
    )
    assert torrent.torf.pieces == 2
    assert_torrent_status(torrent.transmission.id)
    run_with_torrent(torrent)
    _check_file_tree(
        torrent.path,
        {
            "test0.txt.part": b"\x00" * _MIN_PIECE_SIZE + test0contents[-shift_bytes:],
            "test1.txt": test1contents,
        },
    )
    verify_torrent(torrent.transmission.id)
    assert_torrent_status(
        torrent.transmission.id,
        expect_pieces=[False, True],
    )


def test_trim_dryrun(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
    verify_torrent,
):
    torrent = setup_torrent(
        files={
            "test0.txt": TorrentFile(
                random.randbytes(_MIN_PIECE_SIZE + 1), wanted=False
            ),
            "test1.txt": TorrentFile(random.randbytes(1)),
        },
        piece_size=_MIN_PIECE_SIZE,
    )
    assert torrent.torf.pieces == 2
    assert_torrent_status(torrent.transmission.id)
    run_with_torrent(torrent, "--dry-run")
    verify_torrent(torrent.transmission.id)
    assert_torrent_status(torrent.transmission.id)


@pytest.mark.parametrize("shift_bytes", [1, _MIN_PIECE_SIZE // 2, _MIN_PIECE_SIZE - 1])
def test_trim_endaligned(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
    verify_torrent,
    shift_bytes,
):
    test0contents = random.randbytes(_MIN_PIECE_SIZE - shift_bytes)
    test1contents = random.randbytes(_MIN_PIECE_SIZE + shift_bytes)
    torrent = setup_torrent(
        files={
            "test0.txt": TorrentFile(test0contents),
            "test1.txt": TorrentFile(test1contents, wanted=False),
        },
        piece_size=_MIN_PIECE_SIZE,
    )
    assert torrent.torf.pieces == 2
    assert_torrent_status(torrent.transmission.id)
    run_with_torrent(torrent)
    _check_file_tree(
        torrent.path,
        {"test0.txt": test0contents, "test1.txt.part": test1contents[:shift_bytes]},
    )
    verify_torrent(torrent.transmission.id)
    assert_torrent_status(
        torrent.transmission.id,
        expect_pieces=[True, False],
    )


@pytest.mark.parametrize("left_shift_bytes", [1, _MIN_PIECE_SIZE // 2 - 1])
@pytest.mark.parametrize("right_shift_bytes", [1, _MIN_PIECE_SIZE // 2 - 1])
def test_trim_unaligned(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
    verify_torrent,
    left_shift_bytes,
    right_shift_bytes,
):
    test0contents = random.randbytes(_MIN_PIECE_SIZE + left_shift_bytes)
    test1contents = random.randbytes(
        _MIN_PIECE_SIZE * 3 - left_shift_bytes - right_shift_bytes
    )
    test2contents = random.randbytes(_MIN_PIECE_SIZE + right_shift_bytes)
    torrent = setup_torrent(
        files={
            "test0.txt": TorrentFile(test0contents),
            "test1.txt": TorrentFile(test1contents, wanted=False),
            "test2.txt": TorrentFile(test2contents),
        },
        piece_size=_MIN_PIECE_SIZE,
    )
    assert torrent.torf.pieces == 5
    assert_torrent_status(torrent.transmission.id)
    run_with_torrent(torrent)
    _check_file_tree(
        torrent.path,
        {
            "test0.txt": test0contents,
            "test1.txt.part": (
                test1contents[: _MIN_PIECE_SIZE - left_shift_bytes]
                + b"\x00" * _MIN_PIECE_SIZE
                + test1contents[-(_MIN_PIECE_SIZE - right_shift_bytes) :]
            ),
            "test2.txt": test2contents,
        },
    )
    verify_torrent(torrent.transmission.id)
    assert_torrent_status(
        torrent.transmission.id,
        expect_pieces=[True, True, False, True, True],
    )


@pytest.mark.parametrize("left_shift_bytes", [1, _MIN_PIECE_SIZE // 2 - 1])
@pytest.mark.parametrize("right_shift_bytes", [1, _MIN_PIECE_SIZE // 2 - 1])
@pytest.mark.parametrize(
    "incomplete_first_piece,incomplete_last_piece",
    [(True, False), (False, True), (True, True)],
)
def test_trim_unaligned_incomplete(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
    verify_torrent,
    left_shift_bytes,
    right_shift_bytes,
    incomplete_first_piece,
    incomplete_last_piece,
):
    def corrupt_pieces(path):
        with open(path / "test1.txt", "r+b") as file:
            if incomplete_first_piece:
                file.write(b"x" * (_MIN_PIECE_SIZE // 4))
            if incomplete_last_piece:
                file.seek(_MIN_PIECE_SIZE * 2)
                file.write(b"x" * (_MIN_PIECE_SIZE // 4))

    test0contents = random.randbytes(_MIN_PIECE_SIZE + left_shift_bytes)
    test1contents = random.randbytes(
        _MIN_PIECE_SIZE * 3 - left_shift_bytes - right_shift_bytes
    )
    test2contents = random.randbytes(_MIN_PIECE_SIZE + right_shift_bytes)

    torrent = setup_torrent(
        files={
            "test0.txt": TorrentFile(test0contents),
            "test1.txt": TorrentFile(test1contents, wanted=False),
            "test2.txt": TorrentFile(test2contents),
        },
        piece_size=_MIN_PIECE_SIZE,
        before_add=corrupt_pieces,
    )
    assert torrent.torf.pieces == 5
    assert_torrent_status(
        torrent.transmission.id,
        expect_completed=False,
        expect_pieces=[
            True,
            not incomplete_first_piece,
            True,
            not incomplete_last_piece,
            True,
        ],
    )
    run_with_torrent(torrent)
    _check_file_tree(
        torrent.path,
        (
            {"test0.txt": test0contents, "test2.txt": test2contents}
            | (
                # Given the middle piece is unwanted, if both the first piece and the
                # last piece are incomplete, then there are no valid wanted pieces left
                # and the file should be deleted.
                {}
                if incomplete_first_piece and incomplete_last_piece
                else {
                    # Otherwise, we should only find data for the valid, wanted pieces.
                    "test1.txt.part": (
                        b"\x00" * (_MIN_PIECE_SIZE - left_shift_bytes)
                        if incomplete_first_piece
                        else test1contents[: _MIN_PIECE_SIZE - left_shift_bytes]
                    ) + (
                        b""
                        if incomplete_last_piece
                        else (
                            b"\x00" * _MIN_PIECE_SIZE
                            + test1contents[-(_MIN_PIECE_SIZE - right_shift_bytes) :]
                        )
                    )
                }
            )
        ),
    )
    verify_torrent(torrent.transmission.id)
    assert_torrent_status(
        torrent.transmission.id,
        expect_completed=False,
        expect_pieces=[
            True,
            not incomplete_first_piece,
            False,
            not incomplete_last_piece,
            True,
        ],
    )


def test_delete_directory(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
    verify_torrent,
):
    test0contents = random.randbytes(_MIN_PIECE_SIZE)
    test2contents = random.randbytes(_MIN_PIECE_SIZE)
    torrent = setup_torrent(
        files={
            "subdir0/test0.txt": TorrentFile(test0contents),
            "subdir1/test1.txt": TorrentFile(
                random.randbytes(_MIN_PIECE_SIZE), wanted=False
            ),
            "subdir2/test2.txt": TorrentFile(test2contents),
        },
        piece_size=_MIN_PIECE_SIZE,
    )
    assert torrent.torf.pieces == 3
    assert_torrent_status(torrent.transmission.id)
    directory_to_delete = torrent.path / "subdir1"
    assert directory_to_delete.exists()
    run_with_torrent(torrent)
    _check_file_tree(
        torrent.path,
        {"subdir0/test0.txt": test0contents, "subdir2/test2.txt": test2contents},
    )
    assert not directory_to_delete.exists()
    verify_torrent(torrent.transmission.id)
    assert_torrent_status(
        torrent.transmission.id,
        expect_pieces=[True, False, True],
    )


def test_delete_directories(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
    verify_torrent,
):
    test0contents = random.randbytes(_MIN_PIECE_SIZE)
    test2contents = random.randbytes(_MIN_PIECE_SIZE)
    torrent = setup_torrent(
        files={
            "subdir0/subsubdir0/test0.txt": TorrentFile(test0contents),
            "subdir1/subsubdir1/test1.txt": TorrentFile(
                random.randbytes(_MIN_PIECE_SIZE), wanted=False
            ),
            "subdir2/subsubdir2/test2.txt": TorrentFile(test2contents),
        },
        piece_size=_MIN_PIECE_SIZE,
    )
    assert torrent.torf.pieces == 3
    assert_torrent_status(torrent.transmission.id)
    directory_to_delete = torrent.path / "subdir1"
    assert directory_to_delete.exists()
    run_with_torrent(torrent)
    _check_file_tree(
        torrent.path,
        {
            "subdir0/subsubdir0/test0.txt": test0contents,
            "subdir2/subsubdir2/test2.txt": test2contents,
        },
    )
    assert not directory_to_delete.exists()
    verify_torrent(torrent.transmission.id)
    assert_torrent_status(
        torrent.transmission.id,
        expect_pieces=[True, False, True],
    )


def test_delete_part(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
    verify_torrent,
):
    test0contents = random.randbytes(_MIN_PIECE_SIZE)
    test2contents = random.randbytes(_MIN_PIECE_SIZE)
    torrent = setup_torrent(
        files={
            "test0.txt": TorrentFile(test0contents),
            "test1.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE), wanted=False),
            "test2.txt": TorrentFile(test2contents),
        },
        piece_size=_MIN_PIECE_SIZE,
        before_add=lambda path: (path / "test1.txt").rename(path / "test1.txt.part"),
    )
    assert torrent.torf.pieces == 3
    assert_torrent_status(torrent.transmission.id)
    run_with_torrent(torrent)
    _check_file_tree(
        torrent.path,
        {"test0.txt": test0contents, "test2.txt": test2contents},
    )
    verify_torrent(torrent.transmission.id)
    assert_torrent_status(
        torrent.transmission.id,
        expect_pieces=[True, False, True],
    )


def test_verify(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
):
    torrent = setup_torrent(
        files={
            "test0.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE)),
            "test1.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE), wanted=False),
        },
        piece_size=_MIN_PIECE_SIZE,
    )
    assert_torrent_status(torrent.transmission.id)

    def corrupt():
        with open(torrent.path / "test0.txt", "wb") as file:
            file.write(b"x" * _MIN_PIECE_SIZE)

    with pytest.raises(
        transmission_delete_unwanted.delete_unwanted.CorruptTorrentException
    ):
        run_with_torrent(torrent, run_before_check=corrupt)


def test_verify_dryrun(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
):
    torrent = setup_torrent(
        files={
            "test0.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE)),
            "test1.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE), wanted=False),
        },
        piece_size=_MIN_PIECE_SIZE,
    )
    assert_torrent_status(torrent.transmission.id)

    def corrupt():
        with open(torrent.path / "test0.txt", "wb") as file:
            file.write(b"x" * _MIN_PIECE_SIZE)

    run_with_torrent(torrent, "--dry-run", run_before_check=corrupt)

    assert_torrent_status(torrent.transmission.id)


def test_stop(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
    transmission_client,
):
    torrent = setup_torrent(
        files={
            "test0.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE)),
            "test1.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE), wanted=False),
        },
        piece_size=_MIN_PIECE_SIZE,
    )
    assert_torrent_status(torrent.transmission.id)

    def check_stopped():
        assert (
            transmission_client.get_torrent(
                torrent.transmission.id, arguments=["status"]
            ).status
            == transmission_rpc.Status.STOPPED
        )

    run_with_torrent(torrent, run_before_check=check_stopped)
    assert_torrent_status(
        torrent.transmission.id,
        expect_pieces=[True, False],
    )


def test_stop_dryrun(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
    transmission_client,
):
    torrent = setup_torrent(
        files={
            "test0.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE)),
            "test1.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE), wanted=False),
        },
        piece_size=_MIN_PIECE_SIZE,
    )
    assert_torrent_status(torrent.transmission.id)

    def check_not_stopped():
        assert (
            transmission_client.get_torrent(
                torrent.transmission.id, arguments=["status"]
            ).status
            != transmission_rpc.Status.STOPPED
        )

    run_with_torrent(torrent, "--dry-run", run_before_check=check_not_stopped)


@pytest.mark.parametrize(
    "dry_run",
    [False, True],
)
def test_stays_stopped(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
    transmission_client,
    dry_run,
):
    torrent = setup_torrent(
        files={
            "test0.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE)),
            "test1.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE), wanted=False),
        },
        piece_size=_MIN_PIECE_SIZE,
    )
    assert_torrent_status(torrent.transmission.id)

    transmission_client.stop_torrent(torrent.transmission.id)

    def is_stopped():
        return (
            transmission_client.get_torrent(
                torrent.transmission.id, arguments=["status"]
            ).status
            == transmission_rpc.Status.STOPPED
        )

    poll_until(is_stopped)

    def check_stopped():
        assert is_stopped()

    run_with_torrent(
        torrent, *["--dry-run"] if dry_run else [], run_before_check=check_stopped
    )
    check_stopped()


def test_verify_on_error(
    run_with_torrent,
    setup_torrent,
    assert_torrent_status,
    transmission_client,
    verify_torrent,
):
    torrent = setup_torrent(
        files={
            "test0.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE)),
            "test1.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE), wanted=False),
        },
        piece_size=_MIN_PIECE_SIZE,
    )
    assert torrent.torf.pieces == 2
    assert_torrent_status(torrent.transmission.id)

    class TestException(Exception):
        pass

    def raise_test_exception():
        raise TestException()

    with pytest.raises(TestException):
        run_with_torrent(torrent, run_before_check=raise_test_exception)
    verify_torrent(torrent.transmission.id, request=False)
    transmission_info = transmission_client.get_torrent(
        torrent.transmission.id, arguments=["status", "pieces"]
    )
    assert transmission_info.status == transmission_rpc.Status.STOPPED
    # The script should have kicked off verification despite the error, so Transmission
    # should have noticed the piece is gone.
    assert transmission_delete_unwanted.pieces.to_array(
        transmission_info.pieces, piece_count=2
    ) == [True, False]


def test_multiple_torrents(
    run,
    setup_torrent,
    assert_torrent_status,
    verify_torrent,
):
    test00contents = random.randbytes(_MIN_PIECE_SIZE)
    torrent0 = setup_torrent(
        files={
            "test00.txt": TorrentFile(test00contents),
            "test01.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE), wanted=False),
        },
        piece_size=_MIN_PIECE_SIZE,
    )
    test11contents = random.randbytes(_MIN_PIECE_SIZE)
    torrent1 = setup_torrent(
        files={
            "test10.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE), wanted=False),
            "test11.txt": TorrentFile(test11contents),
        },
        piece_size=_MIN_PIECE_SIZE,
    )
    test20contents = random.randbytes(_MIN_PIECE_SIZE)
    test21contents = random.randbytes(_MIN_PIECE_SIZE)
    torrent2 = setup_torrent(
        files={
            "test20.txt": TorrentFile(test20contents),
            "test21.txt": TorrentFile(test21contents, wanted=False),
        },
        piece_size=_MIN_PIECE_SIZE,
    )
    assert_torrent_status(torrent0.transmission.id)
    assert_torrent_status(torrent1.transmission.id)
    assert_torrent_status(torrent2.transmission.id)
    run(
        "--torrent-id",
        str(torrent0.transmission.id),
        "--torrent-id",
        str(torrent1.transmission.id),
    )
    _check_file_tree(
        torrent0.path,
        {"test00.txt": test00contents},
    )
    _check_file_tree(
        torrent1.path,
        {"test11.txt": test11contents},
    )
    _check_file_tree(
        torrent2.path,
        {"test20.txt": test20contents, "test21.txt": test21contents},
    )
    verify_torrent(torrent0.transmission.id)
    verify_torrent(torrent1.transmission.id)
    verify_torrent(torrent2.transmission.id)


def test_all_torrents(
    run,
    setup_torrent,
    assert_torrent_status,
    verify_torrent,
):
    test00contents = random.randbytes(_MIN_PIECE_SIZE)
    torrent0 = setup_torrent(
        files={
            "test00.txt": TorrentFile(test00contents),
            "test01.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE), wanted=False),
        },
        piece_size=_MIN_PIECE_SIZE,
    )
    test11contents = random.randbytes(_MIN_PIECE_SIZE)
    torrent1 = setup_torrent(
        files={
            "test10.txt": TorrentFile(random.randbytes(_MIN_PIECE_SIZE), wanted=False),
            "test11.txt": TorrentFile(test11contents),
        },
        piece_size=_MIN_PIECE_SIZE,
    )
    test20contents = random.randbytes(_MIN_PIECE_SIZE)
    test21contents = random.randbytes(_MIN_PIECE_SIZE)
    torrent2 = setup_torrent(
        files={
            "test20.txt": TorrentFile(test20contents),
            "test21.txt": TorrentFile(test21contents),
        },
        piece_size=_MIN_PIECE_SIZE,
    )
    assert_torrent_status(torrent0.transmission.id)
    assert_torrent_status(torrent1.transmission.id)
    assert_torrent_status(torrent2.transmission.id)
    run()
    _check_file_tree(
        torrent0.path,
        {"test00.txt": test00contents},
    )
    _check_file_tree(
        torrent1.path,
        {"test11.txt": test11contents},
    )
    _check_file_tree(
        torrent2.path,
        {"test20.txt": test20contents, "test21.txt": test21contents},
    )
    verify_torrent(torrent0.transmission.id)
    verify_torrent(torrent1.transmission.id)
    verify_torrent(torrent2.transmission.id)
