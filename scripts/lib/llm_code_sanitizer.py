#!/usr/bin/env python3
"""
llm_code_sanitizer.py — LLM 代码消毒器

将 LLM 生成的代码中的 ak.xxx() 调用重写为 _ds_guard("xxx", ...)，
确保 LLM 代码显式通过 DataSnapshot。

用法:
    from llm_code_sanitizer import sanitize_llm_code

    sanitized, report = sanitize_llm_code(llm_code, ds, stock_code)
    exec(sanitized, namespace)
"""
import ast
from typing import Optional, Tuple, Dict, List


class AkshareCallRewriter(ast.NodeTransformer):
    """AST 重写器：ak.xxx(args) → _ds_guard("xxx", args)"""

    def __init__(self):
        self.rewritten_calls: List[str] = []
        # dict: {alias_name: original_api_name}
        # 处理 from akshare import stock_zh_a_daily as daily
        self._direct_imports: dict = {}

    def visit_Import(self, node):
        """检测 import akshare / import akshare as ak 模式。"""
        for alias in node.names:
            if alias.name == 'akshare':
                asname = alias.asname or 'akshare'
                self._direct_imports[asname] = asname
        return node

    def visit_ImportFrom(self, node):
        """检测 from akshare import xxx / from akshare import xxx as yyy 模式。"""
        if node.module == 'akshare':
            for alias in node.names:
                asname = alias.asname or alias.name
                self._direct_imports[asname] = alias.name
        return node

    def visit_Call(self, node):
        """重写 ak.xxx() 和 xxx() 调用。"""
        self.generic_visit(node)
        func = node.func

        # 模式 1: ak.xxx() 或 akshare.xxx()
        if (isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id in self._direct_imports):
            api_name = func.attr
            new_call = ast.Call(
                func=ast.Name(id='_ds_guard', ctx=ast.Load()),
                args=[ast.Constant(value=api_name)] + node.args,
                keywords=node.keywords,
            )
            self.rewritten_calls.append(api_name)
            return ast.copy_location(new_call, node)

        # 模式 2: from akshare import xxx; xxx()
        if (isinstance(func, ast.Name)
            and func.id in self._direct_imports):
            original_name = self._direct_imports[func.id]
            new_call = ast.Call(
                func=ast.Name(id='_ds_guard', ctx=ast.Load()),
                args=[ast.Constant(value=original_name)] + node.args,
                keywords=node.keywords,
            )
            self.rewritten_calls.append(original_name)
            return ast.copy_location(new_call, node)

        return node


def sanitize_llm_code(
    code: str,
    ds_instance=None,
    stock_code: str = "",
) -> Tuple[str, Dict]:
    """消毒 LLM 代码：将 ak.xxx() 重写为 _ds_guard("xxx", ...)。

    Args:
        code: LLM 生成的原始代码
        ds_instance: DataSnapshot 实例（如有）
        stock_code: 股票代码

    Returns:
        (sanitized_code, report)
    """
    report: Dict = {
        "rewritten_calls": [],
        "parse_error": None,
    }

    # Step 1: AST 解析
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        report["parse_error"] = str(e)
        warn = (
            f"# WARNING: LLM code parse error ({e}), "
            f"falling back to Layer 1 monkey-patch protection\n"
        )
        return warn + code, report

    # Step 2: AST 重写
    rewriter = AkshareCallRewriter()
    new_tree = rewriter.visit(tree)
    ast.fix_missing_locations(new_tree)
    report["rewritten_calls"] = rewriter.rewritten_calls

    # Step 3: 生成最终代码
    rewritten_body = ast.unparse(new_tree)

    # Step 4: 注入 _ds_guard 函数定义
    preamble = f'''
# === Injected by llm_code_sanitizer.py ===
# Stock code: {stock_code}
# Rewritten calls: {rewriter.rewritten_calls}
import pandas as pd
_ds_instance = {repr(ds_instance)}
def _ds_guard(_api_name, *args, **kwargs):
    """Auto-generated guard: replaces ak.xxx() calls. Routes through DataSnapshot."""
    if _ds_instance is not None:
        try:
            params = dict(kwargs)
            if args and isinstance(args[0], str):
                params.setdefault("symbol", args[0])
            result = _ds_instance.fetch_or_cache(_api_name, params)
            if result.get("status") in ("ok", "cached"):
                return pd.DataFrame(result.get("data_full", []))
            elif result.get("status") == "stale":
                import sys
                print(f"WARNING [stale]: {{_api_name}} data outdated", file=sys.stderr)
                return pd.DataFrame(result.get("data_full", []))
        except Exception as _guard_err:
            import sys
            print(f"WARNING [guard fallback]: {{_api_name}}: {{_guard_err}}", file=sys.stderr)
    # Fallback: direct call (will be caught by Layer 1 monkey-patch)
    import akshare as _ak
    _func = getattr(_ak, _api_name)
    return _func(*args, **kwargs)
# === End preamble ===

'''
    return preamble + rewritten_body, report
