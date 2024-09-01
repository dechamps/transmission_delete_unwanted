import base64
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
