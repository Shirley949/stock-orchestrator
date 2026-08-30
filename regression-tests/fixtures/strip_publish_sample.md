# 样例报告（strip invariant 语料）

发布层剥离结构不变性测试的固化语料：混合 [src:] 明文/注释两式 + [verified:] 指针 +
表格 + code fence + 非 src 的模板占位注释。**故意包含 `<!-- PART-X -->` 类非 src 注释**
——strip 职责只剥 src 隐藏注记，模板注释不属其职责面（2026-08-27 收窄断言时定型）。

---

## 证据全景

| 维度 | 现状 | 方向 |
|------|------|------|
| 价格位置 [src: snapshot.s2_quote_kline.data.realtime_quote] | 现价 63.01 <!-- [src: snapshot.s2_quote_kline.data.realtime_quote.current] --> | 中性 |
| 技术面 | MACD 零轴下修复 [src: snapshot.s4_technical.data.technical.macd] | 偏多 |

```json
{"direction": "neutral", "probability": null}
```

<!-- PART-B -->

结论一句话：短期不建议开仓，等待右侧信号。

[verified: self_score=100 profile=quick | see analysis_report.verified.json]
