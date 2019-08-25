import random
import threading
import functools
from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src.containers import UserList
from src.decorators import command, handle_error
from src.functions import get_players, change_role
from src.status import add_dying
from src import events, channels, users

@game_mode("sleepy", minp=10, maxp=24, likelihood=1)
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
        # Make sure priest is always prophet AND blessed, and that drunk is always gunner
        self.SECONDARY_ROLES["blessed villager"] = ["priest"]
        self.SECONDARY_ROLES["prophet"] = ["priest"]
        self.SECONDARY_ROLES["gunner"] = ["village drunk"]
        # disable wolfchat
        #self.RESTRICT_WOLFCHAT = 0x0f

    def startup(self):
        events.add_listener("dullahan_targets", self.dullahan_targets)
        events.add_listener("transition_night_begin", self.setup_nightmares)
        events.add_listener("chk_nightdone", self.prolong_night)
        events.add_listener("transition_day_begin", self.nightmare_kill)
        events.add_listener("del_player", self.happy_fun_times)
        events.add_listener("revealroles", self.on_revealroles)

        self.having_nightmare = UserList()

        cmd_params = dict(chan=False, pm=True, playing=True, phases=("night",), users=self.having_nightmare)

        self.north_cmd = command("north", **cmd_params)(functools.partial(self.move, "n"))
        self.east_cmd = command("east", **cmd_params)(functools.partial(self.move, "e"))
        self.south_cmd = command("south", **cmd_params)(functools.partial(self.move, "s"))
        self.west_cmd = command("west", **cmd_params)(functools.partial(self.move, "w"))

    def teardown(self):
        from src import decorators
        events.remove_listener("dullahan_targets", self.dullahan_targets)
        events.remove_listener("transition_night_begin", self.setup_nightmares)
        events.remove_listener("chk_nightdone", self.prolong_night)
        events.remove_listener("transition_day_begin", self.nightmare_kill)
        events.remove_listener("del_player", self.happy_fun_times)
        events.remove_listener("revealroles", self.on_revealroles)

        def remove_command(name, command):
            if len(decorators.COMMANDS[name]) > 1:
                decorators.COMMANDS[name].remove(command)
            else:
                del decorators.COMMANDS[name]
        remove_command("north", self.north_cmd)
        remove_command("n", self.north_cmd)
        remove_command("east", self.east_cmd)
        remove_command("e", self.east_cmd)
        remove_command("south", self.south_cmd)
        remove_command("s", self.south_cmd)
        remove_command("west", self.west_cmd)
        remove_command("w", self.west_cmd)

        self.having_nightmare.clear()

    def dullahan_targets(self, evt, var, dullahan, max_targets):
        evt.data["targets"].update(var.ROLES["priest"])

    def setup_nightmares(self, evt, var):
        if random.random() < 1/5:
            with var.WARNING_LOCK:
                t = threading.Timer(60, self.do_nightmare, (var, random.choice(get_players()), var.NIGHT_COUNT))
                t.daemon = True
                t.start()

    @handle_error
    def do_nightmare(self, var, target, night):
        if var.PHASE != "night" or var.NIGHT_COUNT != night:
            return
        if target not in get_players():
            return
        self.having_nightmare.clear()
        self.having_nightmare.append(target)
        target.send(messages["sleepy_nightmare_begin"])
        target.send(messages["sleepy_nightmare_navigate"])
        self.correct = [None, None, None]
        self.fake1 = [None, None, None]
        self.fake2 = [None, None, None]
        directions = ["n", "e", "s", "w"]
        self.step = 0
        self.prev_direction = None
        opposite = {"n": "s", "e": "w", "s": "n", "w": "e"}
        for i in range(3):
            corrdir = directions[:]
            f1dir = directions[:]
            f2dir = directions[:]
            if i > 0:
                corrdir.remove(opposite[self.correct[i-1]])
                f1dir.remove(opposite[self.fake1[i-1]])
                f2dir.remove(opposite[self.fake2[i-1]])
            else:
                corrdir.remove("s")
                f1dir.remove("s")
                f2dir.remove("s")
            self.correct[i] = random.choice(corrdir)
            self.fake1[i] = random.choice(f1dir)
            self.fake2[i] = random.choice(f2dir)
        self.prev_direction = "n"
        self.start_direction = "n"
        self.on_path = set()
        self.nightmare_step()

    def nightmare_step(self):
        if self.prev_direction == "n":
            directions = "north, east, and west"
        elif self.prev_direction == "e":
            directions = "north, east, and south"
        elif self.prev_direction == "s":
            directions = "east, south, and west"
        elif self.prev_direction == "w":
            directions = "north, south, and west"

        if self.step == 0:
            self.having_nightmare[0].send(messages["sleepy_nightmare_0"].format(directions))
        elif self.step == 1:
            self.having_nightmare[0].send(messages["sleepy_nightmare_1"].format(directions))
        elif self.step == 2:
            self.having_nightmare[0].send(messages["sleepy_nightmare_2"].format(directions))
        elif self.step == 3:
            if "correct" in self.on_path:
                self.having_nightmare[0].send(messages["sleepy_nightmare_wake"])
                self.having_nightmare.clear()
            elif "fake1" in self.on_path:
                self.having_nightmare[0].send(messages["sleepy_nightmare_fake_1"])
                self.step = 0
                self.on_path = set()
                self.prev_direction = self.start_direction
                self.nightmare_step()
            elif "fake2" in self.on_path:
                self.having_nightmare[0].send(messages["sleepy_nightmare_fake_2"])
                self.step = 0
                self.on_path = set()
                self.prev_direction = self.start_direction
                self.nightmare_step()

    def move(self, direction, var, wrapper, message):
        opposite = {"n": "s", "e": "w", "s": "n", "w": "e"}
        if self.prev_direction == opposite[direction]:
            wrapper.pm(messages["sleepy_nightmare_invalid_direction"])
            return
        advance = False
        if ("correct" in self.on_path or self.step == 0) and self.correct[self.step] == direction:
            self.on_path.add("correct")
            advance = True
        else:
            self.on_path.discard("correct")
        if ("fake1" in self.on_path or self.step == 0) and self.fake1[self.step] == direction:
            self.on_path.add("fake1")
            advance = True
        else:
            self.on_path.discard("fake1")
        if ("fake2" in self.on_path or self.step == 0) and self.fake2[self.step] == direction:
            self.on_path.add("fake2")
            advance = True
        else:
            self.on_path.discard("fake2")
        if advance:
            self.step += 1
            self.prev_direction = direction
        else:
            self.step = 0
            self.on_path = set()
            self.prev_direction = self.start_direction
            wrapper.pm(messages["sleepy_nightmare_restart"])
        self.nightmare_step()

    def prolong_night(self, evt, var):
        if self.having_nightmare:
            evt.data["actedcount"] = -1

    def nightmare_kill(self, evt, var):
        if self.having_nightmare and self.having_nightmare[0] in get_players():
            add_dying(var, self.having_nightmare[0], "bot", "night_kill")
            self.having_nightmare[0].send(messages["sleepy_nightmare_death"])
            del self.having_nightmare[0]

    def happy_fun_times(self, evt, var, player, all_roles, death_triggers):
        if death_triggers:
            if evt.params.main_role == "priest":
                turn_chance = 3/4
                seers = [p for p in get_players(("seer",)) if random.random() < turn_chance]
                harlots = [p for p in get_players(("harlot",)) if random.random() < turn_chance]
                cultists = [p for p in get_players(("cultist",)) if random.random() < turn_chance]
                channels.Main.send(messages["sleepy_priest_death"])
                for seer in seers:
                    change_role(var, seer, "seer", "doomsayer", message="sleepy_doomsayer_turn")
                for harlot in harlots:
                    change_role(var, harlot, "harlot", "succubus", message="sleepy_succubus_turn")
                for cultist in cultists:
                    change_role(var, cultist, "cultist", "demoniac", message="sleepy_demoniac_turn")

    def on_revealroles(self, evt, var, wrapper):
        if self.having_nightmare:
            evt.data["output"].append("\u0002having nightmare\u0002: {0}".format(self.having_nightmare[0]))
