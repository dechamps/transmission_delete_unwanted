import random
import pytest
from transmission_delete_unwanted import file


@pytest.fixture(name="copy", params=[1, 2, 100])
def _fixture_copy(request):
    return lambda *kargs, **kwargs: file.copy(
        *kargs, **kwargs, buffer_size=request.param
    )


def test_copy_empty(tmp_path, copy):
    with open(tmp_path / "from.txt", "wb") as from_file:
        pass
    with open(tmp_path / "from.txt", "rb") as from_file, open(
        tmp_path / "to.txt", "wb"
    ) as to_file:
        copy(from_file, to_file, 0)
    with open(tmp_path / "to.txt", "rb") as to_file:
        assert to_file.read() == b""


def test_copy(tmp_path, copy):
    test_contents = b"test contents"
    with open(tmp_path / "from.txt", "wb") as from_file:
        from_file.write(test_contents)
    with open(tmp_path / "from.txt", "rb") as from_file, open(
        tmp_path / "to.txt", "wb"
    ) as to_file:
        copy(from_file, to_file, len(test_contents))
    with open(tmp_path / "to.txt", "rb") as to_file:
        assert to_file.read() == test_contents


def test_copy_partial(tmp_path, copy):
    with open(tmp_path / "from.txt", "wb") as from_file:
        from_file.write(b"test contents")
    with open(tmp_path / "from.txt", "rb") as from_file, open(
        tmp_path / "to.txt", "wb"
    ) as to_file:
        copy(from_file, to_file, 4)
    with open(tmp_path / "to.txt", "rb") as to_file:
        assert to_file.read() == b"test"


def test_copy_outofbounds(tmp_path, copy):
    with open(tmp_path / "from.txt", "wb") as from_file:
        from_file.write(b"test contents")
    with open(tmp_path / "from.txt", "rb") as from_file, open(
        tmp_path / "to.txt", "wb"
    ) as to_file:
        with pytest.raises(file.EOFException):
            copy(from_file, to_file, 100)


def test_copy_seek(tmp_path, copy):
    with open(tmp_path / "from.txt", "wb") as from_file:
        from_file.write(b"0123456789")
    with open(tmp_path / "from.txt", "rb") as from_file, open(
        tmp_path / "to.txt", "wb"
    ) as to_file:
        from_file.seek(4)
        to_file.seek(4)
        copy(from_file, to_file, 4)
    with open(tmp_path / "to.txt", "rb") as to_file:
        assert to_file.read() == b"\x00\x00\x00\x004567"


@pytest.mark.parametrize("from_offset", [0, 1, 2, 5])
@pytest.mark.parametrize("to_offset", [0, 1, 2, 5])
@pytest.mark.parametrize("copy_length", [1, 2, 5])
def test_copy_combined(tmp_path, from_offset, to_offset, copy_length, copy):
    test_contents = random.randbytes(20)
    with open(tmp_path / "from.txt", "wb") as from_file:
        from_file.write(test_contents)
    with open(tmp_path / "from.txt", "rb") as from_file, open(
        tmp_path / "to.txt", "wb"
    ) as to_file:
        from_file.seek(from_offset)
        to_file.seek(to_offset)
        copy(from_file, to_file, copy_length)
    with open(tmp_path / "to.txt", "rb") as to_file:
        assert (
            to_file.read()
            == b"\x00" * to_offset
            + test_contents[from_offset : from_offset + copy_length]
        )
