import unittest

from brightledger import Plan, Tier, basic_plan, certify, match

SALARY_MIN = 2_500_000
SALARY_MAX = 50_000_000


class RequiredScenariosTest(unittest.TestCase):
    def test_four_percent_at_100_fails_with_minimal_counterexample(self):
        plan = Plan((Tier(400, 10000),))
        result = certify(plan, SALARY_MIN, SALARY_MAX)
        self.assertFalse(result.ok)
        ce = result.counterexample
        self.assertEqual(ce.salary, 2_500_020)
        self.assertEqual(ce.deferral, 125_001)
        self.assertEqual(ce.basic_amount, 100_001)
        self.assertEqual(ce.plan_amount, 100_000)
        # The counterexample must be reproducible through match().
        self.assertEqual(match(plan, ce.salary, ce.deferral), 100_000)
        self.assertEqual(match(basic_plan(), ce.salary, ce.deferral), 100_001)

    def test_five_percent_at_100_with_cap_passes(self):
        plan = Plan((Tier(500, 10000),), cap_cents=2_000_000)
        result = certify(plan, SALARY_MIN, SALARY_MAX)
        self.assertTrue(result.ok)
        self.assertIsNone(result.counterexample)

    def test_cap_reduced_by_one_cent_fails(self):
        plan = Plan((Tier(500, 10000),), cap_cents=1_999_999)
        result = certify(plan, SALARY_MIN, SALARY_MAX)
        self.assertFalse(result.ok)
        ce = result.counterexample
        self.assertEqual(ce.salary, 50_000_000)
        self.assertEqual(ce.deferral, 2_499_999)
        self.assertEqual(ce.basic_amount, 2_000_000)
        self.assertEqual(ce.plan_amount, 1_999_999)
        # Exactly one cent short, and reproducible through match().
        self.assertEqual(
            match(basic_plan(), ce.salary, ce.deferral)
            - match(plan, ce.salary, ce.deferral),
            1,
        )


class CounterexampleMinimalityTest(unittest.TestCase):
    def test_no_bad_deferral_below_returned_salary(self):
        plan = Plan((Tier(400, 10000),))
        result = certify(plan, SALARY_MIN, SALARY_MAX)
        ce = result.counterexample
        basic = basic_plan()
        for salary in range(SALARY_MIN, ce.salary):
            for deferral in (0, salary // 20, salary // 10):
                self.assertGreaterEqual(
                    match(plan, salary, deferral),
                    match(basic, salary, deferral),
                )

    def test_no_smaller_deferral_at_counterexample_salary(self):
        plan = Plan((Tier(400, 10000),))
        result = certify(plan, SALARY_MIN, SALARY_MAX)
        ce = result.counterexample
        basic = basic_plan()
        for deferral in range(ce.deferral):
            self.assertGreaterEqual(
                match(plan, ce.salary, deferral),
                match(basic, ce.salary, deferral),
            )


class CertifyEdgeCasesTest(unittest.TestCase):
    def test_basic_plan_certifies_against_itself(self):
        self.assertTrue(certify(basic_plan(), SALARY_MIN, 2_600_000).ok)

    def test_empty_plan_fails_immediately(self):
        result = certify(Plan(()), SALARY_MIN, SALARY_MAX)
        self.assertFalse(result.ok)
        self.assertEqual(result.counterexample.salary, SALARY_MIN)
        self.assertEqual(result.counterexample.deferral, 1)

    def test_subrange_certification(self):
        # The 4% plan is clean on this small prefix of the domain.
        plan = Plan((Tier(400, 10000),))
        self.assertTrue(certify(plan, SALARY_MIN, 2_500_019).ok)
        self.assertFalse(certify(plan, SALARY_MIN, 2_500_020).ok)

    def test_invalid_salary_interval_rejected(self):
        plan = basic_plan()
        with self.assertRaises(ValueError):
            certify(plan, SALARY_MIN - 1, SALARY_MAX)
        with self.assertRaises(ValueError):
            certify(plan, SALARY_MIN, SALARY_MAX + 1)
        with self.assertRaises(ValueError):
            certify(plan, 3_000_000, 2_900_000)


if __name__ == "__main__":
    unittest.main()
