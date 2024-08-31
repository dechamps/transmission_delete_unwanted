import argparse
import transmission_rpc


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
        print(transmission_client.get_torrent(args.torrent_id).fields)
