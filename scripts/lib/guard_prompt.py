#!/usr/bin/env python3
"""
guard_prompt.py — LLM System Prompt 注入（Layer 3）

在所有 scenario 的 system prompt 中追加数据获取规则，
减少 LLM 直接调用 akshare 的概率。
"""

AKSHARE_GUARD_PROMPT = """
## ⚠️ 数据获取规则（强制执行）

你 **必须** 通过 DataSnapshot 获取所有金融数据。

### ✅ 正确用法:
```python
from data_snapshot import DataSnapshot
ds = DataSnapshot("股票代码")
result = ds.fetch_or_cache("api_name", {"symbol": "股票代码"})
df = pd.DataFrame(result["data_full"])
```

### ❌ 禁止用法:
```python
import akshare as ak                    # 禁止直接 import
df = ak.stock_xxx(...)                   # 禁止直接调用
from akshare import stock_xxx            # 禁止 from import
```

### 原因:
1. DataSnapshot 自动检测排序方向，确保返回最新数据
2. DataSnapshot 自动检查数据陈旧度，防止使用过期数据
3. DataSnapshot 提供缓存，相同请求不重复调用 API

### 如果需要未注册的 API:
声明 "需要使用未注册的 API: xxx，请人工验证数据质量"，等待确认后再使用。
"""


def inject_guard_prompt(original_prompt: str) -> str:
    """将 guard prompt 注入到原始 system prompt。"""
    return original_prompt + "\n\n" + AKSHARE_GUARD_PROMPT
