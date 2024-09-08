import argparse
import pathlib
import sys
import backoff
import humanize
import transmission_rpc
from transmission_delete_unwanted import file, pieces


def _parse_arguments(args):
    argument_parser = argparse.ArgumentParser(
        description="Deletes/trims unwanted files from a Transmission torrent.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    argument_parser.add_argument(
        "--transmission-url",
        help="URL of the Transmission instance to connect to",
        default="http://127.0.0.1:9091",
    )
    argument_parser.add_argument(
        "--torrent-id",
        help=(
            "ID (or hash) of the torrent to delete unwanted files from; can be"
            " specified multiple times (default: all torrents)"
        ),
        action="append",
        default=argparse.SUPPRESS,
    )
    argument_parser.add_argument(
        "--dry-run",
        help=(
            "Do not touch anything or make any changes; instead, just state what would"
            " have been done"
        ),
        action="store_true",
        default=argparse.SUPPRESS,
    )
    return argument_parser.parse_args(args)


def format_piece_count(piece_count, piece_size):
    return f"{piece_count} pieces" + (
        ""
        if piece_count == 0
        else f" ({humanize.naturalsize(piece_count * piece_size, binary=True)})"
    )


@backoff.on_predicate(
    backoff.expo,
    lambda status: status is None,
    factor=0.050,
    max_value=1.0,
)
def _wait_for_torrent_status(transmission_client, torrent_id, status_predicate):
    status = transmission_client.get_torrent(torrent_id, arguments=["status"]).status
    return status if status_predicate(status) else None


def _is_dir_empty(path):
    for _ in path.iterdir():
        return False
    return True


def _remove_torrent_file(download_dir, file_name, dry_run):
    def delete(file_name_to_delete):
        file_path = download_dir / file_name_to_delete
        if not file_path.exists():
            return False
        print(
            f"{'Would have removed' if dry_run else 'Removing'}: {file_name_to_delete}"
        )
        if not dry_run:
            file_path.unlink()
        return True

    # Note: in the very unlikely scenario that a torrent contains a file named
    # "xxx" *and* another file named "xxx.part", this may end up deleting the
    # wrong file. For now we just accept the risk.
    if not any([delete(file_name), delete(f"{file_name}.part")]):
        print(f"WARNING: could not find {file_name} to delete")
        return

    if not dry_run:
        parent_dir = (download_dir / file_name).parent
        while _is_dir_empty(parent_dir):
            parent_dir.rmdir()
            parent_dir = parent_dir.parent


def _trim_torrent_file(
    download_dir, file_name, keep_first_bytes, keep_last_bytes, dry_run
):
    print(f"{'Would have trimmed' if dry_run else 'Trimming'}: {file_name}")
    if dry_run:
        return

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
            if keep_first_bytes > 0:
                file.copy(original_file, new_file, keep_first_bytes)
            if keep_last_bytes > 0:
                original_file.seek(
                    -keep_last_bytes,
                    2,  # Seek from the end
                )
                new_file.seek(original_file.tell())
                file.copy(original_file, new_file, keep_last_bytes)

        new_file_path.replace(part_file_path)
        original_file_path.unlink(missing_ok=True)
    finally:
        new_file_path.unlink(missing_ok=True)


class ScriptException(Exception):
    pass


class CorruptTorrentException(ScriptException):
    pass


def _check_torrent(
    transmission_client,
    torrent_id,
    pieces_present_wanted_previously,
    piece_size,
    transmission_url,
):
    print("All done, kicking off torrent verification. This may take a while...")
    transmission_client.verify_torrent(torrent_id)
    status = _wait_for_torrent_status(
        transmission_client,
        torrent_id,
        lambda status: status
        not in (
            transmission_rpc.Status.CHECKING,
            transmission_rpc.Status.CHECK_PENDING,
        ),
    )
    assert status == transmission_rpc.Status.STOPPED
    torrent = transmission_client.get_torrent(torrent_id, arguments=["pieces"])
    lost_pieces_count = sum(
        piece_present_wanted_previously and not piece_present_now
        for piece_present_wanted_previously, piece_present_now in zip(
            pieces_present_wanted_previously,
            pieces.to_array(torrent.pieces, len(pieces_present_wanted_previously)),
            strict=True,
        )
    )
    if lost_pieces_count > 0:
        raise CorruptTorrentException(
            "Oh no, looks like we corrupted"
            f" {format_piece_count(lost_pieces_count, piece_size)} that were previously"
            " valid and wanted :( This should never happen, please report this as a"
            " bug (make sure to attach the output of `transmission-remote"
            f" {transmission_url} --torrent {torrent.id} --info --info-files"
            " --info-pieces`)"
        )
    print("Torrent verification successful.")


