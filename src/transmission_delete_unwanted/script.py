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
    for child in path.iterdir():
        return False
    return True


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
        begin_piece = current_offset // torrent.piece_size
        end_piece = -(-(current_offset + file_length) // torrent.piece_size)

        if any(pieces_present_unwanted[begin_piece:end_piece]):
            assert not file_wanted
            # TODO: support unaligned files
            assert all(pieces_present_unwanted[begin_piece:end_piece])

            # TODO: handle the case where the file has a .part suffix
            file_name = file["name"]
            print(f"Removing: {file_name}")
            file_path = download_dir / file_name
            parent_dir = file_path.parent
            file_path.unlink()
            if _is_dir_empty(parent_dir):
                parent_dir.rmdir()

        current_offset += file_length


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
