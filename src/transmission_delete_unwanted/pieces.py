import base64


def to_array(transmission_torrent):
    pieces_bitfield = base64.b64decode(transmission_torrent.pieces)
    piece_count = transmission_torrent.piece_count
    assert len(pieces_bitfield) == -(-piece_count // 8)
    return [
        byte & (1 << (bitpos - 1)) != 0
        for bitpos in range(8, 0, -1)
        for byte in pieces_bitfield
    ][: transmission_torrent.piece_count]
