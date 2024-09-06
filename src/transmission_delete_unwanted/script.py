import argparse
import humanize
import pathlib
import transmission_rpc
from transmission_delete_unwanted import pieces


def _parse_arguments(args=None):
    argument_parser = argparse.ArgumentParser(
        description="Deletes unwanted files from a Transmission torrent.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    argument_parser.add_argument(
        "--transmission-url",
        help=(
            "Transmission URL, e.g."
            " http+unix://%2Frun%2Ftransmission%2Fsandbox%2Fsocket/transmission/rpc"
        ),
        required=False,
        default=argparse.SUPPRESS,
    )
    argument_parser.add_argument(
        "--torrent-id",
        help="ID (or hash) of the torrent to delete unwanted files from",
        required=True,
        default=argparse.SUPPRESS,
    )
    return argument_parser.parse_args(args)


def _is_dir_empty(path):
    for _ in path.iterdir():
        return False
    return True


def _remove_torrent_file(download_dir, file_name):
    removed = False

    file_path = download_dir / file_name
    if file_path.exists():
        print(f"Removing: {file_name}")
        file_path.unlink()
        removed = True

    # Note: in the very unlikely scenario that a torrent contains a file named
    # "xxx" *and* another file named "xxx.part", this may end up deleting the
    # wrong file. For now we just accept the risk.
    part_file_name = f"{file_name}.part"
    part_file_path = download_dir / part_file_name
    if part_file_path.exists():
        print(f"Removing: {part_file_name}")
        part_file_path.unlink()
        removed = True

    if not removed:
        print(f"WARNING: could not find {file_name} to delete")
        return

    parent_dir = file_path.parent
    while _is_dir_empty(parent_dir):
        parent_dir.rmdir()
        parent_dir = parent_dir.parent


def _turn_torrent_file_into_partial(
    download_dir, file_name, keep_first_bytes, keep_last_bytes
):
    print(f"Turning into partial: {file_name}")

    # Note: on some operating systems there are ways to do this in-place without any
    # copies ("hole punching"), e.g. fallocate(FALLOC_FL_PUNCH_HOLE) on Linux. This
    # doesn't seem to be worth the extra complexity though, given the amount of data
    # being copied should be relatively small.
    original_file_path = download_dir / file_name
    part_file_path = download_dir / f"{file_name}.part"
    new_file_path = download_dir / f"{file_name}.transmission-delete-unwanted-tmp"
    try:
        with open(
            original_file_path if original_file_path.exists() else part_file_path, "rb"
        ) as original_file, open(new_file_path, "wb") as new_file:
            # TODO: this could potentially load an unbounded amount of data in memory,
            # especially if the torrent is using a large piece size. We should break the
            # copy operation down into small buffers. Even better would be to use an
            # optimized function such as `os.copy_file_range()` or `os.sendfile()` but
            # these are sadly platform-dependent.
            if keep_first_bytes > 0:
                new_file.write(original_file.read(keep_first_bytes))
            if keep_last_bytes > 0:
                original_file.seek(
                    -keep_last_bytes,
                    2,  # Seek from the end
                )
                new_file.seek(original_file.tell())
                new_file.write(original_file.read(keep_last_bytes))

        new_file_path.replace(part_file_path)
        original_file_path.unlink(missing_ok=True)
    finally:
        new_file_path.unlink(missing_ok=True)


