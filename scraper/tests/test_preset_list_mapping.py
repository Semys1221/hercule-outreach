"""Instantly list UUID → scraper preset mapping."""

from bootstrap.discovery import preset_for_instantly_list_id


def test_preset_for_avocat_list() -> None:
    assert (
        preset_for_instantly_list_id("0010fd68-8e7a-4624-bb65-6216b260bf2c")
        == "avocats"
    )


def test_preset_for_unknown_list() -> None:
    assert preset_for_instantly_list_id("00000000-0000-0000-0000-000000000000") is None
