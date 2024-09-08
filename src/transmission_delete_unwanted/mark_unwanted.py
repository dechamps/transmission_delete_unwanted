import argparse
import sys
import transmission_rpc


def _parse_arguments(args):
    argument_parser = argparse.ArgumentParser(
        description=(
            "Given a list of file paths (one per line, relative to download_dir) on"
            " standard input, mark the files as unwanted (do not download) in the"
            " corresponding Transmission torrent."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    argument_parser.add_argument(
        "--transmission-url",
        help="URL of the Transmission instance to connect to",
        default="http://127.0.0.1:9091",
    )
    return argument_parser.parse_args(args)


def _mark_unwanted(transmission_client):
    torrents = transmission_client.get_torrents(arguments=["id", "name", "files"])
    # Note we use torrent.fields["files"], not torrent.get_files(), to work around
    # https://github.com/trim21/transmission-rpc/issues/455
    #
    # TODO: this could be made more memory-efficient by using two levels of nested
    # dicts.
    torrent_id_and_file_id_by_file_name = {
        file["name"]: (torrent.id, file_id)
        for torrent in torrents
        for file_id, file in enumerate(torrent.fields["files"])
    }

    unwanted_file_ids_by_torrent_id = {}
    for file_name in (line.rstrip("\r\n") for line in sys.stdin):
        if len(file_name) == 0:
            continue
        torrent_id, file_id = torrent_id_and_file_id_by_file_name[file_name]
        unwanted_file_ids_by_torrent_id.setdefault(torrent_id, []).append(file_id)

    for torrent_id, unwanted_file_ids in unwanted_file_ids_by_torrent_id.items():
        transmission_client.change_torrent(torrent_id, files_unwanted=unwanted_file_ids)


def run(args):
    args = _parse_arguments(args)
    transmission_url = args.transmission_url
    with transmission_rpc.from_url(transmission_url) as transmission_client:
        _mark_unwanted(transmission_client)


def main():
    run(args=None)
