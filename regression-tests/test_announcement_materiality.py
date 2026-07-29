#!/usr/bin/env python3
"""announcement_materiality P8 标的提取回归测试（Bug 1）。

背景：P8 正则 `([一-龥A-Za-z0-9]{2,20})` 上限 20 → `SJSEMICONDUCTORCORPORATION` 类长名
截断成 `参股公司SJSEMICONDUCTORC`，G46 `tok in report`（只在 `[、,，/]` 拆分后子串校验）
永不命中（报告用全名）→ 硬 FAIL 或被迫复制垃圾 token。

修复 V2：贪婪 ≤40 + 在 连词(暨/及/并)/股权股份 处截断 + rstrip 的之数字%。**不截 资产**
（存货资产/无形资产 是名一部分）。59185 条公告基准（2601 material P8 标题）实测 **0 真回退**。

G46 不对称：截断=硬 FAIL（mid-name 非子串），过截=安全（更短仍是子串）→ 最优策略是「贪婪干净截取」。

本测试锁住：
  1. SJSE 长名不截断（核心 bug 修复）；
  2. 资产名保留（存货资产/无形资产 不被误截）；
  3. 连词/股权/股份/百分号/数字 噪声清理；
  4. 干净标的稳定（V0 已对的，V2 不回退）；
  5. 截断守卫：无输出触 40 上限 / 无 mid-ASCII 截断。
"""
import os, re, sys, unittest

LIB = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'lib')
sys.path.insert(0, LIB)
import announcement_materiality as am

P8 = r"(?:收购|购买|出售|受让|转让|并购|重组)"


def V0(t):
    """旧实现（cap20 + 字符级 rstrip），用于回归对照。"""
    m = re.search(P8 + r"([一-龥A-Za-z0-9]{2,20})", t)
    return m.group(1).rstrip("的之股权股份资产") if m else None


def ext(t):
    """V2 实际函数包装：返回 target 或 None。"""
    return am.extract_machine_fields("P8", t).get("target")


# ---- 1. 核心修复点（canonical，含 600584 实测标题）----
CANONICAL = [
    # (title, expected V2 target)  —— SJSE 截断是 600584 报告的 bug 本身
    ("江苏长电科技股份有限公司关于出售参股公司SJSEMICONDUCTORCORPORATION股权完成交割公告",
     "参股公司SJSEMICONDUCTORCORPORATION"),
    ("600584:江苏长电科技股份有限公司关于出售参股公司SJSEMICONDUCTORCORPORATION股权的公告",
     "参股公司SJSEMICONDUCTORCORPORATION"),
    ("关于收购SJSEMICONDUCTORCORPORATION股权的议案", "SJSEMICONDUCTORCORPORATION"),
    # 晟碟半导体：括号自然停，V0 已对，V2 不回退
    ("江苏长电科技股份有限公司关于收购晟碟半导体(上海)有限公司80%股权的进展公告", "晟碟半导体"),
    # 子公司股权：股权 instrument 截断 → 干净「子公司」
    ("长电科技关于出售子公司股权暨关联交易的公告", "子公司"),
    # 资产名保留（不截 资产）—— V2 得全名
    ("锡业股份关于出售铅业分公司存货资产暨关联交易公告", "铅业分公司存货资产"),
    # 100%股权：rstrip 数字 → 干净（V0 带「100」）
    ("锡业股份关于收购个旧云锡双井实业有限责任公司100%股权暨关联交易的公告",
     "个旧云锡双井实业有限责任公司"),
    # 百分号边缘（小数 %）：贪婪停在 %，rstrip 尾部数字
    ("万邦医药:关于收购安徽赛德盛医药科技有限公司75.52%股权的公告", "安徽赛德盛医药科技有限公司"),
    # 评估报告书（V2.2+ 修复）：「转让股权涉及的X公司股东全部权益价值评估报告书」
    # 朴素 V2 因「涉及的」里的「及」被连词截断→None；V2.4 前置剥前缀 + 边界词截断→干净实体
    ("福建东方百货管理有限公司拟转让股权涉及的福建东百红星商业广场有限公司股东全部权益价值评估报告书",
     "福建东百红星商业广场有限公司"),
    # 股份有限公司名：V2.4 用 股份(?!有限) lookahead 保护（朴素裸切会截成「中国电子工程设计院」）
    ("国投中鲁拟发行股份收购股权涉及的中国电子工程设计院股份有限公司股东全部权益价值资产评估报告书",
     "中国电子工程设计院股份有限公司"),
    # 免于要约/之进展：V2.4 在「免于/之进展」边界词截断→全名（朴素 V2 截在股份丢全名）
    ("浙江京衡律师事务所关于仇建平收购杭州巨星科技股份有限公司免于发出要约事项",
     "杭州巨星科技股份有限公司"),
    ("万科A关于公开挂牌转让环山集团股份有限公司股权之进展公告",
     "环山集团股份有限公司"),
]


