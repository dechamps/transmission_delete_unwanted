import base64


def to_array(pieces_b64bitfield, piece_count):
    pieces_bitfield = base64.b64decode(pieces_b64bitfield)
    if len(pieces_bitfield) != -(-piece_count // 8):
        raise ValueError(
            f"Length of pieces bitfield ({len(pieces_b64bitfield)}) is not consistent"
            f" with piece count ({piece_count})"
        )
    pieces = [
        byte & (1 << (bitpos - 1)) != 0
        for byte in pieces_bitfield
        for bitpos in range(8, 0, -1)
    ]
    if any(pieces[piece_count:]):
        raise ValueError("Pieces bitfield contains spurious trailing set bits")
    return pieces[:piece_count]


def pieces_wanted_from_files(file_lengths, files_wanted, piece_size):
    pieces_wanted = [None] * -(-sum(file_lengths) // piece_size)
    current_offset = 0
    for file_length, file_wanted in zip(file_lengths, files_wanted):
        assert file_wanted in (0, 1)
        # Compute piece boundaries. Note we can't use file["beginPiece"] and
        # file["endPiece"] for this because these are new fields that the
        # Transmission server may be too old to support.
        for piece_index in range(
            current_offset // piece_size,
            -(-(current_offset + file_length) // piece_size),
        ):
            # The value for that piece may already have been set by the previous
            # file, due to unaligned piece/file boundaries. In this case, a piece
            # is wanted if it overlaps with any wanted file.
            pieces_wanted[piece_index] = pieces_wanted[piece_index] or file_wanted
        current_offset += file_length
    assert all(wanted_piece is not None for wanted_piece in pieces_wanted)
    return pieces_wanted
