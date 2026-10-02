# BrightLedger 401(k) 安全港配比验证库

处理单个员工单年的配比结算，并判定增强公式是否在指定工资闭区间内
处处不少于基础公式（前 3% 缴费匹配 100%、接下来至 5% 匹配 50%、无上限）。

## 约定

- 金额：整数分；比例：整数基点（10_000 基点 = 100%）。
- 年工资范围：2_500_000 至 50_000_000 分。
- 年缴费：0 至工资 10% 向下取整之间的任意整数分。
- 结算：各档工资阈值分别向下取整到分；缴费依次填档；超过末档不匹配；
  每档金额乘匹配率后单独四舍五入到分（恰好半分向上）；求和后应用年度上限。

## API

```python
from brightledger import Plan, Tier, match, certify

plan = Plan(tiers=(Tier(400, 10_000),), cap_cents=None)  # 前 4% 匹配 100%

match(plan, 2_500_020, 125_001)          # -> 100000（雇主配比，分）
result = certify(plan, 2_500_000, 50_000_000)
# -> Certification(passed=False, salary=2500020, deferral=125001)
# 合格时 passed=True；否则返回工资最小、该工资下缴费最小的反例。
```

## 实现要点

少付判定分解为 `B >= E_raw + 1`（忽略上限的逐档条件）与 `B >= cap + 1`
（上限条件）的析取。后者用单调性二分 + 闭式最小缴费；前者把基础公式与
增强公式的档位边界合并成固定顺序的缴费分段，每段内最小可行缴费有闭式解，
再用"精确赤字 >= 1/2"的必要条件过滤工资区间，仅对幸存区间做 numpy
向量化扫描。测试中以穷举法对随机计划做交叉验证。

## 运行

```bash
python3 -m pytest tests -q     # 运行全部自动化测试
python3 -c "from brightledger import certify, Plan, Tier; \
print(certify(Plan(tiers=(Tier(400, 10000),)), 2_500_000, 50_000_000))"
```

依赖：Python 3.10+，numpy（测试另需 pytest）。
