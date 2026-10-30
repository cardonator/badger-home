"""Token Tapper rules and badge frame-loop regression tests."""

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


APP = Path(__file__).resolve().parents[1] / "badge/apps/token_tapper"
SPEC = importlib.util.spec_from_file_location("token_tapper_game", APP / "game.py")
rules = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rules)


def advance(game, seconds, dt=1 / 60):
    while seconds > 1e-8:
        elapsed = min(seconds, dt)
        game.step(elapsed)
        seconds -= elapsed


class GameTests(unittest.TestCase):
    def setUp(self):
        self.game = rules.Game()
        self.game.spawn_in = 100

    def test_controls_clamp_and_fire_cooldown(self):
        g = self.game
        g.move(-1)
        self.assertEqual(g.lane, 0)
        for _ in range(8):
            g.move(1)
        self.assertEqual(g.lane, 3)
        self.assertTrue(g.fire())
        self.assertFalse(g.fire())
        advance(g, 0.4)
        self.assertTrue(g.fire())
        self.assertEqual(len(g.tokens), 2)

    def test_delivery_creates_floating_commit_and_immediate_return(self):
        g = self.game
        g.patrons[0]["x"] = 100
        self.assertTrue(g.fire())
        advance(g, 0.25)
        self.assertEqual(g.score, 10)
        self.assertEqual(len(g.commits), 1)
        self.assertEqual(g.commits[0]["lane"], 0)
        self.assertEqual(len(g.returns), 1)
        self.assertEqual(g.pending_commits, 0)
        self.assertEqual(g.token_stock, g.shift_budget - 1)
        self.assertEqual(g.returns[0]["delay"], 0)
        self.assertLess(g.returns[0]["x"], g.commits[0]["x"])
        self.assertTrue(g.patrons[0]["leaving"])
        self.assertEqual(g.patrons[0]["rest"], 0)
        self.assertLess(g.commits[0]["x"], g.patrons[0]["x"])
        self.assertGreater(g.commits[0]["age"], 0)
        advance(g, 1.4)
        self.assertEqual(g.commits, [])

    def test_earliest_patron_in_lane_gets_token(self):
        g = self.game
        g.patrons[0]["x"] = 180
        g.spawn(0)
        g.spawn(1)
        g.patrons[-1]["x"] = 90
        g.fire()
        advance(g, 0.65)
        self.assertTrue(g.patrons[0]["leaving"])
        self.assertFalse(g.patrons[1]["leaving"])
        self.assertFalse(g.patrons[2]["leaving"])
        self.assertEqual(g.score, 10)

    def test_departure_and_catch_score(self):
        g = self.game
        g.fire()
        advance(g, 1.5)
        self.assertEqual(g.served, 1)
        self.assertEqual(g.score, 35)
        self.assertEqual(len(g.returns), 1)
        advance(g, 1.6)
        self.assertEqual(g.returns, [])
        self.assertEqual(g.score, 40)
        self.assertEqual(g.lives, 3)
        self.assertEqual(g.pending_commits, 1)
        self.assertEqual(g.token_stock, g.shift_budget - 1)

    def test_missing_commit_loses_one_life_and_preserves_play(self):
        g = self.game
        g.lane = 1
        g.returns = [
            {"x": 49, "lane": 0, "delay": 0},
            {"x": 200, "lane": 2, "delay": 0},
        ]
        g.pending_commits = 2
        g.token_stock = 5
        advance(g, 0.1)
        self.assertEqual(g.lives, 2)
        self.assertEqual(len(g.returns), 1)
        self.assertEqual(len(g.patrons), 1)
        self.assertEqual(g.recovery, 0)
        self.assertEqual(g.pending_commits, 2)
        self.assertEqual(g.token_stock, 5)
        self.assertTrue(g.fire())
        self.assertIn("DROPPED", g.message)

    def test_empty_lane_shot_and_patron_at_tap_cost_lives(self):
        g = self.game
        g.patrons.clear()
        g.fire()
        advance(g, 1.4)
        self.assertEqual(g.lives, 2)
        self.assertEqual(g.message, "TOKEN WASTED!")
        g.recovery = 0
        g.spawn(0)
        g.patrons[0]["x"] = 58.01
        g.step(0.1)
        self.assertEqual(g.lives, 1)
        self.assertIn("TOO MANY AGENTS", g.message)
        self.assertTrue(g.overloaded)
        self.assertGreater(g.recovery, 0)
        g.miss("last life")
        self.assertTrue(g.over)
        self.assertFalse(g.fire())
        advance(g, 10)
        self.assertEqual(g.lives, 0)
        self.assertEqual(g.patrons, [])

    def test_pacing_ramps_and_spawn_does_not_overlap(self):
        g = self.game
        for lane in (1, 2, 3):
            g.spawn(lane)
        g.spawn()
        self.assertEqual(len(g.patrons), 4)
        g.served = 8
        self.assertEqual(g.level, 1)
        self.assertEqual(g.merge_goal, 2)

    def test_frame_rate_independent_movement_and_collisions(self):
        slow, fast = rules.Game(), rules.Game()
        for g in (slow, fast):
            g.spawn_in = 100
            g.patrons[0]["x"] = 120
            g.fire()
        with patch.object(rules.random, "randrange", return_value=2):
            advance(slow, 0.6, 0.2)
            advance(fast, 0.6, 1 / 120)
        self.assertEqual(slow.score, fast.score)
        self.assertEqual(slow.lives, fast.lives)
        self.assertAlmostEqual(
            slow.patrons[0]["x"], fast.patrons[0]["x"],
            delta=rules.DEPARTURE_SPEED / 60,
        )
        self.assertAlmostEqual(slow.returns[0]["x"], fast.returns[0]["x"], delta=2)
        advance(slow, 0.4, 0.2)
        advance(fast, 0.4, 1 / 120)
        self.assertEqual(slow.pending_commits, 1)
        self.assertEqual(fast.pending_commits, 1)
        self.assertEqual(slow.score, fast.score)

    def test_token_stock_is_spent_only_for_successful_toss(self):
        g = self.game
        g.token_stock = 1
        self.assertTrue(g.fire())
        self.assertEqual(g.token_stock, 0)
        g.cooldown = 0
        self.assertFalse(g.fire())
        self.assertEqual(g.token_stock, 0)
        self.assertEqual(len(g.tokens), 1)
        self.assertIn("OUT OF TOKENS", g.message)
        g.pending_commits = 4
        self.assertFalse(g.fire())
        self.assertIn("LEFT TO MERGE", g.message)

    def test_merge_requires_station_and_four_collected_commits(self):
        g = self.game
        g.pending_commits = 4
        self.assertFalse(g.merge())
        g.visit_station()
        g.pending_commits = 3
        self.assertFalse(g.merge())
        self.assertIn("1 MORE", g.message)
        g.pending_commits = 6
        g.token_stock = 0
        self.assertTrue(g.merge())
        self.assertFalse(g.merge())
        advance(g, 0.4)
        self.assertEqual(g.token_stock, 0)
        self.assertEqual(g.pending_commits, 6)
        advance(g, 0.4)
        self.assertEqual(g.token_stock, 4)
        self.assertEqual(g.pending_commits, 2)
        self.assertEqual(g.merges, 1)
        self.assertTrue(g.at_station)
        self.assertEqual(g.tokens, [])
        self.assertFalse(g.fire())
        advance(g, 1)
        self.assertEqual(g.token_stock, 4)
        self.assertEqual(g.merges, 1)
        g.leave_station()
        self.assertTrue(g.fire())

    def test_station_stops_serving_and_catching_but_not_patrons(self):
        g = self.game
        g.visit_station()
        g.move(1)
        self.assertEqual(g.lane, 0)
        self.assertFalse(g.fire())
        x = g.patrons[0]["x"]
        advance(g, 0.5)
        self.assertLess(g.patrons[0]["x"], x)
        g.returns = [{"lane": 0, "x": 49, "delay": 0}]
        advance(g, 0.1)
        self.assertEqual(g.lives, 2)
        self.assertEqual(g.pending_commits, 0)
        self.assertTrue(g.at_station)
        self.assertEqual(g.recovery, 0)

    def test_cancel_merge_keeps_resources_and_lane(self):
        g = self.game
        g.lane = 2
        g.pending_commits = 4
        g.visit_station()
        self.assertTrue(g.merge())
        advance(g, 0.4)
        g.leave_station()
        advance(g, 1)
        self.assertEqual(g.lane, 2)
        self.assertEqual(g.pending_commits, 4)
        self.assertEqual(g.token_stock, g.shift_budget)
        self.assertEqual(g.merges, 0)
        self.assertEqual(g.merge_remaining, 0)

    def test_life_recovery_restarts_economy_without_free_merge(self):
        g = self.game
        g.token_stock = 0
        g.pending_commits = 4
        g.visit_station()
        g.merge()
        g.miss("test recovery")
        self.assertEqual(g.token_stock, g.shift_budget)
        self.assertEqual(g.pending_commits, 0)
        self.assertEqual(g.merge_remaining, 0)
        g.visit_station()
        self.assertFalse(g.at_station)
        self.assertFalse(g.merge())
        advance(g, 2)
        self.assertEqual(g.merges, 0)
        self.assertEqual(g.token_stock, g.shift_budget)

    def test_in_flight_wasted_shot_cancels_active_merge_without_reward(self):
        g = self.game
        g.patrons.clear()
        g.pending_commits = 4
        g.shift_merges = 1
        g.merges = 1
        g.score = 80
        self.assertTrue(g.fire())
        advance(g, 0.6)
        g.visit_station()
        self.assertTrue(g.merge())
        advance(g, 0.3)
        self.assertEqual(len(g.tokens), 1)
        self.assertGreater(g.merge_remaining, 0)
        advance(g, 0.2)
        self.assertEqual(g.message, "TOKEN WASTED!")
        self.assertEqual(g.lives, 2)
        self.assertEqual(g.tokens, [])
        self.assertFalse(g.at_station)
        self.assertEqual(g.merge_remaining, 0)
        self.assertEqual(g.pending_commits, 0)
        self.assertEqual(g.token_stock, 6)
        self.assertEqual(g.shift_merges, 1)
        self.assertEqual(g.merges, 1)
        self.assertEqual(g.score, 80)
        advance(g, 2)
        self.assertEqual(g.merges, 1)
        self.assertEqual(g.token_stock, 6)
        self.assertEqual(g.score, 80)

    def test_actual_four_deliveries_merge_and_refill_four_tokens(self):
        g = self.game
        for _ in range(4):
            g.spawn_in = 100
            g.patrons.clear()
            g.spawn(0)
            self.assertTrue(g.fire())
            advance(g, 4.5)
        self.assertEqual(g.pending_commits, 4)
        self.assertEqual(g.token_stock, 6)
        self.assertEqual(g.lives, 3)
        g.visit_station()
        self.assertTrue(g.merge())
        advance(g, 1)
        self.assertEqual(g.pending_commits, 0)
        self.assertEqual(g.token_stock, 10)
        self.assertEqual(g.shift_merges, 1)
        self.assertEqual(g.level, 1)
        g.leave_station()
        self.assertTrue(g.fire())
        self.assertEqual(g.token_stock, 9)

    def test_nearby_patron_sends_one_commit_then_leaves_fully(self):
        g = self.game
        p = g.patrons[0]
        p["x"] = 80
        g.fire()
        advance(g, 0.15)
        self.assertTrue(p["leaving"])
        self.assertEqual(len(g.returns), 1)
        self.assertEqual(p["rest"], 0)
        x = p["x"]
        g.receive(p)
        self.assertEqual(g.score, 10)
        self.assertEqual(len(g.returns), 1)
        advance(g, 0.3)
        self.assertGreater(p["x"], x)
        advance(g, 0.4)
        self.assertGreater(p["x"], x)
        advance(g, 2)
        self.assertNotIn(p, g.patrons)
        self.assertGreaterEqual(p["x"], rules.PATRON_EXIT)
        self.assertEqual(g.served, 1)
        self.assertEqual(g.score, 40)
        self.assertEqual(g.pending_commits, 1)
        self.assertEqual(g.lives, 3)

    def test_token_ignores_departing_patron_and_serves_next(self):
        g = self.game
        first = g.patrons[0]
        first["x"] = 180
        g.receive(first)
        g.spawn(0)
        second = g.patrons[1]
        second["x"] = 150
        g.fire()
        advance(g, 0.5)
        self.assertTrue(second["leaving"])
        self.assertEqual(len(g.returns), 2)
        self.assertEqual(g.score, 20)
        self.assertEqual(g.token_stock, 9)

    def test_drop_during_merge_preserves_resources_and_finishes(self):
        g = self.game
        g.pending_commits = 6
        g.token_stock = 2
        g.visit_station()
        g.merge()
        advance(g, 0.2)
        remaining = g.merge_remaining
        g.returns = [{"lane": 0, "x": 49, "delay": 0}]
        advance(g, 0.1)
        self.assertEqual(g.lives, 2)
        self.assertTrue(g.at_station)
        self.assertEqual(g.pending_commits, 6)
        self.assertEqual(g.token_stock, 2)
        self.assertGreater(g.merge_remaining, 0)
        self.assertLess(g.merge_remaining, remaining)
        self.assertEqual(g.recovery, 0)
        advance(g, 0.6)
        self.assertEqual(g.pending_commits, 2)
        self.assertEqual(g.token_stock, 6)
        self.assertEqual(g.merges, 1)
        self.assertTrue(g.at_station)

    def test_last_life_drop_ends_merge_without_reward(self):
        g = self.game
        g.pending_commits = 4
        g.token_stock = 2
        g.lives = 1
        g.visit_station()
        g.merge()
        g.returns = [{"lane": 0, "x": 49, "delay": 0}]
        advance(g, 1)
        self.assertTrue(g.over)
        self.assertEqual(g.merge_remaining, 0)
        self.assertEqual(g.pending_commits, 4)
        self.assertEqual(g.token_stock, 2)
        self.assertEqual(g.merges, 0)

    def test_multiple_drops_cost_one_life_each(self):
        g = self.game
        g.visit_station()
        g.returns = [{"lane": i, "x": 49, "delay": 0} for i in range(3)]
        advance(g, 0.1)
        self.assertEqual(g.lives, 0)
        self.assertEqual(g.returns, [])
        self.assertEqual(g.recovery, 0)

    def test_overload_freezes_bar_and_merge_for_three_seconds_without_reset(self):
        g = self.game
        g.pending_commits = 4
        g.token_stock = 1
        g.visit_station()
        g.merge()
        g.spawn(1)
        g.returns = [{"lane": 1, "x": 180, "delay": 0, "speed": 114}]
        g.tokens = [{"lane": 2, "x": 90}]
        g.commits = [{"lane": 1, "x": 180, "age": 0}]
        g.patrons[0]["x"] = rules.COUNTER + 10.01
        g.step(1 / 60)
        self.assertEqual(g.lives, 2)
        self.assertTrue(g.overloaded)
        self.assertIn("TOO MANY AGENTS", g.message)
        self.assertTrue(g.at_station)
        self.assertEqual(g.recovery, 3)
        self.assertEqual(g.token_stock, 1)
        self.assertEqual(g.pending_commits, 4)
        self.assertEqual(len(g.patrons), 1)
        snapshot = (g.patrons[0]["x"], g.returns[0]["x"], g.tokens[0]["x"],
                    g.commits[0]["age"], g.merge_remaining, g.spawn_in)
        g.leave_station()
        self.assertTrue(g.at_station)
        self.assertFalse(g.fire())
        advance(g, 2.9)
        self.assertEqual(snapshot, (g.patrons[0]["x"], g.returns[0]["x"], g.tokens[0]["x"],
                                   g.commits[0]["age"], g.merge_remaining, g.spawn_in))
        advance(g, 0.2)
        self.assertEqual(g.recovery, 0)
        self.assertLess(g.merge_remaining, snapshot[4])
        g.leave_station()
        self.assertTrue(g.fire())

    def test_agents_already_at_tap_share_one_overload_incident(self):
        g = self.game
        g.spawn(1)
        g.spawn(2)
        for patron in g.patrons[:2]:
            patron["x"] = rules.COUNTER + 10
        survivor = g.patrons[2]
        g.step(1 / 60)
        self.assertEqual(g.lives, 2)
        self.assertEqual(g.recovery, 3)
        self.assertEqual(g.patrons, [survivor])
        advance(g, 3.2)
        self.assertEqual(g.lives, 2)
        self.assertEqual(g.recovery, 0)
        self.assertEqual(g.patrons, [survivor])

    def test_delivery_starts_effect_and_return_in_same_step(self):
        g = self.game
        p = g.patrons[0]
        p["x"] = 180
        g.tokens = [{"lane": 0, "x": p["x"] - 10}]
        g.step(1 / 120)
        self.assertEqual(len(g.commits), 1)
        self.assertEqual(len(g.returns), 1)
        self.assertEqual(g.commits[0]["age"], 0)
        self.assertEqual(g.returns[0]["delay"], 0)
        self.assertLess(g.returns[0]["x"], g.commits[0]["x"])
        self.assertTrue(p["leaving"])
        self.assertEqual(p["rest"], 0)
        x = p["x"]
        g.step(1 / 120)
        self.assertGreater(p["x"], x)

    def test_extra_catch_is_lost_and_penalized_until_merging(self):
        g = self.game
        g.pending_commits = 3
        g.returns = [{"lane": 0, "x": 49, "delay": 0}]
        g.step(1 / 60)
        self.assertEqual(g.pending_commits, 4)
        self.assertEqual(g.score, 5)
        self.assertIn("MERGE READY", g.message)
        g.returns = [{"lane": 0, "x": 49, "delay": 0}]
        g.score = 100
        g.step(1 / 60)
        self.assertEqual(g.pending_commits, 4)
        self.assertEqual(g.score, 90)
        self.assertEqual(g.message, "Commit lost! You need to merge!")
        self.assertEqual(g.returns, [])
        self.assertEqual(g.token_stock, 10)
        g.visit_station()
        g.merge()
        advance(g, 0.9)
        self.assertEqual(g.pending_commits, 0)
        self.assertEqual(g.token_stock, 14)
        self.assertEqual(g.shift_merges, 1)
        g.leave_station()
        g.returns = [{"lane": 0, "x": 49, "delay": 0}]
        g.step(1 / 60)
        self.assertEqual(g.score, 145)
        self.assertEqual(g.pending_commits, 1)
        self.assertIn("COMMIT CAUGHT", g.message)

    def test_multiple_lost_commits_cost_points_but_not_lives_or_tokens(self):
        g = self.game
        g.score = 100
        g.pending_commits = 4
        g.returns = [{"lane": 0, "x": 49, "delay": 0} for _ in range(3)]
        g.step(1 / 60)
        self.assertEqual(g.score, 70)
        self.assertEqual(g.pending_commits, 4)
        self.assertEqual(g.lives, 3)
        self.assertEqual(g.token_stock, 10)
        g.score = 5
        g.returns = [{"lane": 0, "x": 49, "delay": 0}]
        g.step(1 / 60)
        self.assertEqual(g.score, 0)

    def test_opening_pace_meets_faster_timing_targets(self):
        g = rules.Game()
        self.assertEqual(g.spawn_in, 1.4)
        start = g.patrons[0]["x"]
        advance(g, 1)
        self.assertAlmostEqual(start - g.patrons[0]["x"], 16)
        advance(g, 0.5)
        self.assertEqual(len(g.patrons), 2)
        self.assertGreater(g.spawn_in, 2)
        self.assertLessEqual(g.spawn_in, 2.15)
        g.spawn_in = 100
        g.patrons.clear()
        g.spawn(0)
        g.fire()
        advance(g, 0.29)
        self.assertAlmostEqual(g.tokens[0]["x"] - rules.COUNTER, 260 * 0.29)
        self.assertTrue(g.fire())
        g.tokens.clear()
        g.receive(g.patrons[0])
        returned = g.returns[0]
        start = returned["x"]
        advance(g, 0.5)
        self.assertAlmostEqual(start - returned["x"], returned["speed"] * 0.5)

    def test_return_speed_is_chosen_once_from_five_close_paces(self):
        g = self.game
        for pace in range(5):
            g.patrons.clear()
            g.spawn(0)
            with patch.object(rules.random, "randrange", return_value=pace):
                g.receive(g.patrons[0])
            returned = g.returns[-1]
            self.assertEqual(returned["speed"], 108 + pace * 6)
            start = returned["x"]
            g.step(0.1)
            self.assertAlmostEqual(start - returned["x"], returned["speed"] * 0.1)
            self.assertEqual(returned["speed"], 108 + pace * 6)

    def test_shift_goals_and_budgets_scale_together(self):
        g = self.game
        for level, goal, budget in ((1, 2, 10), (2, 3, 14), (3, 4, 18), (5, 6, 26), (20, 6, 26)):
            with self.subTest(level=level):
                g.level = level
                self.assertEqual(g.merge_goal, goal)
                self.assertEqual(g.shift_budget, budget)
                self.assertEqual(budget - goal * rules.MERGE_COMMITS, 2)

    def test_catches_and_departures_cannot_advance_shift_without_merging(self):
        g = self.game
        g.pending_commits = 20
        g.served = 100
        advance(g, 1)
        self.assertEqual(g.level, 1)
        self.assertEqual(g.shift_merges, 0)
        self.assertEqual(g.stage, "serving")
        self.assertFalse(g.next_shift())

    def test_goal_stops_arrivals_and_safely_clears_all_hazards(self):
        g = self.game
        g.shift_merges = g.merge_goal - 1
        g.pending_commits = 4
        g.token_stock = 2
        g.visit_station()
        g.merge()
        advance(g, 0.7)
        p = g.patrons[0]
        p["x"] = 60
        g.tokens = [{"lane": 2, "x": 315}]
        g.returns = [{"lane": 1, "x": 49, "delay": 10}]
        # Place hazards just before completion without letting them resolve first.
        g.merge_remaining = 0.001
        g.step(1 / 60)
        self.assertEqual(g.stage, "clearing")
        self.assertEqual(g.shift_merges, g.merge_goal)
        self.assertEqual(g.tokens, [])
        self.assertEqual(g.returns, [])
        self.assertTrue(p["leaving"])
        self.assertEqual(g.lives, 3)
        self.assertFalse(g.fire())
        self.assertFalse(g.merge())
        g.visit_station()
        self.assertFalse(g.at_station)
        g.spawn()
        self.assertEqual(len(g.patrons), 1)
        self.assertFalse(g.next_shift())
        advance(g, 1.4)
        self.assertEqual(g.stage, "break")
        self.assertEqual(g.patrons, [])
        self.assertGreaterEqual(p["x"], rules.PATRON_EXIT)
        self.assertEqual(g.served, 0)
        self.assertEqual(g.score, 50)
        self.assertEqual(g.token_stock, 6)
        self.assertEqual(g.level, 1)
        score = g.score
        advance(g, 30)
        self.assertEqual(g.stage, "break")
        self.assertEqual(g.score, score)
        self.assertEqual(g.lives, 3)

    def test_next_shift_refreshes_supplies_not_lives_or_score(self):
        g = self.game
        g.shift_merges = g.merge_goal
        g.pending_commits = 5
        g.token_stock = 1
        g.score = 123
        g.lives = 2
        g.merges = 2
        g.clear_shift()
        advance(g, 1)
        self.assertEqual(g.stage, "break")
        self.assertTrue(g.next_shift())
        self.assertEqual(g.level, 2)
        self.assertEqual(g.merge_goal, 3)
        self.assertEqual(g.token_stock, 14)
        self.assertEqual(g.pending_commits, 0)
        self.assertEqual(g.shift_merges, 0)
        self.assertEqual(g.merges, 2)
        self.assertEqual(g.lives, 2)
        self.assertEqual(g.score, 123)
        self.assertEqual(g.stage, "serving")
        self.assertEqual(len(g.patrons), 1)
        self.assertFalse(g.next_shift())
        self.assertEqual(g.level, 2)

    def test_reboot_keeps_completed_merges_and_budgets_remaining_work(self):
        g = self.game
        g.shift_merges = 1
        g.merges = 1
        g.token_stock = 0
        g.pending_commits = 2
        g.miss("test reboot")
        self.assertEqual(g.lives, 2)
        self.assertEqual(g.shift_merges, 1)
        self.assertEqual(g.merges, 1)
        self.assertEqual(g.level, 1)
        self.assertEqual(g.token_stock, 6)
        self.assertEqual(g.pending_commits, 0)
        self.assertEqual(g.stage, "serving")

    def test_full_shift_with_two_drops_is_still_completable(self):
        g = self.game
        for shot in range(10):
            g.spawn_in = 100
            g.patrons.clear()
            g.spawn(0)
            # Fire in the patron's lane, then intentionally miss the first two returns.
            g.lane = 0
            self.assertTrue(g.fire())
            if shot < 2:
                g.lane = 1
            advance(g, 3.1)
            if shot in (5, 9):
                g.visit_station()
                self.assertTrue(g.merge())
                advance(g, 0.9)
                g.leave_station()
        advance(g, 2)
        self.assertEqual(g.lives, 1)
        self.assertEqual(g.merges, 2)
        self.assertEqual(g.shift_merges, 2)
        self.assertEqual(g.stage, "break")
        self.assertEqual(g.token_stock, 8)
        self.assertTrue(g.next_shift())
        self.assertEqual(g.token_stock, 14)
        self.assertEqual(g.lives, 1)

    def test_three_full_shifts_have_exact_budgets_and_merge_quotas(self):
        g = self.game
        total_merges = 0
        for level in range(1, 4):
            self.assertEqual(g.level, level)
            goal = g.merge_goal
            self.assertEqual(g.token_stock, goal * 4 + 2)
            for batch in range(goal):
                for _ in range(4):
                    g.spawn_in = 100
                    g.patrons.clear()
                    g.spawn(0)
                    self.assertTrue(g.fire())
                    advance(g, 3.1)
                self.assertEqual(g.pending_commits, 4)
                self.assertEqual(g.stage, "serving")
                g.visit_station()
                self.assertTrue(g.merge())
                advance(g, 0.9)
                total_merges += 1
                self.assertEqual(g.shift_merges, batch + 1)
                self.assertEqual(g.merges, total_merges)
                self.assertEqual(g.token_stock, goal * 4 + 2)
                g.leave_station()
            advance(g, 2)
            self.assertEqual(g.stage, "break")
            self.assertEqual(g.lives, 3)
            self.assertEqual(g.token_stock, goal * 4 + 2)
            self.assertTrue(g.next_shift())
        self.assertEqual(total_merges, 9)
        self.assertEqual(g.score, 1890)
        self.assertEqual(g.level, 4)
        self.assertEqual(g.token_stock, 22)


