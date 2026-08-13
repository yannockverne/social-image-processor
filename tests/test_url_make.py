from app.services.url_make import replace_url_make_section


def test_creates_section_in_blank_description_and_preserves_order():
    assert replace_url_make_section("", ["https://x/2", "https://x/1"]) == (
        "## URL MAKE\nhttps://x/2\nhttps://x/1\n"
    )


def test_appends_section_without_changing_existing_content():
    original = "## X\n\nPost text."
    assert replace_url_make_section(original, ["https://new/1"]) == (
        original + "\n\n## URL MAKE\nhttps://new/1\n"
    )


def test_replaces_only_managed_section_before_another_heading():
    original = "## X\n\nPost.\n\n## URL MAKE\nhttps://old/1\n\n## Notes\n\nKeep this.\n"
    expected = "## X\n\nPost.\n\n## URL MAKE\nhttps://new/1\n\n## Notes\n\nKeep this.\n"
    result = replace_url_make_section(original, ["https://new/1"])
    assert result == expected
    assert result.count("## URL MAKE") == 1


def test_replaces_section_at_end():
    assert replace_url_make_section("Intro\n\n## URL MAKE\nold\n", ["new"]) == (
        "Intro\n\n## URL MAKE\nnew\n"
    )
