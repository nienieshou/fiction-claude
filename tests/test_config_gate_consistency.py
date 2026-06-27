"""交付门阈值单源化: gate.SHIP_GATE_DEFAULTS 为唯一规范源, config.py 不再手抄(曾 stale 过),
pipeline.yaml 为运营覆盖层(键集须与规范源一致, 防 typo/漏键静默失效)。零 API。"""
import pytest
from hiki import config, gate


def test_config_defaults_no_ship_gate_handcopy():
    # 单源化: config._DEFAULTS 不再手抄 ship_gate → 规范源唯一在 gate.SHIP_GATE_DEFAULTS
    assert "ship_gate" not in config._DEFAULTS


def test_ship_gate_fallback_to_canonical():
    # 无 yaml path: config.load 返回 _DEFAULTS(无 ship_gate)→ 消费点 .get("ship_gate") or fallback 落规范源
    # (复刻 produce.py 取 gate_thr 的表达式)
    thr = (config._DEFAULTS or {}).get("ship_gate") or gate.SHIP_GATE_DEFAULTS
    assert thr is gate.SHIP_GATE_DEFAULTS


def test_pipeline_yaml_ship_gate_keys_match_canonical():
    # pipeline.yaml ship_gate 键集须 == 规范源键集: 防 yaml 漏键/typo 静默失效, 或 gate 加键忘同步 yaml
    yaml = pytest.importorskip("yaml")
    p = config._CONFIG_DIR / "pipeline.yaml"
    cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert set(cfg["ship_gate"]) == set(gate.SHIP_GATE_DEFAULTS)
