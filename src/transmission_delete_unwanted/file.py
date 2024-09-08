def copy(from_file, to_file, length):
    # TODO: this could potentially load an unbounded amount of data in memory,
    # especially if the torrent is using a large piece size. We should break the
    # copy operation down into small buffers. Even better would be to use an
    # optimized function such as `os.copy_file_range()` or `os.sendfile()` but
    # these are sadly platform-dependent.
    to_file.write(from_file.read(length))
