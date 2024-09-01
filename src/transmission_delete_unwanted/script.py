import argparse
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


def main(args=None):
    args = _parse_arguments(args)
    with transmission_rpc.from_url(args.transmission_url) as transmission_client:
        torrent_id = args.torrent_id
        torrent = transmission_client.get_torrent(
            torrent_id if len(torrent_id) == 40 else int(torrent_id),
            arguments=[
                "files",
                "pieces",
                "pieceCount",
                "pieceSize",
                "wanted",
            ],
        )

        wanted_pieces = [None] * torrent.piece_count
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
                wanted_pieces[piece_index] = wanted_pieces[piece_index] or file_wanted
            current_offset += file_length
        print(wanted_pieces)
        assert all(wanted_piece is not None for wanted_piece in wanted_pieces)

        # Actual functionality not implemented yet; for now, just fail if anything needs
        # to be done
        assert wanted_pieces == pieces.to_array(torrent.pieces, torrent.piece_count)
