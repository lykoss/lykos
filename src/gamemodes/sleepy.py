import random
import threading
import functools
from collections import Counter
from src.gamemodes import game_mode, GameMode
from src.messages import messages
from src.containers import UserList, UserDict
from src.decorators import command, handle_error
from src.functions import get_players, change_role
from src.status import add_dying
from src.events import EventListener
from src import channels

@game_mode("sleepy", minp=10, maxp=24, likelihood=5)
class SleepyMode(GameMode):
    """A small village has become the playing ground for all sorts of supernatural beings."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_GUIDE = {
            10: ["wolf", "werecrow", "traitor", "cultist", "seer", "prophet", "priest", "dullahan", "cursed villager", "blessed villager"],
            12: ["wolf(2)", "vigilante"],
            15: ["wolf(3)", "detective", "vengeful ghost"],
            18: ["wolf(4)", "harlot", "monster"],
            21: ["wolf(5)", "village drunk", "monster(2)", "gunner"],
        }
        self.NIGHTMARE_CHANCE = 1/5
        self.NIGHTMARE_MAX = 1
        self.TURN_CHANCE = 3/5
        # Make sure priest is always prophet AND blessed, and that drunk is always gunner
        self.SECONDARY_ROLES["blessed villager"] = ["priest"]
        self.SECONDARY_ROLES["prophet"] = ["priest"]
        self.SECONDARY_ROLES["gunner"] = ["village drunk"]
        self.EVENTS = {
            "dullahan_targets": EventListener(self.dullahan_targets),
            "transition_night_begin": EventListener(self.setup_nightmares),
            "chk_nightdone": EventListener(self.prolong_night),
            "transition_day_begin": EventListener(self.nightmare_kill),
            "del_player": EventListener(self.happy_fun_times),
            "revealroles": EventListener(self.on_revealroles),
            "night_idled": EventListener(self.on_night_idled)
        }

        self.having_nightmare = UserList()
        cmd_params = dict(chan=False, pm=True, playing=True, phases=("night",),
                          users=self.having_nightmare, register=False)
        self.north_cmd = command("north", **cmd_params)(functools.partial(self.move, "n"))
        self.east_cmd = command("east", **cmd_params)(functools.partial(self.move, "e"))
        self.south_cmd = command("south", **cmd_params)(functools.partial(self.move, "s"))
        self.west_cmd = command("west", **cmd_params)(functools.partial(self.move, "w"))

        self.correct = UserDict()
        self.fake1 = UserDict()
        self.fake2 = UserDict()
        self.step = UserDict()
        self.prev_direction = UserDict()
        self.start_direction = UserDict()
        self.on_path = UserDict()

    def startup(self):
        super().startup()
        self.north_cmd.register()
        self.east_cmd.register()
        self.south_cmd.register()
        self.west_cmd.register()

    def teardown(self):
        super().teardown()
        self.north_cmd.remove()
        self.east_cmd.remove()
        self.south_cmd.remove()
        self.west_cmd.remove()
        self.having_nightmare.clear()
        self.correct.clear()
        self.fake1.clear()
        self.fake2.clear()
        self.step.clear()
        self.prev_direction.clear()
        self.start_direction.clear()
        self.on_path.clear()

    def dullahan_targets(self, evt, var, dullahan, max_targets):
        evt.data["targets"].update(var.ROLES["priest"])

    def setup_nightmares(self, evt, var):
        pl = get_players()
        for i in range(self.NIGHTMARE_MAX):
            if not pl:
                break
            if random.random() < self.NIGHTMARE_CHANCE:
                with var.WARNING_LOCK:
                    target = random.choice(pl)
                    pl.remove(target)
                    t = threading.Timer(60, self.do_nightmare, (var, target, var.NIGHT_COUNT))
                    t.daemon = True
                    t.start()

    @handle_error
    def do_nightmare(self, var, target, night):
        if var.PHASE != "night" or var.NIGHT_COUNT != night:
            return
        if target not in get_players():
            return
        self.having_nightmare.append(target)
        target.send(messages["sleepy_nightmare_begin"])
        target.send(messages["sleepy_nightmare_navigate"])
        self.correct[target] = [None, None, None]
        self.fake1[target] = [None, None, None]
        self.fake2[target] = [None, None, None]
        directions = ["n", "e", "s", "w"]
        self.step[target] = 0
        self.prev_direction[target] = None
        opposite = {"n": "s", "e": "w", "s": "n", "w": "e"}
        for i in range(3):
            corrdir = directions[:]
            f1dir = directions[:]
            f2dir = directions[:]
            if i > 0:
                corrdir.remove(opposite[self.correct[target][i-1]])
                f1dir.remove(opposite[self.fake1[target][i-1]])
                f2dir.remove(opposite[self.fake2[target][i-1]])
            else:
                corrdir.remove("s")
                f1dir.remove("s")
                f2dir.remove("s")
            self.correct[target][i] = random.choice(corrdir)
            self.fake1[target][i] = random.choice(f1dir)
            self.fake2[target][i] = random.choice(f2dir)
        self.prev_direction[target] = "n"
        self.start_direction[target] = "n"
        self.on_path[target] = set()
        self.nightmare_step(target)

    def nightmare_step(self, target):
        # FIXME: hardcoded English
        if self.prev_direction[target] == "n":
            directions = "north, east, and west"
        elif self.prev_direction[target] == "e":
            directions = "north, east, and south"
        elif self.prev_direction[target] == "s":
            directions = "east, south, and west"
        elif self.prev_direction[target] == "w":
            directions = "north, south, and west"
        else:
            # wat? reset them
            self.step[target] = 0
            self.prev_direction[target] = self.start_direction[target]
            self.on_path[target] = set()
            directions = "north, east, and west"

        if self.step[target] == 0:
            target.send(messages["sleepy_nightmare_0"].format(directions))
        elif self.step[target] == 1:
            target.send(messages["sleepy_nightmare_1"].format(directions))
        elif self.step[target] == 2:
            target.send(messages["sleepy_nightmare_2"].format(directions))
        elif self.step[target] == 3:
            if "correct" in self.on_path[target]:
                target.send(messages["sleepy_nightmare_wake"])
                self.having_nightmare.remove(target)
            elif "fake1" in self.on_path[target]:
                target.send(messages["sleepy_nightmare_fake_1"])
                self.step[target] = 0
                self.on_path[target] = set()
                self.prev_direction[target] = self.start_direction[target]
                self.nightmare_step(target)
            elif "fake2" in self.on_path[target]:
                target.send(messages["sleepy_nightmare_fake_2"])
                self.step[target] = 0
                self.on_path[target] = set()
                self.prev_direction[target] = self.start_direction[target]
                self.nightmare_step(target)

    def move(self, direction, var, wrapper, message):
        opposite = {"n": "s", "e": "w", "s": "n", "w": "e"}
        target = wrapper.source
        if self.prev_direction[target] == opposite[direction]:
            wrapper.pm(messages["sleepy_nightmare_invalid_direction"])
            return
        advance = False
        step = self.step[target]
        if ("correct" in self.on_path[target] or step == 0) and self.correct[target][step] == direction:
            self.on_path[target].add("correct")
            advance = True
        else:
            self.on_path[target].discard("correct")
        if ("fake1" in self.on_path[target] or step == 0) and self.fake1[target][step] == direction:
            self.on_path[target].add("fake1")
            advance = True
        else:
            self.on_path[target].discard("fake1")
        if ("fake2" in self.on_path[target] or step == 0) and self.fake2[target][step] == direction:
            self.on_path[target].add("fake2")
            advance = True
        else:
            self.on_path[target].discard("fake2")
        if advance:
            self.step[target] += 1
            self.prev_direction[target] = direction
        else:
            self.step[target] = 0
            self.on_path[target] = set()
            self.prev_direction[target] = self.start_direction[target]
            wrapper.pm(messages["sleepy_nightmare_restart"])
        self.nightmare_step(target)

    def prolong_night(self, evt, var):
        evt.data["nightroles"].extend(self.having_nightmare)

    def on_night_idled(self, evt, var, player):
        # don't give warning points if the person having a nightmare idled out night
        if player in self.having_nightmare:
            evt.prevent_default = True

    def nightmare_kill(self, evt, var):
        pl = get_players()
        for player in self.having_nightmare:
            if player not in pl:
                continue
            add_dying(var, player, "bot", "night_kill")
            player.send(messages["sleepy_nightmare_death"])
        self.having_nightmare.clear()

    def happy_fun_times(self, evt, var, player, all_roles, death_triggers):
        if death_triggers and evt.params.main_role == "priest":
            channels.Main.send(messages["sleepy_priest_death"])

            mapping = {"seer": "doomsayer", "harlot": "succubus", "cultist": "demoniac"}
            for old, new in mapping.items():
                turn = [p for p in get_players((old,)) if random.random() < self.TURN_CHANCE]
                for t in turn:
                    # messages: sleepy_doomsayer_turn, sleepy_succubus_turn, sleepy_demoniac_turn
                    change_role(var, t, old, new, message="sleepy_{0}_turn".format(new))

                newstats = set()
                for rs in var.ROLE_STATS:
                    d = Counter(dict(rs))
                    newstats.add(rs)
                    if old in d and d[old] >= 1:
                        d[old] -= 1
                        d[new] += 1
                        newstats.add(frozenset(d.items()))
                var.ROLE_STATS = frozenset(newstats)

    def on_revealroles(self, evt, var):
        if self.having_nightmare:
            evt.data["output"].append(messages["sleepy_revealroles"].format(self.having_nightmare))
