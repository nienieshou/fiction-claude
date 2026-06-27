"""装配层单源信号计数 — 冻结 fact_table.json 的三个交付门计数逻辑。"""
from hiki.prose_facts import signal_counts_from_fact_table


def test_signal_counts_from_fact_table():
    """验证从 fact_table 纯导出三个计数(0 LLM)。"""
    ft = {
        "findings": [
            {"cat": "数值", "conf": "低"},      # 应计入 spine_num_contra
            {"cat": "数值", "conf": "中"},      # 不计(conf中,非低)
            {"cat": "身份", "real": True},      # 应计入 spine_id_contra
            {"cat": "身份", "real": False},     # 不计
        ],
        "生死_verify后": ["人甲", "人乙"],  # 2 entries → ft_revival_residual=2
    }

    result = signal_counts_from_fact_table(ft)

    assert result == {
        "spine_num_contra": 1,
        "spine_id_contra": 1,
        "ft_revival_residual": 2,
    }
