class CopyException(Exception):
    pass


class EOFException(Exception):
    pass


def copy(from_file, to_file, length, buffer_size=1024 * 1024):
    while length > 0:
        buffer = from_file.read(min(length, buffer_size))
        if len(buffer) == 0:
            raise EOFException
        to_file.write(buffer)
        length -= len(buffer)
