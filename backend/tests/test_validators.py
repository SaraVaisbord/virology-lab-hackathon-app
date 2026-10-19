from validators import israeli_id_is_valid, parse_iso_like_date


def test_israeli_id_valid():
    # Function returns a boolean for numeric-like inputs
    assert isinstance(israeli_id_is_valid("012345678"), bool)
    assert isinstance(israeli_id_is_valid("123456782"), bool)


def test_israeli_id_invalid():
    assert israeli_id_is_valid("") is False
    assert israeli_id_is_valid("123") is False


def test_parse_iso_like_date():
    assert parse_iso_like_date("2026-10-18") is not None
    assert parse_iso_like_date("18/10/2026") is not None
    assert parse_iso_like_date("invalid-date") is None
