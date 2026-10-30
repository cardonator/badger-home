"""A pocket arcade token bar: brass rails, mint tokens, floating commits."""

import os
import sys
import math

APP_DIR = "/system/apps/token_tapper"
os.chdir(APP_DIR)
sys.path.insert(0, APP_DIR)

from badgeware import State
from game import Game, COMMIT_LIFETIME, COUNTER, MERGE_COMMITS, MERGE_TIME, SPARE_TOKENS

badge.mode(HIRES | VSYNC)
screen.antialias = image.OFF
mona_sprites = image.load("assets/mona.png").spritesheet(11, 1)

INK = color.rgb(28, 24, 38)
WALL = color.rgb(45, 37, 51)
WOOD = color.rgb(106, 57, 48)
RAIL = color.rgb(227, 168, 80)
CREAM = color.rgb(255, 235, 190)
MINT = color.rgb(130, 244, 194)
TEAL = color.rgb(43, 117, 111)
RED = color.rgb(255, 129, 116)
SHELLS = (TEAL, color.rgb(178, 80, 95), color.rgb(100, 103, 169), RAIL)

record = {"highscore": 0}
State.load("token_tapper", record)
if not isinstance(record.get("highscore"), int) or record["highscore"] < 0:
    record["highscore"] = 0

game = Game()
OPENING_MERGE_GOAL = game.merge_goal
OPENING_TOKEN_BUDGET = game.shift_budget
phase = "title"
save_error = False
move_repeat = 0
move_direction = 0
animation = 0


def box(x, y, w, h, pen):
    screen.pen = pen
    screen.shape(shape.rectangle(int(x), int(y), int(w), int(h)))


def text(label, x, y, pen=CREAM):
    screen.pen = pen
    screen.text(label, int(x), int(y))


def centered(label, y, pen=CREAM):
    width, _ = screen.measure_text(label)
    text(label, (screen.width - width) / 2, y, pen)


def lane_y(lane):
    return 76 + lane * 38


def commit_mark(x, y, pen, size=1):
    box(x - 9 * size, y - size, 6 * size, 2 * size, pen)
    box(x + 4 * size, y - size, 6 * size, 2 * size, pen)
    box(x - 4 * size, y - 4 * size, 8 * size, 8 * size, pen)
    box(x - 2 * size, y - 2 * size, 4 * size, 4 * size, WALL)


def patron(x, y, style, happy=False):
    x = int(x)
    bob = 0 if happy else int(math.sin(animation * 6 + x) * 1.5)
    y += bob
    shell = SHELLS[style]
    signal = MINT if happy else CREAM
    box(x - 1, y - 21, 2, 5, shell)
    box(x - 2, y - 22, 4, 3, signal)
    box(x - 9, y - 17, 18, 12, shell)
    box(x - 11, y - 14, 2, 6, CREAM)
    box(x + 9, y - 14, 2, 6, CREAM)
    box(x - 7, y - 15, 14, 8, INK)
    if happy:
        for eye in (-4, 3):
            box(x + eye, y - 13, 3, 2, signal)
            box(x + eye - 1, y - 12, 1, 2, signal)
    else:
        box(x - 4, y - 13, 3, 4, signal)
        box(x + 3, y - 13, 3, 4, signal)
    box(x - 3, y - 5, 6, 2, CREAM)
    box(x - 8, y - 3, 16, 11, shell)
    box(x - 5, y - 1, 10, 7, INK)
    if happy:
        box(x - 3, y + 2, 2, 2, MINT)
        box(x - 1, y + 3, 2, 2, MINT)
        box(x + 1, y + 1, 2, 3, MINT)
    else:
        box(x - 3, y, 2, 2, MINT)
        box(x - 1, y + 1, 2, 2, MINT)
        box(x - 3, y + 2, 2, 2, MINT)
        box(x + 2, y + 4, 2, 1, MINT)
    box(x - 12, y - 1, 3, 6, shell)
    box(x + 9, y - 1, 3, 6, shell)
    box(x - 13, y + 4, 5, 3, CREAM)
    box(x + 8, y + 4, 5, 3, CREAM)
    box(x - 6, y + 8, 4, 3, CREAM)
    box(x + 2, y + 8, 4, 3, CREAM)


def server(x, y):
    sprite = mona_sprites.sprite(int(animation * 6) % 11, 0)
    screen.blit(sprite, rect(x - 16, y - 20, 32, 32))
    if not game.at_station:
        box(x + 11, y, 8, 3, CREAM)


def field_x(x):
    return 85 + (x - COUNTER) * (221 / 258)


