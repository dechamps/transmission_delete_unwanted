import base64


def to_array(pieces_b64bitfield, piece_count):
    pieces_bitfield = base64.b64decode(pieces_b64bitfield)
    assert len(pieces_bitfield) == -(-piece_count // 8)
    return [
        byte & (1 << (bitpos - 1)) != 0
        for byte in pieces_bitfield
        for bitpos in range(8, 0, -1)
    ][:piece_count]
