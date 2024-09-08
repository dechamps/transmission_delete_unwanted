import argparse
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


def run(args):
    args = _parse_arguments(args)
    transmission_url = args.transmission_url
    with transmission_rpc.from_url(transmission_url) as transmission_client:
        pass


def main():
    run(args=None)
