from aiskra.shared.text import search_key


def test_search_key_is_case_and_yo_insensitive() -> None:
    assert search_key("  Петров  Пётр ", None, "PETROV") == "петров петр petrov"
    assert search_key("ПЁТР") == search_key("петр")
    assert search_key(None, "") == ""