def _process_torrent(transmission_client, torrent_id, download_dir):
    torrent = transmission_client.get_torrent(
        torrent_id,
        arguments=[
            "id",
            "infohash",
            "name",
            "files",
            "pieces",
            "pieceCount",
            "pieceSize",
            "wanted",
        ],
    )
    print(
        f'>>> PROCESSING TORRENT: "{torrent.name}" (hash: {torrent.info_hash} id:'
        f" {torrent.id})"
    )

    pieces_wanted = [None] * torrent.piece_count
    # Note we use torrent.fields["files"], not torrent.get_files(), to work around
    # https://github.com/trim21/transmission-rpc/issues/455
    current_offset = 0
    for file, file_wanted in zip(torrent.fields["files"], torrent.wanted):
        assert file_wanted == 0 or file_wanted == 1
        file_length = file["length"]
        # Compute piece boundaries. Note we can't use file["beginPiece"] and
        # file["endPiece"] for this because these are new fields that the
        # Transmission server may be too old to support.
        for piece_index in range(
            current_offset // torrent.piece_size,
            -(-(current_offset + file_length) // torrent.piece_size),
        ):
            # The value for that piece may already have been set by the previous
            # file, due to unaligned piece/file boundaries. In this case, a piece
            # is wanted if it overlaps with any wanted file.
            pieces_wanted[piece_index] = pieces_wanted[piece_index] or file_wanted
        current_offset += file_length
    assert all(wanted_piece is not None for wanted_piece in pieces_wanted)

    pieces_present = pieces.to_array(torrent.pieces, torrent.piece_count)
    pieces_present_unwanted = [
        present and not wanted
        for wanted, present in zip(
            pieces_wanted,
            pieces_present,
            strict=True,
        )
    ]

    piece_size = torrent.piece_size

    def _format_piece_count(piece_count):
        return f"{piece_count} pieces" + (
            ""
            if piece_count == 0
            else f" ({humanize.naturalsize(piece_count * piece_size, binary=True)})"
        )

    pieces_present_unwanted_count = pieces_present_unwanted.count(True)
    print(
        f"Wanted: {_format_piece_count(pieces_wanted.count(True))}; present:"
        f" {_format_piece_count(pieces_present.count(True))}; present and not wanted:"
        f" {_format_piece_count(pieces_present_unwanted_count)}"
    )

    if pieces_present_unwanted_count == 0:
        print("Every downloaded piece is wanted. Nothing to do.")
        return

    current_offset = 0
    for file, file_wanted in zip(torrent.fields["files"], torrent.wanted):
        file_length = file["length"]
        begin_piece = current_offset // piece_size
        end_piece = -(-(current_offset + file_length) // piece_size)
        next_offset = current_offset + file_length

        if any(pieces_present_unwanted[begin_piece:end_piece]):
            assert not file_wanted
            if any(pieces_wanted[begin_piece:end_piece]):
                # The file contains pieces that overlap with wanted, adjacent files. We
                # can't get rid of the file without corrupting these pieces; best we can
                # do is turn it into a partial file.

                # Sanity check that the wanted pieces are where we expect them to be.
                assert (
                    current_offset % piece_size != 0 or not pieces_wanted[begin_piece]
                )
                assert next_offset % piece_size != 0 or not pieces_wanted[end_piece - 1]
                assert not any(pieces_wanted[begin_piece + 1 : end_piece - 1])

                keep_first_bytes = (
                    (begin_piece + 1) * piece_size - current_offset
                    if pieces_wanted[begin_piece]
                    else 0
                )
                assert 0 <= keep_first_bytes < piece_size
                keep_last_bytes = (
                    piece_size - (end_piece * piece_size - next_offset)
                    if pieces_wanted[end_piece - 1]
                    else piece_size
                )
                assert 0 < keep_last_bytes <= piece_size
                keep_last_bytes %= piece_size
                assert keep_first_bytes > 0 or keep_last_bytes > 0
                assert (keep_first_bytes + keep_last_bytes) < file_length
                _turn_torrent_file_into_partial(
                    download_dir,
                    file["name"],
                    keep_first_bytes=keep_first_bytes,
                    keep_last_bytes=keep_last_bytes,
                )
            else:
                # The file does not contain any data from wanted pieces; we can safely
                # get rid of it.
                _remove_torrent_file(download_dir, file["name"])

        current_offset = next_offset


def main(args=None):
    args = _parse_arguments(args)
    with transmission_rpc.from_url(args.transmission_url) as transmission_client:
        download_dir = pathlib.Path(transmission_client.get_session().download_dir)
        torrent_id = args.torrent_id
        _process_torrent(
            transmission_client=transmission_client,
            torrent_id=torrent_id if len(torrent_id) == 40 else int(torrent_id),
            download_dir=download_dir,
        )
