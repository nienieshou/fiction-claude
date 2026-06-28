"""C6②: config.advisory_on 单源 advisory 开关助手。"""
from hiki import config


def test_advisory_on_missing_block_returns_default():
    assert config.advisory_on({}, "craft_audit") is True
    assert config.advisory_on({}, "anything", default=False) is False


def test_advisory_on_none_block_returns_default():
    assert config.advisory_on({"advisories": None}, "craft_audit") is True


def test_advisory_on_block_present_key_missing_returns_default():
    assert config.advisory_on({"advisories": {}}, "craft_audit") is True


def test_advisory_on_explicit_value_wins():
    assert config.advisory_on({"advisories": {"craft_audit": False}}, "craft_audit") is False
    assert config.advisory_on({"advisories": {"craft_audit": True}}, "craft_audit", default=False) is True
