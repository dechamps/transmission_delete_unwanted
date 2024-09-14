# Delete files from Transmission torrents

[![Continuous Integration](https://github.com/dechamps/transmission_delete_unwanted/actions/workflows/continuous-integration.yml/badge.svg)](https://github.com/dechamps/transmission_delete_unwanted/actions/)
[![PyPI version](https://badge.fury.io/py/transmission-delete-unwanted.svg)](https://pypi.org/project/transmission-delete-unwanted/)
[![Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![pylint](https://img.shields.io/badge/linting-pylint-yellowgreen)](https://github.com/pylint-dev/pylint)
[![SLSA level 3](https://img.shields.io/badge/SLSA-level%203-green?logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAA4AAAAOCAMAAAAolt3jAAAABGdBTUEAALGPC/xhBQAAACBjSFJNAAB6JgAAgIQAAPoAAACA6AAAdTAAAOpgAAA6mAAAF3CculE8AAABMlBMVEXvMQDvMADwMQDwMADwMADvMADvMADwMADwMQDvMQDvMQDwMADwMADvMADwMADwMADwMQDvMQDvMQDwMQDvMQDwMQDwMADwMADwMQDwMADwMADvMADvMQDvMQDwMADwMQDwMADvMQDwMADwMQDwMADwMADwMADwMADwMADwMADvMQDvMQDwMADwMQDwMADvMQDvMQDwMADvMQDvMQDwMADwMQDwMQDwMQDvMQDwMADvMADwMADwMQDvMQDwMADwMQDwMQDwMQDwMQDvMQDvMQDvMADwMADvMADvMADvMADwMQDwMQDvMADvMQDvMQDvMADvMADvMQDwMQDvMQDvMADvMADvMADvMQDwMQDvMQDvMQDvMADvMADwMADvMQDvMQDvMQDvMADwMADwMQDwMAAAAAA/HoSwAAAAY3RSTlMpsvneQlQrU/LQSWzvM5DzmzeF9Pi+N6vvrk9HuP3asTaPgkVFmO3rUrMjqvL6d0LLTVjI/PuMQNSGOWa/6YU8zNuDLihJ0e6aMGzl8s2IT7b6lIFkRj1mtvQ0eJW95rG0+Sid59x/AAAAAWJLR0Rltd2InwAAAAlwSFlzAAAOwwAADsMBx2+oZAAAAAd0SU1FB+YHGg0tGLrTaD4AAACqSURBVAjXY2BgZEqGAGYWVjYGdg4oj5OLm4eRgZcvBcThFxAUEk4WYRAVE09OlpCUkpaRTU6WY0iWV1BUUlZRVQMqUddgSE7W1NLS1gFp0NXTB3KTDQyNjE2Sk03NzC1A3GR1SytrG1s7e4dkBogtjk7OLq5uyTCuu4enl3cyhOvj66fvHxAIEmYICg4JDQuPiAQrEmGIio6JjZOFOjSegSHBBMpOToxPAgCJfDZC/m2KHgAAACV0RVh0ZGF0ZTpjcmVhdGUAMjAyMi0wNy0yNlQxMzo0NToyNCswMDowMC8AywoAAAAldEVYdGRhdGU6bW9kaWZ5ADIwMjItMDctMjZUMTM6NDU6MjQrMDA6MDBeXXO2AAAAGXRFWHRTb2Z0d2FyZQB3d3cuaW5rc2NhcGUub3Jnm+48GgAAAABJRU5ErkJggg==)](https://slsa.dev/spec/v1.0/levels#build-l3)

`transmission-delete-unwanted` is a tool that makes it possible to delete
specific files from [Transmission][] torrents _after they have been downloaded_,
with correct handling of edge cases such as overlapping pieces.

```text
$ transmission-delete-unwanted --torrent-id 88825ccd2812867852a405409313c5aeb6e9b7dc
>>> PROCESSING TORRENT: "Linux ISOs" (hash: 88825ccd2812867852a405409313c5aeb6e9b7dc id: 42)
Wanted: 3224 pieces (25.2 GiB); present: 13266 pieces (103.6 GiB); present and wanted: 3224 pieces (25.2 GiB); present and not wanted: 10042 pieces (78.5 GiB)
Trimming: Linux ISOs/Debian.iso
Removing: Linux ISOs/Fedora.iso
Removing: Linux ISOs/Arch.iso
All done, kicking off torrent verification. This may take a while...
Torrent verification successful.
```

This package also includes `transmission-mark-unwanted`, a tool that ingests a
list of file names and marks the corresponding files as "unwanted" (i.e. do not
download) in Transmission.

## How to use

**WARNING:** while great care was used to ensure `transmission-delete-unwanted`
will not mess up wanted torrent data (including extensive automated test
suites), the possibility of a data corruption bug cannot be excluded. If your
torrent data is valuable, it is a good idea to **make a backup** before running
the script. You can get rid of the backup as soon as the torrent passes the
automatic verification step.

1. Make sure you have [Python][] installed.
2. Make sure you have [pipx][] installed.
3. Run `pipx install transmission_delete_unwanted`.
   - The scripts are now available in your PATH.
4. In Transmission, "uncheck" (i.e. set as unwanted/do not download) the files
   that you want to get rid of.
   - Sadly the Transmission UI will not let you do this for fully downloaded
     files (the checkbox is greyed out). You can either do it manually using
     `transmission-remote --no-get`, or use the bundled
     `transmission-mark-unwanted` tool.
5. Run `transmission-delete-unwanted`.
   - Pass `--help` for options.
   - Note the script needs RPC access to your Transmission instance, and it also
     needs write access to the downloaded torrent files.
6. The files are now gone!

## What does `transmission-delete-unwanted` do?

For each torrent that contains files that are (at least partially) downloaded
but not wanted, `transmission-delete-unwanted` does the following:

1. It stops (pauses) the torrent.
   - This ensures Transmission will not attempt to seed data that the script is
     in the middle of deleting.
2. It trims and removes files so that no unwanted torrent pieces remain.
3. It triggers a torrent verification (hash check).
   - This is to make Transmission notice that the data is gone, so that it
     doesn't attempt to seed it anymore.
4. It resumes the torrent.

## FAQ

### How is this different from just deleting the files by hand?

If you naively just delete the files you don't want, it is almost certain that
your torrent will not pass verification anymore, and Transmission will have to
re-download a few bits and pieces.

This is not a Transmission-specific limitation; fundamentally, it is a
consequence of how torrents work. From a low-level BitTorrent protocol
perspective, a torrent is just a giant continuous blob of data that is split
into equal-sized "pieces", which is the smallest unit of data that can be
verified (hash checked) and made available for seeding. If the torrent contains
multiple files, these are just concatenated together; the torrent metadata
indicates the position of each file within the continuous blob.

Crucially, piece boundaries are not related to file boundaries in any way. This
means that it is possible, and in fact very likely, that some pieces will
_straddle_ a file boundary: that is, some pieces contain both the end of a file
and the beginning of the next file.

If you delete a file whose first and/or last piece overlaps with adjacent,
wanted files, you are _de facto_ corrupting these pieces, and Transmission will
(correctly) see them as such. These pieces cannot be advertised for seeding
anymore and will have to be re-downloaded.

The main value proposition of `transmission-delete-unwanted` is it will not fall
into this trap and will correctly preserve overlapping pieces, while still
deleting the remaining unwanted pieces. The tool is also less error-prone as it
does not involve mapping unwanted files manually.

### What does "trimming" mean, and why is the tool producing `.part` files?

If `transmission-delete-unwanted` is unable to remove a file because it contains
data from overlapping wanted pieces (see previous answer), then it will _trim_
the file instead. Trimming means that the file is replaced by a new file which
only contains data from these overlapping pieces and nothing else, so that most
of the disk space can still be reclaimed.

The `.part` suffix makes it clear that this is not a valid, usable file anymore.
This suffix is recognized by Transmission; in fact, it is the same suffix
Transmission itself uses to mark partially downloaded files if the
`rename-partial-files` Transmission setting is used.

Note that these partial files may _look_ like they are still taking the full
amount of disk space, but that is not actually the case. The partial files
`transmission-delete-unwanted` produces are [sparse files][] - that is, most of
the file is a "hole" and does not actually take up disk space. Use the [`du`
command] to see the actual amount of disk space the file is using.

### I marked a file as unwanted, but `transmission-delete-unwanted` does not remove it!

If `transmission-delete-unwanted` produced a `.part` file instead, see the
previous answer.

There is one rare edge case where `transmission-delete-unwanted` may not remove
nor trim the file even though it is unwanted: if the file is only composed of
wanted pieces - i.e. the file is so small that it is only composed of 1 or 2
pieces _and_ these pieces overlap with wanted files - then there is nothing that
can be done about this file without corrupting wanted pieces. In that case the
script will just leave the file alone.

### Is this safe to run on torrents that are actively downloading?

Yes, and it will behave as you'd expect. Even partially downloaded files can be
cleaned up.

The only caveat is this will result in torrent verification being requested in
the middle of a download, which may(?) cause partially downloaded torrent pieces
to be re-downloaded.

[`du` command]: https://man7.org/linux/man-pages/man1/du.1.html
[pipx]: https://pipx.pypa.io/stable/
[Python]: https://www.python.org/
[sparse files]: https://en.wikipedia.org/wiki/Sparse_file
[Transmission]: https://transmissionbt.com/