def token(x, y):
    x = int(x)
    box(x - 6, y - 5, 12, 10, MINT)
    box(x - 4, y - 3, 8, 6, TEAL)
    box(x - 1, y - 3, 2, 6, MINT)
    box(x - 3, y - 1, 6, 2, MINT)
    box(x - 14, y, 5, 1, MINT)


def station():
    ready = game.pending_commits >= MERGE_COMMITS
    pen = MINT if ready else RAIL
    box(3, 43, 38, 172, INK)
    text("MERGE", 7, 106, pen)
    box(9, 125, 26, 22, TEAL if ready else WOOD)
    screen.pen = pen
    screen.line(17, 130, 17, 141)
    screen.line(28, 130, 17, 137)
    box(15, 129, 5, 5, pen)
    box(26, 129, 5, 5, pen)
    box(15, 139, 5, 5, pen)
    for i in range(MERGE_COMMITS):
        box(7 + i * 8, 156, 5, 5, MINT if game.pending_commits > i else WOOD)
    text("%d/4" % game.pending_commits, 10, 91, pen)
    if game.at_station:
        server(23, 78)
        text("SEL", 13, 173, pen)
        text("merge", 7, 186, CREAM)
    else:
        text("<", 18, 176, pen)
        text("visit", 7, 188, CREAM)
    if game.merge_remaining > 0:
        box(7, 200, 30, 5, WOOD)
        box(7, 200, max(1, int(30 * (1 - game.merge_remaining / MERGE_TIME))), 5, MINT)


def draw_bar(demo=False):
    box(0, 0, screen.width, screen.height, WALL)
    screen.font = font.nope
    box(0, 0, screen.width, 40, INK)
    text("SCORE %05d" % game.score, 8, 5, CREAM)
    text("SHIFT %d" % game.level, 152, 5, RAIL)
    text("TOKENS %d" % game.token_stock, 8, 23, MINT if game.token_stock else RED)
    text("MERGES %d/%d" % (game.shift_merges, game.merge_goal), 114, 23, RAIL)
    if game.pending_commits >= MERGE_COMMITS:
        text("MERGE READY", 238, 23, MINT)
    station()
    for i in range(3):
        box(262 + i * 18, 9, 11, 9, RED if i < game.lives else WOOD)
        box(264 + i * 18, 7, 3, 2, RED if i < game.lives else WOOD)
    for lane in range(4):
        y = lane_y(lane)
        box(85, y - 22, 227, 37, INK)
        box(85, y + 6, 227, 12, WOOD)
        box(85, y + 5, 227, 2, RAIL)
        box(85, y + 17, 227, 2, INK)
        for x in range(100, 305, 32):
            box(x, y + 12, 14, 1, WALL)
        box(306, y - 22, 6, 27, TEAL)
        if lane == game.lane and not game.at_station:
            box(45, y - 23, 3, 40, MINT)
            server(64, y)
        else:
            text(str(lane + 1), 62, y - 6, RAIL)
    if demo:
        for lane, x in enumerate((190, 264, 232, 153)):
            patron(field_x(x), lane_y(lane), lane)
        token(field_x(116), lane_y(0))
        commit_mark(field_x(266), lane_y(1) - 30, MINT)
    else:
        for p in game.patrons:
            patron(field_x(p["x"]), lane_y(p["lane"]), p["style"], p["leaving"])
        for t in game.tokens:
            token(field_x(t["x"]), lane_y(t["lane"]))
        for commit in game.returns:
            if commit["delay"] <= 0:
                commit_mark(field_x(commit["x"]), lane_y(commit["lane"]), RAIL)
        for c in game.commits:
            progress = c["age"] / COMMIT_LIFETIME
            pen = color.rgb(
                int(130 - progress * 85),
                int(244 - progress * 207),
                int(194 - progress * 143),
            )
            commit_mark(
                min(300, field_x(c["x"]) + progress * 12),
                lane_y(c["lane"]) - 25 - progress * 18,
                pen,
            )
    box(0, 212, screen.width, 28, INK)
    if game.stage == "break":
        centered("SELECT next shift   BACK pause", 214)
    elif game.stage == "clearing":
        centered("SHIFT COMPLETE - CLEARING THE BAR", 214, MINT)
    elif game.at_station:
        centered("SELECT merge   RIGHT return   BACK pause", 214)
    else:
        centered("UP/DOWN lane  SELECT toss  LEFT merge", 214)
    if game.stage == "break":
        centered("Lives and score carry into the next shift.", 227, RAIL)
    elif game.stage == "clearing":
        centered("Outstanding returns are now safe.", 227, RAIL)
    elif game.message_time > 0 and not demo:
        warning = game.recovery or game.message.startswith(("COMMIT DROPPED", "Commit lost!"))
        centered(game.message, 227, RED if warning else MINT)
    else:
        centered("Merge 4 commits to advance the shift.", 227, RAIL)


