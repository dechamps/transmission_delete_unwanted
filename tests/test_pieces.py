import base64
import pytest
from transmission_delete_unwanted import pieces


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