class P8ExtractionTests(unittest.TestCase):

    def test_canonical_fixes(self):
        """核心修复点：SJSE 不截断 + 资产保留 + 噪声清理。"""
        for title, expected in CANONICAL:
            with self.subTest(title=title[:30]):
                got = ext(title)
                self.assertEqual(got, expected,
                                 f"\n  title: {title}\n  expected: {expected!r}\n  got:      {got!r}")

    def test_sjse_not_truncated(self):
        """SJSE 类长英文名：V0 截断（G46 硬 FAIL），V2 必须出全名。"""
        t = "关于出售参股公司SJSEMICONDUCTORCORPORATION股权完成交割公告"
        self.assertEqual(V0(t), "参股公司SJSEMICONDUCTORC")   # 旧：截断（bug）
        self.assertEqual(ext(t), "参股公司SJSEMICONDUCTORCORPORATION")  # 新：全名

    def test_asset_name_preserved(self):
        """资产是名一部分时不被误截（V3 会误截，V2 保留）。"""
        for t, exp in [
            ("关于购买无形资产暨关联交易的公告", "无形资产"),
            ("锡业股份关于出售铅业分公司存货资产暨关联交易公告", "铅业分公司存货资产"),
        ]:
            self.assertEqual(ext(t), exp, f"资产名被误截: {t}")
            self.assertIn("资产", ext(t) or "", "资产名丢失")

    # ---- 真实标题样本（取自 59185 公告基准；V0→V2 行为锁定）----
    SAMPLE = [
        ("乖宝宠物:关于公司购买无形资产暨关联交易的公告", "无形资产"),
        ("万邦医药:关于收购安徽赛德盛医药科技有限公司75.52%股权的公告", "安徽赛德盛医药科技有限公司"),
        ("上海能源:上海能源关于收购启东市华尔晟新能源科技有限公司100%股权的进展公告", "启东市华尔晟新能源科技有限公司"),
        ("东方雨虹:关于收购世界五金塑胶厂有限公司100%股权进展暨交割完成的公告", "世界五金塑胶厂有限公司"),
        ("爱普股份:爱普香料集团股份有限公司关于收购挪亚圣诺(太仓)生物科技有限公司100%股权的进展公告", "挪亚圣诺"),
        ("北京科锐:关于转让二级参股公司陕西科锐综合能源服务有限公司股权的公告", "二级参股公司陕西科锐综合能源服务有限公司"),
        ("*ST英飞:关于挂牌转让全资子公司Infinova(India)PrivateLimited100%股权的公告", "全资子公司Infinova"),
        # 进展公告类（无标的水，文档型）—— V2.4「进展」是边界词 → 整串被截断 → None
        # （比 V0 surface「进展公告」文档词更干净；G46 无 target 即不查，neutral）
        ("长电科技重大资产重组进展公告", None),
    ]

    def test_real_sample_outputs(self):
        for title, expected in self.SAMPLE:
            with self.subTest(title=title[:30]):
                self.assertEqual(ext(title), expected,
                                 f"\n  title: {title}\n  expected: {expected!r}\n  got:      {ext(title)!r}")

    def test_no_truncation_guard(self):
        """截断守卫：所有样本输出都不触 40 上限、不以半截 ASCII 大写结尾。"""
        all_titles = [t for t, _ in CANONICAL] + [t for t, _ in self.SAMPLE]
        for t in all_titles:
            got = ext(t)
            if not got:
                continue
            self.assertLess(len(got), 40, f"触 40 上限（截断）: {got!r} ← {t}")
            # 不以孤立 ASCII 字母结尾且标题其后还有更多 ASCII（mid-name 截断特征）
            if got[-1].isascii() and got[-1].isalpha():
                idx = t.find(got)
                tail = t[idx + len(got):idx + len(got) + 3] if idx >= 0 else ""
                self.assertNotRegex(tail, r'^[A-Za-z]',
                                    f"mid-ASCII 截断: {got!r} 后继 {tail!r} ← {t}")

    def test_no_clean_regression(self):
        """回归守卫：V0 已是干净标的（无噪声前缀/后缀）时，V2 不许变差（None 或更垃圾）。"""
        NAME_KW = ('公司', '集团', '有限', '科技', '半导体', '能源', '资源', '医药', '置业',
                   '实业', '控股', '投资', '发展', '新材', '材料')
        LEADING_NOISE = ('股权涉及', '事宜涉及', '涉及的', '方式', '协议转让', '拟', '之', '及', '并',
                         '暨', '的', '部分', '相关', '本次', '事宜', '结果', '摊薄')
        DOC_SUFFIX = ('公告', '报告书', '报告', '说明', '摘要', '草案', '提示', '预案')

        def usable(tok):
            if not tok or len(tok) < 2 or tok.startswith(LEADING_NOISE):
                return False
            if any(tok.endswith(s) for s in DOC_SUFFIX):
                return False
            return any(s in tok for s in NAME_KW) or \
                sum(c.isascii() and c.isalpha() for c in tok) >= 4

        all_titles = [t for t, _ in CANONICAL] + [t for t, _ in self.SAMPLE]
        regressed = []
        for t in all_titles:
            a, b = V0(t), ext(t)
            if usable(a) and not usable(b) and a != b:
                # 同名区（互为子串）不算回退
                if not (a in (b or "") or (b or "") in a):
                    regressed.append((t, a, b))
        self.assertEqual(regressed, [], f"干净标的回退: {regressed}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