class FakeScreen:
    width = 320
    height = 240

    def __init__(self):
        self.labels = []

    def shape(self, value):
        pass

    def text(self, label, x, y):
        self.labels.append((label, x, y))

    def blit(self, *args):
        pass

    def line(self, *args):
        pass

    def measure_text(self, label):
        return len(label) * 7, 13


class FrameTests(unittest.TestCase):
    def setUp(self):
        self.pressed = set()
        self.held = set()
        self.saved = []
        self.sprite_calls = []
        self.sheet_calls = []
        self.sprite = types.SimpleNamespace(width=28, height=24)
        state = types.SimpleNamespace(
            load=lambda key, record: None,
            save=lambda key, record: self.saved.append((key, dict(record))),
        )
        self.badge = types.SimpleNamespace(
            ticks_delta=16, mode=lambda mode: None,
            pressed=lambda key: key in self.pressed,
            held=lambda key: key in self.held,
        )
        self.env = {
            "badge": self.badge, "screen": FakeScreen(),
            "font": types.SimpleNamespace(nope=0, ziplock=1),
            "image": types.SimpleNamespace(OFF=0, load=lambda path: self),
            "rect": lambda *args: args,
            "color": types.SimpleNamespace(rgb=lambda *args: args),
            "shape": types.SimpleNamespace(rectangle=lambda *args: args),
            "run": lambda callback: None, "HIRES": 1, "VSYNC": 2,
        }
        for name in ("SELECT", "UP", "DOWN", "LEFT", "RIGHT", "BACK", "MENU"):
            self.env["BUTTON_" + name] = name
        with patch.dict(sys.modules, {"game": rules, "badgeware": types.SimpleNamespace(State=state)}):
            with patch("os.chdir"), patch.object(sys, "path", list(sys.path)):
                exec(compile((APP / "__init__.py").read_text(), str(APP / "__init__.py"), "exec"), self.env)

    def spritesheet(self, columns, rows):
        self.sheet_calls.append((columns, rows))
        return types.SimpleNamespace(sprite=self.sprite_frame)

    def sprite_frame(self, x, y):
        self.sprite_calls.append((x, y))
        return self.sprite

    def frame(self, *buttons):
        self.pressed = set(buttons)
        self.held = set(buttons)
        self.env["update"]()

    def test_title_uses_opening_rules_even_after_later_shift(self):
        opening = rules.Game()
        expected = "SHIFT 1: %d merges / %d tokens" % (opening.merge_goal, opening.shift_budget)
        self.frame()
        self.assertIn(expected, [label for label, _, _ in self.env["screen"].labels])
        self.env["game"].level = 5
        self.env["screen"].labels.clear()
        self.frame()
        self.assertIn(expected, [label for label, _, _ in self.env["screen"].labels])
        self.env["OPENING_MERGE_GOAL"] = 3
        self.env["OPENING_TOKEN_BUDGET"] = 14
        self.env["screen"].labels.clear()
        self.frame()
        self.assertIn("SHIFT 1: 3 merges / 14 tokens",
                      [label for label, _, _ in self.env["screen"].labels])

    def test_start_move_shoot_and_pause_resume_without_shooting(self):
        self.frame("SELECT")
        self.assertEqual(self.env["phase"], "play")
        self.assertEqual(self.env["game"].tokens, [])
        self.frame("DOWN")
        self.assertEqual(self.env["game"].lane, 1)
        self.frame("SELECT")
        self.assertEqual(len(self.env["game"].tokens), 1)
        self.frame("BACK")
        self.assertEqual(self.env["phase"], "pause")
        x = self.env["game"].tokens[0]["x"]
        self.frame()
        self.assertEqual(self.env["game"].tokens[0]["x"], x)
        self.frame("SELECT")
        self.assertEqual(self.env["phase"], "play")
        self.assertEqual(len(self.env["game"].tokens), 1)
        self.frame("MENU")
        self.assertEqual(self.env["phase"], "pause")
        self.frame("BACK")
        self.assertEqual(self.env["phase"], "play")

    def test_game_over_saves_once_and_restart_and_title_work(self):
        self.frame("SELECT")
        g = self.env["game"]
        g.score = 80
        g.lives = 0
        self.frame()
        self.assertEqual(self.env["phase"], "over")
        self.assertEqual(self.saved, [("token_tapper", {"highscore": 80})])
        self.frame()
        self.assertEqual(len(self.saved), 1)
        self.frame("SELECT")
        self.assertEqual(self.env["phase"], "play")
        self.assertEqual(self.env["game"].lives, 3)
        self.env["game"].lives = 0
        self.frame()
        self.frame("BACK")
        self.assertEqual(self.env["phase"], "title")

    def test_failed_high_score_save_is_visible(self):
        self.frame("SELECT")
        self.env["game"].score = 25
        self.env["game"].lives = 0
        with patch.object(self.env["State"], "save", side_effect=OSError("disk full")):
            with patch("builtins.print") as logged:
                self.frame()
        self.assertTrue(self.env["save_error"])
        logged.assert_called_once()

    def test_merge_controls_and_pause_freeze_resource_transaction(self):
        self.frame("SELECT")
        g = self.env["game"]
        g.pending_commits = 4
        self.frame("LEFT")
        self.assertTrue(g.at_station)
        self.frame("SELECT")
        self.assertGreater(g.merge_remaining, 0)
        self.assertEqual(g.tokens, [])
        self.frame("BACK")
        remaining = g.merge_remaining
        self.badge.ticks_delta = 200
        self.frame()
        self.assertEqual(g.merge_remaining, remaining)
        self.frame("SELECT")
        self.assertEqual(g.merge_remaining, remaining)
        for _ in range(5):
            self.frame()
        self.assertEqual(g.token_stock, 14)
        self.assertEqual(g.pending_commits, 0)
        self.frame("RIGHT")
        self.assertFalse(g.at_station)
        self.frame("SELECT")
        self.assertEqual(g.token_stock, 13)

    def test_mona_animation_uses_eleven_complete_frames(self):
        import struct

        data = (APP / "assets/mona.png").read_bytes()
        width, height = struct.unpack(">II", data[16:24])
        self.assertEqual((width, height), (308, 24))
        self.assertEqual(self.sheet_calls, [(11, 1)])
        self.frame("SELECT")
        for _ in range(130):
            self.env["animation"] += 0.1
            self.frame()
        self.assertEqual({frame for frame, _ in self.sprite_calls}, set(range(11)))

    def test_agent_bots_fit_existing_patron_envelope_in_both_states(self):
        for style in range(4):
            for happy in (False, True):
                with self.subTest(style=style, happy=happy):
                    boxes = []
                    self.env["animation"] = 0
                    with patch.dict(self.env, {"box": lambda *args: boxes.append(args)}):
                        self.env["patron"](160, 114, style, happy)
                    for x, y, width, height, _ in boxes:
                        self.assertGreaterEqual(x, 147)
                        self.assertLessEqual(x + width, 173)
                        self.assertGreaterEqual(y, 91)
                        self.assertLessEqual(y + height, 126)
                    self.assertIn((153, 99, 14, 8, self.env["INK"]), boxes)
                    self.assertIn((155, 113, 10, 7, self.env["INK"]), boxes)
                    signal = self.env["MINT"] if happy else self.env["CREAM"]
                    self.assertIn((158, 92, 4, 3, signal), boxes)

    def test_drop_does_not_interrupt_merge_in_frame_loop(self):
        self.frame("SELECT")
        g = self.env["game"]
        g.pending_commits = 4
        self.frame("LEFT")
        self.frame("SELECT")
        g.returns = [{"lane": 0, "x": 49, "delay": 0}]
        self.frame()
        self.assertEqual(g.lives, 2)
        self.assertEqual(self.env["phase"], "play")
        self.assertTrue(g.at_station)
        self.assertGreater(g.merge_remaining, 0)
        self.badge.ticks_delta = 200
        for _ in range(5):
            self.frame()
        self.assertEqual(g.merges, 1)
        self.assertEqual(g.token_stock, 14)
        self.assertEqual(g.pending_commits, 0)

    def test_fatal_drop_during_merge_shows_results(self):
        self.frame("SELECT")
        g = self.env["game"]
        g.lives = 1
        g.pending_commits = 4
        self.frame("LEFT")
        self.frame("SELECT")
        g.returns = [{"lane": 0, "x": 49, "delay": 0}]
        self.frame()
        self.assertEqual(self.env["phase"], "over")
        self.assertEqual(g.merges, 0)
        self.assertEqual(g.token_stock, 10)

    def test_patron_exit_position_is_completely_outside_display(self):
        self.assertGreater(self.env["field_x"](rules.PATRON_EXIT) - 13, 320)

    def test_intermission_select_starts_next_shift_without_tossing(self):
        self.frame("SELECT")
        g = self.env["game"]
        g.shift_merges = 1
        g.pending_commits = 4
        g.token_stock = 2
        self.frame("LEFT")
        self.frame("SELECT")
        self.badge.ticks_delta = 200
        for _ in range(10):
            self.frame()
        self.assertEqual(g.stage, "break")
        self.assertEqual(g.token_stock, 6)
        self.assertIn("SHIFT COMPLETE", [label for label, _, _ in self.env["screen"].labels])
        self.frame("BACK")
        self.frame("SELECT")
        self.assertEqual(g.stage, "break")
        self.assertEqual(self.env["phase"], "play")
        self.frame("SELECT")
        self.assertEqual(g.level, 2)
        self.assertEqual(g.token_stock, 14)
        self.assertEqual(g.tokens, [])
        self.assertEqual(g.shift_merges, 0)
        self.assertIn("MERGES 0/3", [label for label, _, _ in self.env["screen"].labels])
        for label, x, y in self.env["screen"].labels:
            with self.subTest(label=label):
                self.assertGreaterEqual(x, 0)
                self.assertLessEqual(x + len(label) * 7, 320)
                self.assertLessEqual(y + 13, 240)

    def test_title_game_station_and_results_text_fit_screen(self):
        self.frame()
        self.frame("SELECT")
        self.frame()
        self.frame("LEFT")
        self.frame("SELECT")
        self.frame("BACK")
        self.frame("SELECT")
        g = self.env["game"]
        g.patrons[0]["x"] = rules.COUNTER + 10.01
        self.frame()
        self.assertTrue(g.overloaded)
        self.assertIn("Too many agents", [label for label, _, _ in self.env["screen"].labels])
        self.assertIn("Resuming in 3...", [label for label, _, _ in self.env["screen"].labels])
        self.env["game"].lives = 0
        self.frame()
        for label, x, y in self.env["screen"].labels:
            with self.subTest(label=label):
                self.assertGreaterEqual(x, 0)
                self.assertLessEqual(x + len(label) * 7, 320)
                self.assertGreaterEqual(y, 0)
                self.assertLessEqual(y + 13, 240)

    def test_overload_countdown_freezes_controls_and_resumes_without_menu(self):
        self.frame("SELECT")
        g = self.env["game"]
        g.spawn_in = 100
        g.spawn(1)
        g.patrons[0]["x"] = 58
        self.frame()
        self.assertEqual(self.env["phase"], "play")
        self.assertEqual(g.lives, 2)
        x = g.patrons[0]["x"]
        animation = self.env["animation"]
        self.badge.ticks_delta = 200
        for _ in range(5):
            self.frame("DOWN", "LEFT", "SELECT")
        self.assertEqual(g.lane, 0)
        self.assertFalse(g.at_station)
        self.assertEqual(g.tokens, [])
        self.assertEqual(g.patrons[0]["x"], x)
        self.assertEqual(self.env["animation"], animation)
        self.assertAlmostEqual(g.recovery, 2)
        self.frame("BACK")
        remaining = g.recovery
        self.frame()
        self.frame("SELECT")
        self.assertEqual(g.recovery, remaining)
        self.env["screen"].labels.clear()
        self.frame()
        self.assertIn("Resuming in 2...", [label for label, _, _ in self.env["screen"].labels])
        for _ in range(11):
            self.frame()
        self.assertEqual(g.recovery, 0)
        self.assertLess(g.patrons[0]["x"], x)
        self.assertEqual(self.env["phase"], "play")
        g.lives = 1
        g.patrons[0]["x"] = 58
        self.frame()
        self.assertEqual(self.env["phase"], "over")


if __name__ == "__main__":
    unittest.main()