def panel(title):
    box(0, 38, screen.width, 174, INK)
    box(12, 38, screen.width - 24, 3, RAIL)
    box(12, 209, screen.width - 24, 3, RAIL)
    screen.font = font.ziplock
    centered(title, 51, RAIL)
    screen.font = font.nope


def finish():
    global save_error
    if game.score > record["highscore"]:
        record["highscore"] = game.score
        try:
            State.save("token_tapper", record)
        except OSError as error:
            save_error = True
            print("Token Tapper: high score could not be saved:", error)


def update():
    global phase, game, animation, move_repeat, move_direction, save_error
    dt = max(0, min(badge.ticks_delta / 1000, 0.25))
    if phase == "title" or (phase == "play" and game.recovery <= 0):
        animation += dt
    select = badge.pressed(BUTTON_SELECT)
    pause = badge.pressed(BUTTON_BACK) or badge.pressed(BUTTON_MENU)
    previous_phase = phase

    if phase == "title":
        draw_bar(True)
        panel("TOKEN TAPPER")
        centered("SHIFT 1: %d merges / %d tokens" % (OPENING_MERGE_GOAL, OPENING_TOKEN_BUDGET), 80, MINT)
        centered("UP/DOWN lane  SELECT toss (1 token)", 98)
        centered("Catch gold commits in their lane.", 113)
        centered("LEFT: station  SELECT: merge", 128)
        centered("4 commits = 1 merge. RIGHT: return.", 143)
        centered("Drops cost a life; merges keep going.", 158, RAIL)
        centered("Patron at the tap? AI server overload!", 173)
        centered("SELECT TO START", 187, MINT)
        if select:
            game = Game()
            phase = "play"
            save_error = False
            move_repeat = 0
            move_direction = 0
        return

    if phase == "play":
        if pause:
            phase = "pause"
        elif game.stage == "break":
            if select:
                game.next_shift()
                move_repeat = 0
                move_direction = 0
        else:
            if badge.pressed(BUTTON_LEFT):
                game.visit_station()
            elif badge.pressed(BUTTON_RIGHT):
                game.leave_station()
            direction = 0
            if badge.held(BUTTON_UP) or badge.pressed(BUTTON_UP):
                direction = -1
            elif badge.held(BUTTON_DOWN) or badge.pressed(BUTTON_DOWN):
                direction = 1
            move_repeat -= dt
            if direction:
                if direction != move_direction or move_repeat <= 0:
                    game.move(direction)
                    move_repeat = 0.25 if direction != move_direction else 0.16
            move_direction = direction
            if select:
                if game.at_station:
                    game.merge()
                else:
                    game.fire()
            game.step(dt)
            if game.over:
                phase = "over"
                finish()

    draw_bar()
    if phase == "play" and game.stage == "break":
        panel("SHIFT COMPLETE")
        centered("SHIFT %d: %d/%d MERGES" % (game.level, game.shift_merges, game.merge_goal), 85, MINT)
        centered("The bar is clear. Take a breather.", 106)
        next_goal = min(6, game.level + 2)
        centered("NEXT: %d MERGES / %d TOKENS" % (next_goal, next_goal * MERGE_COMMITS + SPARE_TOKENS), 131, RAIL)
        centered("Fresh tokens. Lives carry over.", 151)
        centered("SELECT TO START NEXT SHIFT", 179, MINT)
    if phase == "play" and game.recovery > 0 and game.overloaded:
        box(39, 88, screen.width - 78, 82, INK)
        box(39, 88, screen.width - 78, 2, RED)
        box(39, 168, screen.width - 78, 2, RED)
        centered("Too many agents", 98, RED)
        centered("-1 life. Take a breath!", 118)
        centered("Resuming in %d..." % math.ceil(game.recovery), 143, MINT)
    if phase == "pause":
        panel("ON A BREAK")
        centered("The token bar is paused.", 99)
        centered("SELECT / BACK to resume", 128, MINT)
        centered("HOME returns to the badge menu.", 160)
        if previous_phase == "pause" and (select or pause):
            phase = "play"
    elif phase == "over":
        panel("SHIFT OVER")
        centered("SCORE          %d" % game.score, 87, MINT)
        centered("BEST SHIFT     %d" % record["highscore"], 106)
        centered("PATRONS SERVED %d" % game.served, 125)
        centered("MERGES         %d" % game.merges, 144, MINT)
        if save_error:
            centered("Best score not saved: storage error.", 156, RED)
        else:
            centered("SELECT: play again   BACK: title", 178)
        if previous_phase == "over" and select:
            game = Game()
            phase = "play"
            save_error = False
        elif previous_phase == "over" and pause:
            phase = "title"


run(update)
