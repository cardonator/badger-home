"""Hardware-independent rules for Token Tapper; distances use a 320px field."""

import random

LANES = 4
COUNTER = 48
DOOR = 306
PATRON_EXIT = 340
TOKEN_SPEED = 260
RETURN_SPEED = 120
DEPARTURE_SPEED = 220
COMMIT_LIFETIME = 1.3
MERGE_COMMITS = 4
SPARE_TOKENS = 2
MERGE_TIME = 0.8
MERGE_TOKENS = 4
LOST_COMMIT_PENALTY = 10


class Game:
    def __init__(self):
        self.lane = 0
        self.score = 0
        self.lives = 3
        self.served = 0
        self.level = 1
        self.shift_merges = 0
        self.stage = "serving"
        self.token_stock = self.shift_budget
        self.pending_commits = 0
        self.merges = 0
        self.at_station = False
        self.merge_remaining = 0
        self.patrons = []
        self.tokens = []
        self.returns = []
        self.commits = []
        self.cooldown = 0
        self.spawn_in = 1.4
        self.recovery = 0
        self.overloaded = False
        self.message = ""
        self.message_time = 0
        self.spawn(0)

    @property
    def merge_goal(self):
        return min(6, self.level + 1)

    @property
    def shift_budget(self):
        return self.merge_goal * MERGE_COMMITS + SPARE_TOKENS

    @property
    def serving(self):
        return self.stage == "serving" and not self.over

    @property
    def over(self):
        return self.lives == 0

    def move(self, direction):
        if not self.at_station and self.serving and self.recovery <= 0:
            self.lane = max(0, min(LANES - 1, self.lane + direction))

    def visit_station(self):
        if self.serving and self.recovery <= 0:
            self.at_station = True

    def leave_station(self):
        if self.recovery > 0:
            return
        self.at_station = False
        if self.merge_remaining > 0:
            self.notify("MERGE CANCELLED - COMMITS KEPT")
        self.merge_remaining = 0

    def notify(self, message):
        self.message = message
        self.message_time = 1.5

    def merge(self):
        if not self.serving or self.recovery > 0 or not self.at_station:
            return False
        if self.merge_remaining > 0:
            return False
        if self.pending_commits < MERGE_COMMITS:
            self.notify("CATCH %d MORE COMMITS FIRST" % (MERGE_COMMITS - self.pending_commits))
            return False
        self.merge_remaining = MERGE_TIME
        self.notify("MERGING... RIGHT TO CANCEL")
        return True

    def fire(self):
        if not self.serving or self.recovery > 0 or self.cooldown > 0 or self.at_station:
            return False
        if self.token_stock == 0:
            if self.pending_commits >= MERGE_COMMITS:
                self.notify("OUT OF TOKENS! LEFT TO MERGE")
            else:
                self.notify("OUT OF TOKENS! CATCH RETURNING COMMITS")
            return False
        self.token_stock -= 1
        self.tokens.append({"lane": self.lane, "x": COUNTER})
        self.cooldown = 0.28
        return True

    def spawn(self, lane=None):
        if not self.serving:
            return
        if lane is None:
            available = [
                i for i in range(LANES)
                if not any(p["lane"] == i and p["x"] > 230 for p in self.patrons)
            ]
            if not available:
                return
            lane = available[random.randrange(len(available))]
        self.patrons.append({
            "lane": lane, "x": 286.0, "leaving": False,
            "rest": 0.0, "style": random.randrange(4),
        })

    def miss(self, message, overloaded=False):
        if not self.serving:
            return
        self.lives -= 1
        self.message = message
        self.message_time = 1.5
        self.patrons.clear()
        self.tokens.clear()
        self.returns.clear()
        self.commits.clear()
        self.at_station = False
        self.merge_remaining = 0
        self.token_stock = (self.merge_goal - self.shift_merges) * MERGE_COMMITS + SPARE_TOKENS
        self.pending_commits = 0
        self.cooldown = 0
        self.recovery = 1.3
        self.overloaded = overloaded
        self.spawn_in = 0

    def drop_commit(self):
        if not self.serving:
            return
        self.lives -= 1
        self.notify("COMMIT DROPPED! -1 LIFE")
        if self.over:
            self.merge_remaining = 0

    def receive(self, patron):
        if not self.serving or patron["leaving"]:
            return
        self.score += 10
        patron["leaving"] = True
        patron["rest"] = 0
        self.commits.append({
            "lane": patron["lane"], "x": patron["x"], "age": 0.0,
        })
        self.returns.append({
            "lane": patron["lane"], "x": patron["x"], "delay": 0,
            "speed": RETURN_SPEED + random.randrange(5) * 6 - 12,
        })

    def overload(self):
        self.lives -= 1
        self.overloaded = True
        self.recovery = 3.0
        self.notify("TOO MANY AGENTS! -1 LIFE")
        self.patrons[:] = [
            p for p in self.patrons if p["leaving"] or p["x"] > COUNTER + 10
        ]
        if self.over:
            self.merge_remaining = 0

    def clear_shift(self):
        self.stage = "clearing"
        self.merge_remaining = 0
        self.at_station = False
        self.tokens.clear()
        self.returns.clear()
        self.commits.clear()
        for patron in self.patrons:
            patron["clearing"] = not patron["leaving"]
            patron["leaving"] = True
            patron["rest"] = 0
        self.notify("SHIFT COMPLETE! EVERYONE HEADING OUT")

    def next_shift(self):
        if self.over or self.stage != "break":
            return False
        self.level += 1
        self.shift_merges = 0
        self.stage = "serving"
        self.token_stock = self.shift_budget
        self.pending_commits = 0
        self.at_station = False
        self.merge_remaining = 0
        self.cooldown = 0
        self.recovery = 0
        self.overloaded = False
        self.lane = 0
        self.spawn_in = 1.4
        self.notify("NEW SHIFT! COMPLETE %d MERGES" % self.merge_goal)
        self.spawn(0)
        return True

    def step(self, dt):
        if self.over:
            return
        # Bound simulation steps so a slow frame cannot tunnel through a patron.
        remaining = max(0, min(dt, 0.25))
        while remaining > 0 and not self.over:
            elapsed = min(remaining, 1 / 60)
            self._step(elapsed)
            remaining -= elapsed

    def _step(self, dt):
        if self.stage == "break":
            return
        if self.recovery > 0:
            self.recovery = max(0, self.recovery - dt)
            return
        self.cooldown = max(0, self.cooldown - dt)
        self.message_time = max(0, self.message_time - dt)
        for commit in self.commits[:]:
            commit["age"] += dt
            if commit["age"] >= COMMIT_LIFETIME:
                self.commits.remove(commit)
        if self.stage == "clearing":
            for patron in self.patrons[:]:
                patron["x"] += DEPARTURE_SPEED * dt
                if patron["x"] >= PATRON_EXIT:
                    self.patrons.remove(patron)
                    if not patron["clearing"]:
                        self.served += 1
                        self.score += 25
            if not self.patrons:
                self.stage = "break"
                self.pending_commits = 0
            return
        if self.merge_remaining > 0:
            self.merge_remaining = max(0, self.merge_remaining - dt)
            if self.merge_remaining == 0:
                self.pending_commits -= MERGE_COMMITS
                self.merges += 1
                self.shift_merges += 1
                self.score += 50
                self.token_stock += MERGE_TOKENS
                if self.shift_merges >= self.merge_goal:
                    self.clear_shift()
                    return
                self.notify("MERGED! +4 TOKENS - RIGHT TO SERVE")

        speed = 16 + min(self.level - 1, 15) * 2
        for patron in self.patrons[:]:
            if patron["leaving"]:
                if patron["rest"] > 0:
                    patron["rest"] = max(0, patron["rest"] - dt)
                else:
                    patron["x"] += DEPARTURE_SPEED * dt
            else:
                patron["x"] -= speed * dt
            if patron["leaving"] and patron["x"] >= PATRON_EXIT:
                self.patrons.remove(patron)
                self.served += 1
                self.score += 25
            elif patron["x"] <= COUNTER + 10:
                self.overload()
                return

        for token in self.tokens[:]:
            token["x"] += TOKEN_SPEED * dt
            targets = [
                p for p in self.patrons
                if not p["leaving"] and p["lane"] == token["lane"]
                and token["x"] >= p["x"] - 10
            ]
            if targets:
                patron = min(targets, key=lambda p: p["x"])
                self.tokens.remove(token)
                self.receive(patron)
            elif token["x"] > DOOR + 8:
                self.miss("TOKEN WASTED!")
                return

        for commit in self.returns[:]:
            if commit["delay"] > 0:
                commit["delay"] = max(0, commit["delay"] - dt)
                continue
            commit["x"] -= commit.get("speed", RETURN_SPEED) * dt
            if commit["x"] <= COUNTER:
                self.returns.remove(commit)
                if commit["lane"] == self.lane and not self.at_station:
                    if self.pending_commits >= MERGE_COMMITS:
                        self.score = max(0, self.score - LOST_COMMIT_PENALTY)
                        self.notify("Commit lost! You need to merge!")
                    else:
                        self.score += 5
                        self.pending_commits += 1
                        if self.pending_commits == MERGE_COMMITS:
                            self.notify("MERGE READY! LEFT TO THE STATION")
                        else:
                            self.notify("COMMIT CAUGHT! %d/4" % self.pending_commits)
                else:
                    self.drop_commit()
                    if self.over:
                        return

        self.spawn_in -= dt
        if self.spawn_in <= 0:
            self.spawn()
            self.spawn_in = max(0.75, 2.3 - self.level * 0.15)
