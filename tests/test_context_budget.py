from modules.context.budget import ConservativeTokenCounter


def test_token_counter_is_conservative_for_chinese_and_ascii() -> None:
    counter = ConservativeTokenCounter()
    assert counter.count_text("中文测试") == 12
    assert counter.count_text("abcdefgh") == 8
    assert counter.count_text("中文abcdefgh") == 14
