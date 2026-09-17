#!/usr/bin/env python3
"""test_e2e_v210 — V2-10 E2E 成本块契约（判据 v5 EQ-Tokens 口径）。

覆盖：
  1. 七票三元组 EQ 逐位复现（canon 三元组；威=冻结时点整文件）。
  2. 主判据线与同票比：0.70×基线 = 15.9709M；22.8156/11.5856 = 1.9690（与 CNY 口径逐位一致）。
  3. 三层输出结构：raw 三元组正典 → EQ 主行 → CNY 导出行（价表快照注记，无促销限定词）。
  4. 同权禁令模板：w 全档行 + w_real 行同三元组输出；翻转点 0.0005。
  5. 威派格 V4 双口径（audit 切面 12.4343 vs canon 12.8943）。
  6. R10 水位 + 隐性推理分量 + compact 探针两极。
跑：python3 test_e2e_v210.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import token_audit  # noqa: E402

# 七票 canon 三元组 (input, cache_read, output)
TRIPLETS = {
    "东材4b":    (1092108, 32420352, 335051),
    "威派格":    (1671821, 33585664, 447598),
    "威派格_audit切面": (1642403, 32285632, 431353),
    "先导":      (1647630, 36594368, 384050),
    "厦钨":      (1465021, 42443264, 467710),
    "圣泉_1M":   (1070690, 60630144, 342754),
    "东材1M-v1": (1369532, 68666112, 487018),
    "飞凯":      (1104819, 51792064, 304308),
}
EQ_EXPECT = {  # 逐位复验值（0.2875/3.5 比率）
    "东材4b": 11.5856, "威派格": 12.8943, "先导": 13.5127, "厦钨": 15.3044,
    "圣泉_1M": 19.7015, "东材1M-v1": 22.8156, "飞凯": 17.0601,
}


def _eq(tri, model="flash"):
    return token_audit.e2e_eq(*tri, model=model) / 1e6


def test_seven_ticket_eq_exact():
    for k, v in EQ_EXPECT.items():
        assert abs(_eq(TRIPLETS[k]) - v) < 0.0005, (k, _eq(TRIPLETS[k]))


def test_criterion_line_and_same_ticket_ratio():
    base = _eq(TRIPLETS["东材1M-v1"])
    assert abs(base * 0.70 - 15.9709) < 0.0005          # 主判据线
    assert abs(base * 0.80 - 18.2525) < 0.0005          # 分程带上沿
    ratio = base / _eq(TRIPLETS["东材4b"])
    assert abs(ratio - 1.9690) < 0.001                  # 与 CNY 口径逐位一致（纯换算）


def test_render_three_layers():
    lines = token_audit.e2e_v210_block(*TRIPLETS["东材1M-v1"], prefix_series=[100, 200])
    text = "\n".join(lines)
    assert "(1,369,532, 68,666,112, 487,018)" in text   # 正典三元组
    assert "EQ-Tokens（主判据" in text and "22.8156" in text
    assert "CNY 导出行" in text and "价表快照" in text
    assert "五折" not in text                            # 促销限定词不得入判据正文
    for w in token_audit.E2E_W_GRID:
        assert f"w={w}:" in text
    assert "w_real=0.2875" in text


def test_same_weight_flip_point():
    a, b = TRIPLETS["圣泉_1M"], TRIPLETS["东材4b"]
    w_star = ((b[0] + b[2]) - (a[0] + a[2])) / (a[1] - b[1])
    assert abs(w_star - 0.000486) < 0.00001


def test_wei_v4_dual_cut():
    assert abs(_eq(TRIPLETS["威派格_audit切面"]) - 12.4343) < 0.0005
    assert abs(_eq(TRIPLETS["威派格"]) - 12.8943) < 0.0005


def test_r10_hidden_probe_polarity():
    lines = token_audit.e2e_v210_block(
        1369532, 68666112, 487018, [100000, 343439],
        input_series=[500, 25234],
        text_chars=5501, thinking_chars=176193, tool_chars=121434)
    text = "\n".join(lines)
    assert "R10 prefix 水位" in text and "compact 探针（单请求 input>100K）= 0 处" in text
    assert "隐性推理分量" in text
    assert "R10" not in "\n".join(token_audit.e2e_v210_block(1, 2, 3, []))
    hit = "\n".join(token_audit.e2e_v210_block(
        1369532, 68666112, 487018, [100000, 343439], input_series=[500, 150000]))
    assert "compact 探针命中" in hit


def test_flagship_ratio_config():
    # 常数模型特定：旗舰 = 0.25/3.5（判据换模型时随冻结件快照切换）
    assert token_audit.E2E_RATIOS["flagship"] == {"cache": 0.25, "out": 3.5}


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✅ {name}")
    print("test_e2e_v210 全绿")
