#!/usr/bin/env python3
"""test_e2e_v210 — V2-10 E2E 成本块契约（判据 v5 口径）。

覆盖：
  1. 六票三元组逐位复现：E2E(0.1) 与 CNY 与 1M 审计定标值全等（容差 = 渲染位数）。
  2. 同权禁令模板：每块必含 w 全档行（0/0.01/0.05/0.1/0.25）+ w_real 行——同一三元组下输出。
  3. 同权翻转点：圣泉 vs 东材4b 的 w* = 0.0005（0.0137M / 28.21M）。
  4. 威派格 V4 闭环：audit 切面三元组 → 5.302M；冻结时点整文件三元组 → 5.478M（=v4 冻结 5.48），
     两口径并存有定义，票成本 canon = v4 冻结值。
  5. R10 水位与隐性推理分量的存在性与格式。
跑：python3 test_e2e_v210.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import token_audit  # noqa: E402

# 六票三元组（input, cache_read, output）——来源各票 token_audit / v4 冻结重放
TRIPLETS = {
    "东材4b":        (1092108, 32420352, 335051),
    "威派格_audit切面": (1642403, 32285632, 431353),
    "威派格_冻结时点":  (1671821, 33585664, 447598),
    "先导":          (1647630, 36594368, 384050),
    "厦钨":          (1465021, 42443264, 467710),
    "圣泉_1M":       (1070690, 60630144, 342754),
    "东材1M-v1":     (1369532, 68666112, 487018),
}


def _cny(tri):
    P = token_audit.E2E_PRICES
    return tri[0] * P["input"] + tri[1] * P["cache"] + tri[2] * P["out"]


def _e2e01(tri):
    return tri[0] + 0.1 * tri[1] + tri[2]


def test_six_ticket_exact_values():
    assert abs(_e2e01(TRIPLETS["东材4b"]) / 1e6 - 4.6692) < 0.0001
    assert abs(_cny(TRIPLETS["东材4b"]) - 4.63) < 0.005
    assert abs(_e2e01(TRIPLETS["圣泉_1M"]) / 1e6 - 7.4765) < 0.0001
    assert abs(_cny(TRIPLETS["圣泉_1M"]) - 7.88) < 0.005
    assert abs(_e2e01(TRIPLETS["东材1M-v1"]) / 1e6 - 8.7232) < 0.0001
    assert abs(_cny(TRIPLETS["东材1M-v1"]) - 9.13) < 0.005


def test_render_block_contains_triplet_and_grid():
    lines = token_audit.e2e_v210_block(*TRIPLETS["东材1M-v1"], prefix_series=[100, 200])
    text = "\n".join(lines)
    assert "(1,369,532, 68,666,112, 487,018)" in text
    for w in token_audit.E2E_W_GRID:
        assert f"w={w}:" in text
    assert "w_real=0.2875" in text
    assert "9.13" in text            # CNY 真账
    assert "8.7232" in text          # w=0.1 观测列


def test_same_weight_flip_point():
    a, b = TRIPLETS["圣泉_1M"], TRIPLETS["东材4b"]
    w_star = ((_b := (b[0] + b[2])) - (a[0] + a[2])) / (a[1] - b[1])
    assert abs(w_star - 0.000486) < 0.00001  # ≈0.0005：现实定价内不翻转


def test_wei_v4_cut_definitions():
    assert abs(_e2e01(TRIPLETS["威派格_audit切面"]) / 1e6 - 5.3024) < 0.0001
    assert abs(_e2e01(TRIPLETS["威派格_冻结时点"]) / 1e6 - 5.4780) < 0.0001  # = v4 冻结 5.48


def test_r10_and_hidden_component():
    lines = token_audit.e2e_v210_block(
        1369532, 68666112, 487018, [100000, 343439],
        input_series=[500, 25234],
        text_chars=5501, thinking_chars=176193, tool_chars=121434)
    text = "\n".join(lines)
    assert "R10 prefix 水位" in text and "343,439" in text
    assert "compact 探针（单请求 input>100K）= 0 处" in text  # prefix>100K 不触发探针
    assert "隐性推理分量" in text and "隐性 ≈" in text
    # 反例 1：无水位序列时不产 R10 行
    assert "R10" not in "\n".join(token_audit.e2e_v210_block(1, 2, 3, []))
    # 反例 2：非 cache input 超 100K 才触发探针（两极验证）
    hit = "\n".join(token_audit.e2e_v210_block(
        1369532, 68666112, 487018, [100000, 343439], input_series=[500, 150000]))
    assert "compact 探针命中" in hit


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✅ {name}")
    print("test_e2e_v210 全绿")
