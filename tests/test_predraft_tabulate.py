# tests/test_predraft_tabulate.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import predraft_tabulate as pt


def test_precision_recall_basic():
    # opus 对 b1 预测 hard {混名,境界}; 实测 {混名,性别错}
    predraft = {"b1": {"opus": {"hard": {"混名/认亲矛盾", "境界乱序"}, "all": {"混名/认亲矛盾", "境界乱序"}}}}
    observed = {"b1": ["混名/认亲矛盾", "性别错"]}
    pr = pt.precision_recall(predraft, observed)
    o = pr["opus"]
    # 混名: tp(预测+实测) ; 境界: fp(预测未实测) ; 性别错: fn(实测未预测)
    assert o["混名/认亲矛盾"]["tp"] == 1 and o["混名/认亲矛盾"]["precision"] == 1.0
    assert o["境界乱序"]["fp"] == 1 and o["境界乱序"]["precision"] == 0.0
    assert o["性别错"]["fn"] == 1 and o["性别错"]["recall"] == 0.0


def test_crossfamily_synthesized_precision_recall():
    # opus 预测 {混名}, gpt55 预测 {境界}; 实测 {混名,境界} → 跨族=opus∪gpt55 两者都 tp
    predraft = {"b1": {"opus": {"hard": {"混名/认亲矛盾"}, "all": {"混名/认亲矛盾"}},
                       "gpt55": {"hard": {"境界乱序"}, "all": {"境界乱序"}}}}
    observed = {"b1": ["混名/认亲矛盾", "境界乱序"]}
    pr = pt.precision_recall(predraft, observed)
    assert "crossfamily" in pr                       # 合成跨族 reviewer
    assert pr["crossfamily"]["混名/认亲矛盾"]["tp"] == 1
    assert pr["crossfamily"]["境界乱序"]["tp"] == 1


def test_precision_recall_no_data_safe():
    pr = pt.precision_recall({}, {})
    assert pr == {}                                  # 空不崩, 返回空 dict


def test_format_report_deepseek_vs_crossfamily_pr():
    # deepseek 漏报混名(实测有)→ R=0; 跨族(opus)报中 → R=1; 报告须含 P/R 对比行
    predraft = {"b1": {"opus": {"hard": {"混名/认亲矛盾"}, "all": {"混名/认亲矛盾"}},
                       "gpt55": {"hard": set(), "all": set()},
                       "deepseek": {"hard": set(), "all": set()}}}
    observed = {"b1": ["混名/认亲矛盾"]}
    out = pt.format_predraft_report(predraft, observed)
    assert "精度" in out and "诚实" in out
    assert "DeepSeek P=" in out and "跨族 P=" in out   # 真 P/R 对比(非仅命中数)
