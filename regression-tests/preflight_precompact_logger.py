#!/usr/bin/env python3
"""preflight_precompact_logger.py — 4a 诱导 compact 前置②（批3-3c，用后即焚）。

PreCompact(matcher:manual) logger 探针：压缩前触发，记录诱导时点（与 SessionStart
的压缩后触发配对，两时间戳夹住一次 /compact）。**不入常驻 settings**——4a 实测完
`--uninstall` 即焚。

双模式：
  1) hook 模式（被 settings 调用）：stdin=hook JSON → 追加一行到 /tmp/precompact_probe.log
  2) --install / --uninstall：临时写/删 ~/.claude/settings.json 的 PreCompact hook 条目
     （自动备份 settings.json.bak-precompact；uninstall 恢复清理）

用法：
  python3 preflight_precompact_logger.py --install    # 装探针（幂等）
  python3 preflight_precompact_logger.py --uninstall  # 拆探针（用后必跑）
  （被 hook 调用时无参数：读 stdin 记日志，零输出零退出码干扰）
"""
import json
import sys
import time
from pathlib import Path

LOG = Path("/tmp/precompact_probe.log")
SETTINGS = Path.home() / ".claude" / "settings.json"
HOOK_KEY = "PreCompact"
SELF = str(Path(__file__).resolve())
ENTRY = {
    "matcher": "manual",
    "hooks": [{"type": "command", "command": f"python3 {SELF}"}],
}


def hook_mode():
    try:
        d = json.load(sys.stdin)
    except Exception:
        d = {}
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
           "source": d.get("source", "?"),
           "transcript": Path(d.get("transcript_path", "")).name,
           "custom": d.get("custom_instructions", "")[:80]}
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _load_settings():
    if not SETTINGS.exists():
        return {}
    return json.loads(SETTINGS.read_text(encoding="utf-8"))


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("--install", "--uninstall"):
        cfg = _load_settings()
        hooks = cfg.setdefault("hooks", {})
        items = hooks.get(HOOK_KEY, [])
        if sys.argv[1] == "--install":
            if any(h.get("hooks", [{}])[0].get("command", "") == ENTRY["hooks"][0]["command"]
                   for h in items):
                print("ℹ️ 探针已在位，不重复装")
                return
            SETTINGS.with_suffix(".json.bak-precompact").write_text(
                SETTINGS.read_text(encoding="utf-8"), encoding="utf-8") \
                if SETTINGS.exists() else None
            items.append(ENTRY)
            hooks[HOOK_KEY] = items
            SETTINGS.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"✅ PreCompact(matcher:manual) 探针已装（备份 {SETTINGS}.bak-precompact；"
                  f"日志 {LOG}）。用后必跑 --uninstall。")
        else:
            kept = [h for h in items if h.get("hooks", [{}])[0].get("command", "") != ENTRY["hooks"][0]["command"]]
            hooks[HOOK_KEY] = kept
            if not kept:
                del hooks[HOOK_KEY]
            SETTINGS.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"✅ 探针已拆（日志留存 {LOG}，读后可 rm）")
        return
    hook_mode()


if __name__ == "__main__":
    main()
