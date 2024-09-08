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


class _TorrentProcessor:
    def __init__(
        self,
        transmission_client,
        torrent_id,
        download_dir,
        run_before_check,
        transmission_url,
        dry_run,
    ):
        self._transmission_client = transmission_client
        self._download_dir = download_dir
        self._transmission_url = transmission_url
        self._dry_run = dry_run

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
        self._torrent_id = torrent.id
        self._piece_size = torrent.piece_size
        self._initially_stopped = torrent.status == transmission_rpc.Status.STOPPED
        print(
            f'>>> PROCESSING TORRENT: "{torrent.name}" (hash: {torrent.info_hash} id:'
            f" {self._torrent_id})"
        )

        total_piece_count = torrent.piece_count
        self._pieces_wanted = pieces.pieces_wanted_from_files(
            # Note we use torrent.fields["files"], not torrent.get_files(), to work around
            # https://github.com/trim21/transmission-rpc/issues/455
            [file["length"] for file in torrent.fields["files"]],
            torrent.wanted,
            torrent.piece_size,
        )
        assert len(self._pieces_wanted) == total_piece_count
        pieces_present = pieces.to_array(torrent.pieces, total_piece_count)
        assert len(pieces_present) == total_piece_count

        pieces_wanted_present = list(
            zip(
                self._pieces_wanted,
                pieces_present,
                strict=True,
            )
        )
        self._pieces_present_wanted = [
            present and wanted for wanted, present in pieces_wanted_present
        ]
        self._pieces_present_unwanted = [
            present and not wanted for wanted, present in pieces_wanted_present
        ]

        pieces_present_unwanted_count = self._pieces_present_unwanted.count(True)
        print(
            f"Wanted: {self._format_piece_count(self._pieces_wanted.count(True))};"
            f" present: {self._format_piece_count(pieces_present.count(True))}; present"
            " and wanted:"
            f" {self._format_piece_count(self._pieces_present_wanted.count(True))};"
            " present and not wanted:"
            f" {self._format_piece_count(pieces_present_unwanted_count)}"
        )

        if pieces_present_unwanted_count == 0:
            print("Every downloaded piece is wanted. Nothing to do.")
            return

        self._stop_torrent()

        try:
            current_offset = 0
            for torrent_file, file_wanted in zip(
                torrent.fields["files"], torrent.wanted
            ):
                file_length = torrent_file["length"]
                self._process_file(
                    torrent_file["name"], file_length, current_offset, file_wanted
                )
                current_offset += file_length

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
            self._check_torrent()
            if not self._initially_stopped:
                transmission_client.start_torrent(self._torrent_id)

    def _stop_torrent(self):
        if self._initially_stopped or self._dry_run:
            return

        # Stop the torrent before we make any changes. We don't want to risk
        # Transmission serving deleted pieces that it thinks are still there. It is only
        # safe to resume the torrent after a completed verification (hash check).
        self._transmission_client.stop_torrent(self._torrent_id)
        # Transmission does not stop torrents synchronously, so wait for the torrent to
        # transition to the stopped state. Hopefully Transmission will not attempt to
        # read from the torrent files after that point.
        self._wait_for_status(lambda status: status == transmission_rpc.Status.STOPPED)

    def _process_file(self, file_name, file_length, current_offset, file_wanted):
        begin_piece = current_offset // self._piece_size
        end_piece = -(-(current_offset + file_length) // self._piece_size)
        next_offset = current_offset + file_length

        if not any(self._pieces_present_unwanted[begin_piece:end_piece]):
            return
        assert not file_wanted

        if any(self._pieces_present_wanted[begin_piece:end_piece]):
            # The file is not wanted, but it contains valid pieces that are wanted.
            # In practice this means the file contains pieces that overlap with
            # wanted, adjacent files. We can't get rid of the file without
            # corrupting these pieces; best we can do is turn it into a partial
            # file.

            # Sanity check that the wanted pieces are where we expect them to be.
            assert (
                current_offset % self._piece_size != 0
                or not self._pieces_wanted[begin_piece]
            )
            assert (
                next_offset % self._piece_size != 0
                or not self._pieces_wanted[end_piece - 1]
            )
            assert not any(self._pieces_wanted[begin_piece + 1 : end_piece - 1])

            keep_first_bytes = (
                (begin_piece + 1) * self._piece_size - current_offset
                if self._pieces_present_wanted[begin_piece]
                else 0
            )
            assert 0 <= keep_first_bytes < self._piece_size
            keep_last_bytes = (
                self._piece_size
                - (end_piece * self._piece_size - current_offset - file_length)
                if self._pieces_present_wanted[end_piece - 1]
                else self._piece_size
            )
            assert 0 < keep_last_bytes <= self._piece_size
            keep_last_bytes %= self._piece_size
            assert keep_first_bytes > 0 or keep_last_bytes > 0
            assert (keep_first_bytes + keep_last_bytes) < file_length
            _trim_torrent_file(
                self._download_dir,
                file_name,
                keep_first_bytes=keep_first_bytes,
                keep_last_bytes=keep_last_bytes,
                dry_run=self._dry_run,
            )
        else:
            # The file does not contain any data from wanted, valid pieces; we can
            # safely get rid of it.
            _remove_torrent_file(self._download_dir, file_name, dry_run=self._dry_run)

    def _check_torrent(self):
        print("All done, kicking off torrent verification. This may take a while...")
        self._transmission_client.verify_torrent(self._torrent_id)
        status = self._wait_for_status(
            lambda status: status
            not in (
                transmission_rpc.Status.CHECKING,
                transmission_rpc.Status.CHECK_PENDING,
            ),
        )
        assert status == transmission_rpc.Status.STOPPED
        torrent = self._transmission_client.get_torrent(
            self._torrent_id, arguments=["pieces"]
        )
        lost_pieces_count = sum(
            piece_present_wanted_previously and not piece_present_now
            for piece_present_wanted_previously, piece_present_now in zip(
                self._pieces_present_wanted,
                pieces.to_array(torrent.pieces, len(self._pieces_present_wanted)),
                strict=True,
            )
        )
        if lost_pieces_count > 0:
            raise CorruptTorrentException(
                "Oh no, looks like we corrupted"
                f" {self._format_piece_count(lost_pieces_count)} that were previously"
                " valid and wanted :( This should never happen, please report this as"
                " a bug (make sure to attach the output of `transmission-remote"
                f" {self._transmission_url} --torrent {self._torrent_id} --info"
                " --info-files --info-pieces`)"
            )
        print("Torrent verification successful.")

    @backoff.on_predicate(
        backoff.expo,
        lambda status: status is None,
        factor=0.050,
        max_value=1.0,
    )
    def _wait_for_status(self, status_predicate):
        status = self._transmission_client.get_torrent(
            self._torrent_id, arguments=["status"]
        ).status
        return status if status_predicate(status) else None

    def _format_piece_count(self, piece_count):
        return f"{piece_count} pieces" + (
            ""
            if piece_count == 0
            else (
                f" ({humanize.naturalsize(piece_count * self._piece_size, binary=True)})"
            )
        )


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
            _TorrentProcessor(
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
