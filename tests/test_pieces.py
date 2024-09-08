import base64
import pytest
from transmission_delete_unwanted import pieces


def test_to_array_empty():
    assert pieces.to_array(base64.b64encode(bytes([])), 0) == []


def test_to_array_zero():
    assert pieces.to_array(base64.b64encode(bytes([0b00000000])), 1) == [False]


def test_to_array_one():
    assert pieces.to_array(base64.b64encode(bytes([0b10000000])), 1) == [True]


def test_to_array_onezero():
    assert pieces.to_array(base64.b64encode(bytes([0b10101010])), 8) == [
        True,
        False,
        True,
        False,
        True,
        False,
        True,
        False,
    ]


def test_to_array_zeroone():
    assert pieces.to_array(base64.b64encode(bytes([0b01010101])), 8) == [
        False,
        True,
        False,
        True,
        False,
        True,
        False,
        True,
    ]


def test_to_array_multibyte():
    assert pieces.to_array(base64.b64encode(bytes([0b10000001, 0b01111110])), 16) == [
        True,
        False,
        False,
        False,
        False,
        False,
        False,
        True,
        False,
        True,
        True,
        True,
        True,
        True,
        True,
        False,
    ]


def test_to_array_too_short():
    with pytest.raises(ValueError):
        pieces.to_array(base64.b64encode(bytes([0])), 9)


def test_to_array_too_long():
    with pytest.raises(ValueError):
        pieces.to_array(base64.b64encode(bytes([0, 0])), 8)


def test_to_array_spurious_bits():
    with pytest.raises(ValueError):
        pieces.to_array(base64.b64encode(bytes([0b00001000])), 4)


def test_pieces_wanted_from_files_empty():
    assert pieces.pieces_wanted_from_files([], [], 1) == []


@pytest.mark.parametrize("piece_size", [1, 2, 3])
def test_pieces_wanted_from_files_unwanted(piece_size):
    assert pieces.pieces_wanted_from_files([1], [0], piece_size) == [False]


@pytest.mark.parametrize("piece_size", [1, 2, 3])
def test_pieces_wanted_from_files_unwanted_over(piece_size):
    assert pieces.pieces_wanted_from_files([1], [0], piece_size) == [False]


@pytest.mark.parametrize("piece_size", [1, 2, 3])
def test_pieces_wanted_from_files_wanted(piece_size):
    assert pieces.pieces_wanted_from_files([1], [1], piece_size) == [True]


@pytest.mark.parametrize("piece_size", [1, 2, 3])
def test_pieces_wanted_from_files_wanted_over(piece_size):
    assert pieces.pieces_wanted_from_files([1], [1], piece_size) == [True]


def test_pieces_wanted_from_files_unwanted2():
    assert pieces.pieces_wanted_from_files([1, 1], [0, 0], 1) == [False, False]


def test_pieces_wanted_from_files_wanted2():
    assert pieces.pieces_wanted_from_files([1, 1], [1, 1], 1) == [True, True]


def test_pieces_wanted_from_files_mixed2():
    assert pieces.pieces_wanted_from_files([1, 1], [1, 0], 1) == [True, False]
    assert pieces.pieces_wanted_from_files([1, 1], [0, 1], 1) == [False, True]


@pytest.mark.parametrize("piece_size", [2, 3, 4])
def test_pieces_wanted_from_files_onepiece_multifile_wanted(piece_size):
    assert pieces.pieces_wanted_from_files([1, 1], [1, 1], piece_size) == [True]


@pytest.mark.parametrize("piece_size", [2, 3, 4])
def test_pieces_wanted_from_files_onepiece_multifile_unwanted(piece_size):
    assert pieces.pieces_wanted_from_files([1, 1], [0, 0], piece_size) == [False]


@pytest.mark.parametrize("piece_size", [2, 3, 4])
def test_pieces_wanted_from_files_onepiece_multifile_mix(piece_size):
    assert pieces.pieces_wanted_from_files([1, 1], [0, 1], piece_size) == [True]
    assert pieces.pieces_wanted_from_files([1, 1], [1, 0], piece_size) == [True]


def test_pieces_wanted_from_files_multipiece():
    assert pieces.pieces_wanted_from_files([3, 1], [0, 1], 2) == [False, True]
    assert pieces.pieces_wanted_from_files([3, 1], [1, 0], 2) == [True, True]
    assert pieces.pieces_wanted_from_files([1, 3], [0, 1], 2) == [True, True]
    assert pieces.pieces_wanted_from_files([1, 3], [1, 0], 2) == [True, False]
