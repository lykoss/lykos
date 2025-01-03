from collections import Counter, defaultdict

from src.cats import Wolf
from src.dispatcher import MessageDispatcher
from src.gamemodes import game_mode, GameMode
from src.messages import messages
from src.containers import UserDict, UserSet
from src.decorators import command, handle_error
from src.functions import get_players, change_role, get_main_role
from src.gamestate import GameState
from src.status import remove_all_protections
from src.events import EventListener, Event
from src import channels, config
from src.users import User
from src.random import random

@game_mode("sleepy", minp=8, maxp=24)
class SleepyMode(GameMode):
    """A small village has become the playing ground for all sorts of supernatural beings."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_GUIDE = {
            8: ["werecrow", "traitor", "mystic", "seer", "priest", "dullahan", "cursed villager"],
            9: ["amnesiac"],
            10: ["-traitor", "wolf", "blessed villager", "cursed villager(2)"],
            11: ["village drunk"],
            12: ["wolf(2)"],
            13: ["vengeful ghost"],
            14: ["sorcerer", "prophet"],
            15: ["gunner"],
            16: ["-wolf", "fallen angel", "vigilante"],
            17: ["succubus"],
            18: ["detective"],
            20: ["werecrow(2)"],
            21: ["monster", "hunter"],
            22: ["augur", "amnesiac(2)"],
            23: ["insomniac", "cultist"],
            24: ["wolf(2)"]
        }

        self.TURN_CHANCE = config.Main.get("gameplay.modes.sleepy.turn")
        # Force secondary roles
        self.SECONDARY_ROLES["blessed villager"] = {"priest"}
        self.SECONDARY_ROLES["gunner"] = {"village drunk"}
        self.SECONDARY_ROLES["hunter"] = {"monster"}
        self.EVENTS = {
            "dullahan_targets": EventListener(self.dullahan_targets),
            "chk_nightdone": EventListener(self.setup_nightmares, priority=10),
            "del_player": EventListener(self.happy_fun_times),
            "revealroles": EventListener(self.on_revealroles),
            "remove_protection": EventListener(self.on_remove_protection),
        }

        self.MESSAGE_OVERRIDES = {
            "mystic_info_nightmare": "mystic_info_night"
        }

        self.having_nightmare: UserDict[User, User] = UserDict()
        self.nightmare_progress: UserDict[User, int] = UserDict()
        self.nightmare_acted = UserSet()
        # nightmare commands for the person being chased
        cmd_params = dict(chan=False, pm=True, playing=True, phases=("nightmare",),
                          users=self.having_nightmare.values(), register=False)
        self.hide_cmd = command("hide", **cmd_params)(self.hide)
        self.run_cmd = command("run", **cmd_params)(self.run)

        # nightmare commands for dulla
        cmd_params = dict(chan=False, pm=True, playing=True, phases=("nightmare",),
                          roles=("dullahan",), register=False)
        self.search_cmd = command("search", **cmd_params)(self.search)
        self.chase_cmd = command("chase", **cmd_params)(self.chase)

    def startup(self):
        super().startup()
        self.hide_cmd.register()
        self.run_cmd.register()
        self.search_cmd.register()
        self.chase_cmd.register()

    def teardown(self):
        super().teardown()
        self.hide_cmd.remove()
        self.run_cmd.remove()
        self.search_cmd.remove()
        self.chase_cmd.remove()
        # clear user containers
        self.having_nightmare.clear()
        self.nightmare_progress.clear()
        self.nightmare_acted.clear()

    def dullahan_targets(self, evt: Event, var: GameState, dullahan, max_targets):
        evt.data["targets"].update(get_players(var, ("priest",)))
        evt.data["exclude"].update(get_players(var, Wolf))
        # dulla needs 1 fewer target to win than normal
        evt.data["num_targets"] = max_targets - 1

    def setup_nightmares(self, evt: Event, var: GameState):
        from src.roles.dullahan import KILLS
        dullahans = get_players(var, ("dullahan",))
        # don't give nightmares to other dullas, because that'd just be awkward
        filtered = [x for x in KILLS.values() if x not in dullahans]
        if filtered:
            evt.data["transition_day"] = self.do_nightmares

    # called from trans.py when night ends and dulla has kills
    @handle_error
    def do_nightmares(self, var: GameState):
        from src.roles.dullahan import KILLS
        self.having_nightmare.update(KILLS)
        self.nightmare_progress.clear()
        steps = config.Main.get("gameplay.modes.sleepy.nightmare.steps")

        counts = defaultdict(int)
        time_limit = config.Main.get("gameplay.modes.sleepy.nightmare.time")
        timers_enabled = config.Main.get("timers.enabled")
        for dulla, target in self.having_nightmare.items():
            if get_main_role(var, target) == "dullahan":
                continue
            # ensure regular dullahan kill logic doesn't fire since we do it specially
            # (except for dullahans targeting themselves or other dullahans)
            del KILLS[dulla]
            self.nightmare_progress[dulla] = 3 - steps
            self.nightmare_progress[target] = 4 - steps
            counts[target] += 1
            dulla.send(messages["sleepy_nightmare_start_dullahan"].format(target))
            if timers_enabled and time_limit:
                dulla.queue_message(messages["sleepy_nightmare_timer_notify"].format(time_limit))

        # send the initial messages to targets too
        for target, count in counts.items():
            if count == 1:
                target.send(messages["sleepy_nightmare_start_target"])
            else:
                target.send(messages["sleepy_nightmare_start_target_multiple"].format(count))
            if timers_enabled and time_limit:
                target.queue_message(messages["sleepy_nightmare_timer_notify"].format(time_limit))

        # send timer_notify messages
        User.send_messages()

        # kick it all off
        self.nightmare_step(var)

    @handle_error
    def nightmare_timer(self, timer_type: str, var: GameState):
        idlers = False
        for dulla, target in self.having_nightmare.items():
            if dulla not in self.nightmare_acted:
                idlers = True
                self.nightmare_progress[dulla] += 2
                dulla.send(messages["sleepy_nightmare_dullahan_idle"])
            if target not in self.nightmare_acted:
                idlers = True
                self.nightmare_progress[target] += 1
                target.send(messages["sleepy_nightmare_target_idle"])

        if idlers:
            self.nightmare_step(var)

    def nightmare_step(self, var: GameState):
        from src.roles.dullahan import KILLS
        # keep track of who was already sent messages in case they're being chased by multiple dullahans
        notified = set()
        dulla_counts = defaultdict(int)
        for target in self.having_nightmare.values():
            dulla_counts[target] += 1

        for dulla, target in list(self.having_nightmare.items()):
            if self.nightmare_progress[dulla] == self.nightmare_progress[target]:
                # dulla caught up and target dies
                del self.having_nightmare[dulla]
                if target not in notified:
                    notified.add(target)
                    target.send(messages["sleepy_nightmare_caught"].format(dulla_counts[target]))
                dulla.send(messages["sleepy_nightmare_kill"].format(target))
                KILLS[dulla] = target
                remove_all_protections(var, target, dulla, "dullahan", "nightmare")
            elif self.nightmare_progress[dulla] > self.nightmare_progress[target]:
                # dulla passed the target by (maybe escaping or maybe a different dulla catches them)
                del self.having_nightmare[dulla]
                remaining = sum(1 for x in self.having_nightmare.values() if x is target)
                if remaining == 0 and target not in notified:
                    # target escapes fully
                    notified.add(target)
                    target.send(messages["sleepy_nightmare_escape_hide"].format(dulla_counts[target]))
                dulla.send(messages["sleepy_nightmare_fail_hide"])
            elif self.nightmare_progress[target] == 4:
                # target escapes
                del self.having_nightmare[dulla]
                if target not in notified:
                    notified.add(target)
                    target.send(messages["sleepy_nightmare_escape_run"].format(dulla_counts[target]))
                dulla.send(messages["sleepy_nightmare_fail_river"])
            else:
                # target still being chased
                if target not in notified:
                    notified.add(target)
                    target.send(messages["sleepy_nightmare_target_step_{0}".format(self.nightmare_progress[target])])
                dulla.send(messages["sleepy_nightmare_dullahan_step"].format(4 - self.nightmare_progress[target]))

        self.nightmare_acted.clear()
        if self.having_nightmare:
            # need another round of nightmares
            var.begin_phase_transition("nightmare")
            time_limit = config.Main.get("gameplay.modes.sleepy.nightmare.time")
            var.end_phase_transition(time_limit, timer_cb=self.nightmare_timer, cb_args=(var,))
        else:
            # all nightmares resolved, can finally make it daytime
            from src.trans import transition_day
            self.nightmare_progress.clear()
            transition_day(var)

    def _resolve_nightmare_command(self, wrapper: MessageDispatcher, cmd: str):
        self.nightmare_acted.add(wrapper.source)
        wrapper.reply(messages["sleepy_nightmare_success"].format(cmd))
        need_act = set(self.having_nightmare.keys()) | set(self.having_nightmare.values())
        if need_act == set(self.nightmare_acted):
            self.nightmare_step(wrapper.game_state)

    def hide(self, wrapper: MessageDispatcher, message: str):
        """Attempt to hide from the dullahan chasing you."""
        if wrapper.source in self.nightmare_acted:
            wrapper.reply(messages["sleepy_nightmare_acted"])
            return

        self._resolve_nightmare_command(wrapper, "hide")

    def run(self, wrapper: MessageDispatcher, message: str):
        """Attempt to run from the dullahan chasing you."""
        if wrapper.source in self.nightmare_acted:
            wrapper.reply(messages["sleepy_nightmare_acted"])
            return

        self.nightmare_progress[wrapper.source] += 1
        self._resolve_nightmare_command(wrapper, "run")

    def search(self, wrapper: MessageDispatcher, message: str):
        """Chase at a slower pace to catch hiding targets."""
        if wrapper.source in self.nightmare_acted:
            wrapper.reply(messages["sleepy_nightmare_acted"])
            return

        self.nightmare_progress[wrapper.source] += 1
        self._resolve_nightmare_command(wrapper, "search")

    def chase(self, wrapper: MessageDispatcher, message: str):
        """Chase at a faster pace to catch running targets."""
        if wrapper.source in self.nightmare_acted:
            wrapper.reply(messages["sleepy_nightmare_acted"])
            return

        self.nightmare_progress[wrapper.source] += 2
        self._resolve_nightmare_command(wrapper, "chase")

    def happy_fun_times(self, evt: Event, var: GameState, player, all_roles, death_triggers):
        if death_triggers and evt.params.main_role == "priest":
            channels.Main.send(messages["sleepy_priest_death"])

            mapping = {"seer": "doomsayer",
                       "cultist": "demoniac",
                       "vengeful ghost": "jester"}
            for old, new in mapping.items():
                turn = [p for p in get_players(var, (old,)) if random.random() < self.TURN_CHANCE]
                for t in turn:
                    if new == "doomsayer":
                        # so game doesn't just end immediately at 8-9p, make the traitor into a monster too
                        # do this before seer turns to doomsayer so the traitor doesn't know the new wolf
                        for traitor in get_players(var, ("traitor",)):
                            change_role(var, traitor, "traitor", "monster", message="sleepy_monster_turn")
                    # messages: sleepy_doomsayer_turn, sleepy_succubus_turn, sleepy_demoniac_turn, sleepy_jester_turn
                    change_role(var, t, old, new, message="sleepy_{0}_turn".format(new))
                    if new == "jester":
                        # VGs turned into jesters remain spicy
                        var.roles["vengeful ghost"].add(t)

                newstats = set()
                for rs in var.get_role_stats():
                    d = Counter(dict(rs))
                    newstats.add(rs)
                    if old in d and d[old] >= 1:
                        for i in range(1, d[old] + 1):
                            d[old] -= i
                            d[new] += i
                            if new == "doomsayer" and "traitor" in d and d["traitor"] >= 1:
                                d["monster"] += d["traitor"]
                                d["traitor"] = 0
                            newstats.add(frozenset(d.items()))
                var.set_role_stats(newstats)

    def on_remove_protection(self, evt: Event, var: GameState, target: User, attacker: User, attacker_role: str, protector: User, protector_role: str, reason: str):
        if reason == "nightmare":
            evt.data["remove"] = True

    def on_revealroles(self, evt: Event, var: GameState):
        if self.having_nightmare:
            evt.data["output"].append(messages["sleepy_revealroles"].format(self.having_nightmare.values()))