def _process_torrent(
    transmission_client,
    torrent_id,
    download_dir,
    run_before_check,
    transmission_url,
    dry_run,
):
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
            "status",
        ],
    )
    torrent_id = torrent.id
    print(
        f'>>> PROCESSING TORRENT: "{torrent.name}" (hash: {torrent.info_hash} id:'
        f" {torrent_id})"
    )

    total_piece_count = torrent.piece_count
    pieces_wanted = pieces.pieces_wanted_from_files(
        # Note we use torrent.fields["files"], not torrent.get_files(), to work around
        # https://github.com/trim21/transmission-rpc/issues/455
        [file["length"] for file in torrent.fields["files"]],
        torrent.wanted,
        torrent.piece_size,
    )
    assert len(pieces_wanted) == total_piece_count
    pieces_present = pieces.to_array(torrent.pieces, total_piece_count)
    assert len(pieces_present) == total_piece_count

    pieces_wanted_present = list(
        zip(
            pieces_wanted,
            pieces_present,
            strict=True,
        )
    )
    pieces_present_wanted = [
        present and wanted for wanted, present in pieces_wanted_present
    ]
    pieces_present_unwanted = [
        present and not wanted for wanted, present in pieces_wanted_present
    ]

    piece_size = torrent.piece_size

    def _format_piece_count(piece_count):
        return format_piece_count(piece_count, piece_size)

    pieces_present_unwanted_count = pieces_present_unwanted.count(True)
    print(
        f"Wanted: {_format_piece_count(pieces_wanted.count(True))}; present:"
        f" {_format_piece_count(pieces_present.count(True))}; present and wanted:"
        f" {_format_piece_count(pieces_present_wanted.count(True))}; present and not"
        f" wanted: {_format_piece_count(pieces_present_unwanted_count)}"
    )

    if pieces_present_unwanted_count == 0:
        print("Every downloaded piece is wanted. Nothing to do.")
        return

    initially_stopped = torrent.status == transmission_rpc.Status.STOPPED
    if not initially_stopped and not dry_run:
        # Stop the torrent before we make any changes. We don't want to risk
        # Transmission serving deleted pieces that it thinks are still there. It is only
        # safe to resume the torrent after a completed verification (hash check).
        transmission_client.stop_torrent(torrent_id)
        # Transmission does not stop torrents synchronously, so wait for the torrent to
        # transition to the stopped state. Hopefully Transmission will not attempt to
        # read from the torrent files after that point.
        _wait_for_torrent_status(
            transmission_client,
            torrent_id,
            lambda status: status == transmission_rpc.Status.STOPPED,
        )

    try:
        current_offset = 0
        for file, file_wanted in zip(torrent.fields["files"], torrent.wanted):
            file_length = file["length"]
            begin_piece = current_offset // piece_size
            end_piece = -(-(current_offset + file_length) // piece_size)
            next_offset = current_offset + file_length

            if any(pieces_present_unwanted[begin_piece:end_piece]):
                assert not file_wanted
                if any(pieces_present_wanted[begin_piece:end_piece]):
                    # The file is not wanted, but it contains valid pieces that are wanted.
                    # In practice this means the file contains pieces that overlap with
                    # wanted, adjacent files. We can't get rid of the file without
                    # corrupting these pieces; best we can do is turn it into a partial
                    # file.

                    # Sanity check that the wanted pieces are where we expect them to be.
                    assert (
                        current_offset % piece_size != 0
                        or not pieces_wanted[begin_piece]
                    )
                    assert (
                        next_offset % piece_size != 0
                        or not pieces_wanted[end_piece - 1]
                    )
                    assert not any(pieces_wanted[begin_piece + 1 : end_piece - 1])

                    keep_first_bytes = (
                        (begin_piece + 1) * piece_size - current_offset
                        if pieces_present_wanted[begin_piece]
                        else 0
                    )
                    assert 0 <= keep_first_bytes < piece_size
                    keep_last_bytes = (
                        piece_size - (end_piece * piece_size - next_offset)
                        if pieces_present_wanted[end_piece - 1]
                        else piece_size
                    )
                    assert 0 < keep_last_bytes <= piece_size
                    keep_last_bytes %= piece_size
                    assert keep_first_bytes > 0 or keep_last_bytes > 0
                    assert (keep_first_bytes + keep_last_bytes) < file_length
                    _trim_torrent_file(
                        download_dir,
                        file["name"],
                        keep_first_bytes=keep_first_bytes,
                        keep_last_bytes=keep_last_bytes,
                        dry_run=dry_run,
                    )
                else:
                    # The file does not contain any data from wanted, valid pieces; we can
                    # safely get rid of it.
                    _remove_torrent_file(download_dir, file["name"], dry_run=dry_run)

            current_offset = next_offset

        run_before_check()
    except:
        # If we are interrupted while touching torrent data, before we bail at least try
        # to kick off a verification so that Transmission is aware that data may have
        # changed. Otherwise the risk is the user may just resume the torrent and start
        # serving corrupt pieces.
        if not dry_run:
            transmission_client.verify_torrent(torrent_id)
        raise

    if not dry_run:
        _check_torrent(
            transmission_client=transmission_client,
            torrent_id=torrent_id,
            pieces_present_wanted_previously=pieces_present_wanted,
            piece_size=piece_size,
            transmission_url=transmission_url,
        )
        if not initially_stopped:
            transmission_client.start_torrent(torrent_id)


def run(args, run_before_check=lambda: None):
    args = _parse_arguments(args)
    transmission_url = args.transmission_url
    with transmission_rpc.from_url(transmission_url) as transmission_client:
        download_dir = pathlib.Path(transmission_client.get_session().download_dir)

        torrent_ids = getattr(args, "torrent_id", [])
        for torrent_id in (
            (
                torrent_info.id
                for torrent_info in transmission_client.get_torrents(arguments=["id"])
            )
            if len(torrent_ids) == 0
            else (
                torrent_id if len(torrent_id) == 40 else int(torrent_id)
                for torrent_id in torrent_ids
            )
        ):
            _process_torrent(
                transmission_client=transmission_client,
                torrent_id=torrent_id,
                download_dir=download_dir,
                run_before_check=run_before_check,
                transmission_url=transmission_url,
                dry_run=getattr(args, "dry_run", False),
            )


def main():
    try:
        run(args=None)
    except ScriptException as script_exception:
        print(f"FATAL ERROR: {script_exception.args[0]}", file=sys.stderr)
        return 1
    return 0
