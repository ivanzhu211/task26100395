import unittest

from brightledger import Plan, Tier, basic_plan, match


class MatchSettlementTest(unittest.TestCase):
    def test_tier_thresholds_floor_to_cents(self):
        # 3% of 2,500,020 = 75000.6 -> floored to 75000
        plan = Plan((Tier(300, 10000),))
        self.assertEqual(match(plan, 2_500_020, 75_001), 75_000)

    def test_tiers_fill_sequentially(self):
        plan = Plan((Tier(300, 10000), Tier(500, 5000)))
        # t1 = 75000, t2 = 125001 at salary 2,500,020
        # 75000 @100% + 50001 @50% (25000.5 -> 25001 half-up)
        self.assertEqual(match(plan, 2_500_020, 125_001), 100_001)

    def test_per_tier_rounding_half_up(self):
        # tier width 251 cents at 50% -> 125.5 cents rounds up to 126
        plan = Plan((Tier(0, 0), Tier(1, 5000)))
        self.assertEqual(match(plan, 2_510_000, 251), 126)

    def test_rounding_applies_per_tier_not_on_total(self):
        # two tiers of 251 cents each at 50% -> 126 + 126 = 252;
        # rounding the total instead would give 251
        plan = Plan((Tier(0, 0), Tier(1, 5000), Tier(2, 5000)))
        self.assertEqual(match(plan, 2_510_000, 502), 252)

    def test_deferral_beyond_last_tier_unmatched(self):
        plan = Plan((Tier(100, 10000),))
        self.assertEqual(match(plan, 2_500_000, 250_000), 25_000)

    def test_cap_applied_after_summation(self):
        plan = Plan((Tier(500, 10000),), cap_cents=100_000)
        self.assertEqual(match(plan, 2_500_000, 250_000), 100_000)

    def test_zero_deferral(self):
        self.assertEqual(match(basic_plan(), 2_500_000, 0), 0)

    def test_basic_formula_profile(self):
        basic = basic_plan()
        # salary 40,000,000: t1 = 1,200,000, t2 = 2,000,000
        self.assertEqual(match(basic, 40_000_000, 4_000_000), 1_600_000)

    def test_domain_validation(self):
        plan = basic_plan()
        with self.assertRaises(ValueError):
            match(plan, 2_499_999, 0)
        with self.assertRaises(ValueError):
            match(plan, 50_000_001, 0)
        with self.assertRaises(ValueError):
            match(plan, 2_500_000, -1)
        with self.assertRaises(ValueError):
            match(plan, 2_500_000, 250_001)  # > floor(10% of salary)


class PlanValidationTest(unittest.TestCase):
    def test_thresholds_must_be_strictly_increasing(self):
        with self.assertRaises(ValueError):
            Plan((Tier(300, 10000), Tier(300, 5000)))

    def test_threshold_bounded_by_1000_bps(self):
        with self.assertRaises(ValueError):
            Plan((Tier(1001, 10000),))

    def test_rate_bounded_by_10000_bps(self):
        with self.assertRaises(ValueError):
            Plan((Tier(300, 10001),))

    def test_negative_cap_rejected(self):
        with self.assertRaises(ValueError):
            Plan((Tier(300, 10000),), cap_cents=-1)


if __name__ == "__main__":
    unittest.main()
