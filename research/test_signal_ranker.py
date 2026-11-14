import unittest
from dataclasses import replace

from research.signal_ranker import Candidate, Example, STRATEGY, demo, evaluate, fit, shadow_rank, split


def candidate(name, at, trigger=2., volume=2., **kwargs):
    return Candidate(name, STRATEGY, at, at + 30, (trigger, volume, 20., 2.), **kwargs)


def training():
    return [Example(candidate(str(i), i, volume=float(i)), i + 1, float(i * 5), 1.) for i in range(1, 12)]


class RankerTest(unittest.TestCase):
    def test_ml_can_rerank_only_eligible_candidates(self):
        m = fit(training(), "fixture-v1")
        a = candidate("rules-first", 100, trigger=4., volume=1.)
        b = candidate("ml-first", 100, volume=10.)
        blocked = candidate("blocked", 100, volume=100., blocked_reasons=("spread",))
        stale = candidate("stale", 50, volume=100.)
        future = candidate("future", 101, volume=100.)
        bad = candidate("bad", 100, volume=float("nan"))
        result = shadow_rank([a, b, blocked, stale, future, bad], 100, m)
        self.assertEqual(result["baseline"], ["rules-first", "ml-first"])
        self.assertEqual(result["shadow"], ["ml-first", "rules-first"])
        self.assertEqual(result["mode"], "paper-shadow")

    def test_missing_or_future_model_keeps_baseline(self):
        a = candidate("a", 100)
        m = fit(training(), "fixture-v1")
        for model in (None, replace(m, trained_through=100)):
            self.assertEqual(shadow_rank([a], 100, model)["baseline"], ["a"])
            self.assertEqual(shadow_rank([a], 100, model)["shadow"], [])

    def test_split_purges_overlapping_labels(self):
        a = Example(candidate("before", 10), 15, 3., 1.)
        b = Example(candidate("overlap", 16), 20, 3., 1.)
        c = Example(candidate("after", 20), 25, 3., 1.)
        self.assertEqual(split([a, b, c], 20), ([a], [c]))
        with self.assertRaisesRegex(ValueError, "Holdout"):
            evaluate(training(), [a], "bad-split")

    def test_no_eligible_means_no_ranking(self):
        r = shadow_rank([candidate("expired", 100)], 130, fit(training(), "fixture-v1"))
        self.assertEqual((r["baseline"], r["shadow"]), ([], []))

    def test_demo_explicitly_synthetic_and_cannot_promote(self):
        r = demo()
        self.assertEqual(r["data"], "synthetic_example_only")
        self.assertEqual(r["promotion"], "not_evaluated")
        self.assertGreater(r["windows"], 0)


if __name__ == "__main__":
    unittest.main()
