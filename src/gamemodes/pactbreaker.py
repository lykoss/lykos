from __future__ import annotations

import random
import re
from collections import defaultdict
from typing import Iterable

from src import users, channels
from src.users import User, FakeUser
from src.containers import UserSet, UserDict, DefaultUserDict
from src.decorators import command
from src.dispatcher import MessageDispatcher
from src.events import Event
from src.events import EventListener
from src.functions import get_players, get_main_role, get_target, change_role
from src.gamemodes import game_mode, GameMode
from src.gamestate import GameState
from src.messages import messages, LocalRole
from src.locations import move_player, get_home, Location, VillageSquare, Forest
from src.cats import Wolf, Vampire
from src.roles.helper.wolves import send_wolfchat_message, wolf_kill, wolf_retract
from src.roles.vampire import send_vampire_chat_message, vampire_bite, vampire_retract
from src.roles.vigilante import vigilante_kill, vigilante_retract, vigilante_pass

@game_mode("pactbreaker", minp=6, maxp=24, likelihood=0)
class PactBreakerMode(GameMode):
    """Help a rogue vigilante take down the terrors of the night or re-establish your pact with the werewolves!"""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.CUSTOM_SETTINGS.limit_abstain = False
        self.CUSTOM_SETTINGS.self_lynch_allowed = False
        self.CUSTOM_SETTINGS.always_pm_role = True
        self.ROLE_GUIDE = {
            6: ["wolf", "vampire", "vigilante"],
            8: ["wolf(2)"],
            10: ["vampire(2)"],
            12: ["vigilante(2)"],
            14: ["wolf(3)"],
            16: ["vampire(3)"],
            18: ["wolf(4)"],
            20: ["vigilante(3)"],
            24: ["wolf(5)", "vampire(4)"],
        }
        self.EVENTS = {
            "wolf_numkills": EventListener(self.on_wolf_numkills),
            "chk_nightdone": EventListener(self.on_chk_nightdone),
            "chk_win": EventListener(self.on_chk_win),
            "team_win": EventListener(self.on_team_win),
            "start_game": EventListener(self.on_start_game),
            "send_role": EventListener(self.on_send_role, priority=10),
            "transition_day_begin": EventListener(self.on_transition_day_begin),
            "night_kills": EventListener(self.on_night_kills),
            "update_stats": EventListener(self.on_update_stats),
            "begin_day": EventListener(self.on_begin_day),
            "transition_night_begin": EventListener(self.on_transition_night_begin),
            "lynch": EventListener(self.on_lynch),
            "del_player": EventListener(self.on_del_player),
        }

        self.MESSAGE_OVERRIDES = {
            "villagers_vote": "pactbreaker_villagers_vote",
            # all of these include pactbreaker_notify at the end of them to inform about the visit and pass commands
            "wolf_notify": "pactbreaker_wolf_notify",
            "vampire_notify": "pactbreaker_vampire_notify",
            "vigilante_notify": "pactbreaker_vigilante_notify",
            "villager_notify": "pactbreaker_villager_notify",
        }

        def dfd():
            return DefaultUserDict(set)

        self.visiting: UserDict[User, Location] = UserDict()
        # only populated/used during transition_day so it doesn't need to be a user container
        self.night_kills: dict[User, User] = {}
        self.drained = UserSet()
        self.active_players = UserSet()
        self.hobbies: UserDict[User, int] = UserDict()
        # evidence strings: hobby, forest, hard
        self.collected_evidence: DefaultUserDict[User, DefaultUserDict[User, set]] = DefaultUserDict(dfd)
        kwargs = dict(chan=False, pm=True, playing=True, phases=("night",), register=False)
        self.pass_command = command("pass", **kwargs)(self.stay_home)
        self.visit_command = command("visit", **kwargs)(self.visit)

        hobby_message = messages.raw("pactbreaker_hobby_message")
        hobby_evidence_1 = messages.raw("pactbreaker_hobby_evidence_1")
        hobby_evidence_2 = messages.raw("pactbreaker_hobby_evidence_2")
        forest_evidence = messages.raw("pactbreaker_forest_evidence")
        assert len(hobby_message) >= 3
        assert len(hobby_message) == len(hobby_evidence_1) == len(hobby_evidence_2) == len(forest_evidence)

    def startup(self):
        super().startup()
        self.active_players.clear()
        self.hobbies.clear()
        self.drained.clear()
        self.night_kills.clear()
        self.collected_evidence.clear()
        self.visiting.clear()
        # register !visit and !pass, remove all role commands
        self.visit_command.register()
        self.pass_command.register()
        wolf_kill.remove()
        wolf_retract.remove()
        vampire_bite.remove()
        vampire_retract.remove()
        vigilante_kill.remove()
        vigilante_retract.remove()
        vigilante_pass.remove()

    def teardown(self):
        super().teardown()
        self.visit_command.remove()
        self.pass_command.remove()
        wolf_kill.register()
        wolf_retract.register()
        vampire_bite.register()
        vampire_retract.register()
        vigilante_kill.register()
        vigilante_retract.register()
        vigilante_pass.register()

    def on_del_player(self, evt: Event, var: GameState, player, all_roles, death_triggers):
        # self.night_kills isn't updated because it is short-lived
        # and won't have del_player run in the middle of it in a way that matters
        self.active_players.discard(player)
        self.drained.discard(player)
        del self.hobbies[:player:]
        del self.visiting[:player:]
        if player in self.collected_evidence:
            del self.collected_evidence[player]
        for p, stuff in self.collected_evidence.items():
            if player in stuff:
                del stuff[player]

    def on_start_game(self, evt: Event, var: GameState, mode_name: str, mode: GameMode):
        # mark every player as active at start of game
        pl = get_players(var)
        self.active_players.update(pl)

        # assign hobbies to players
        # between 2-3 hobbies in any particular game, depending on the number of wolves
        num_wolves = len(get_players(var, ("wolf",)))
        num_hobbies = min(3, max(2, num_wolves))
        total_hobbies = len(messages.raw("pactbreaker_hobby_message"))
        hobby_indexes = random.sample(range(total_hobbies), num_hobbies)
        i = 0
        random.shuffle(pl)
        for player in pl:
            self.hobbies[player] = hobby_indexes[i]
            i = (i + 1) % num_hobbies

    def on_send_role(self, evt: Event, var: GameState):
        pl = get_players(var)
        for player in pl:
            # wolf, vigilante, and vampire already got a player list from their send_role event,
            # so only give this to villagers
            if get_main_role(var, player) == "villager":
                ps = pl[:]
                random.shuffle(ps)
                ps.remove(player)
                player.send(messages["players_list"].format(ps))
            # on first night, inform the player of their hobby
            if var.night_count == 1:
                player.send(messages.get("pactbreaker_hobby_message", self.hobbies[player]))

    def on_chk_nightdone(self, evt: Event, var: GameState):
        evt.data["acted"].clear()
        evt.data["nightroles"].clear()
        evt.data["acted"].extend(self.visiting)
        evt.data["nightroles"].extend(self.active_players)
        evt.stop_processing = True

    def on_transition_night_begin(self, evt: Event, var: GameState):
        # figure out who is in the stocks (if anyone)
        stocks_players = set(get_players(var)) - self.active_players
        for player in stocks_players:
            move_player(var, player, VillageSquare)

    def on_transition_day_begin(self, evt: Event, var: GameState):
        # resolve night visits on a per-location basis
        self.night_kills.clear()
        visited: dict[Location, set[User]] = defaultdict(set)
        for player, location in self.visiting.items():
            visited[location].add(player)

        for location, visitors in visited.items():
            if not visitors:
                continue

            if location is Forest:
                wolves = get_players(var, ("wolf",))
                non_wolves = [x for x in visitors if x not in wolves]
                deck = []
                for wolf in wolves:
                    deck.append(("evidence", wolf))
                    deck.append(("hunted" if wolf in visitors else "evidence", wolf))
                while len(deck) < max(10, len(non_wolves)):
                    deck.append(("empty-handed", None))

                random.shuffle(deck)
                for i, visitor in enumerate(non_wolves):
                    role = get_main_role(var, visitor)
                    card, wolf = deck[i]
                    if card == "evidence" or (card == "hunted" and role == "vigilante"):
                        if "forest" in self.collected_evidence[visitor][wolf]:
                            # already got forest evidence for this wolf; treat as empty-handed instead
                            visitor.send(messages["pactbreaker_forest_empty"])
                        else:
                            self.collected_evidence[visitor][wolf].add("forest")
                            visitor.send(messages.get("pactbreaker_forest_evidence", self.hobbies[wolf]))
                    elif card == "hunted" and role == "vampire":
                        self.collected_evidence[wolf][visitor].add("hard")
                        wolf.send(messages["pactbreaker_hunter_vampire"].format(visitor))
                        wolf.send(messages["pactbreaker_hunted_vampire"])
                    elif card == "hunted":
                        self.night_kills[visitor] = wolf
                        wolf.send(messages["pactbreaker_hunter"].format(visitor))
                        visitor.send(messages["pactbreaker_hunted"])
                    else:
                        visitor.send(messages["pactbreaker_forest_empty"])
            elif location is VillageSquare:
                deck = []
                # figure out who is in the stocks (if anyone)
                stocks_players = set(get_players(var)) - self.active_players
                if stocks_players:
                    deck.append(("evidence", None))
                    deck.append(("evidence", None))
                for visitor in visitors:
                    role = get_main_role(var, visitor)
                    if role == "wolf":
                        deck.append(("hunted", visitor))
                    elif role == "vampire":
                        deck.append(("drained", visitor))
                    elif role == "vigilante":
                        deck.append(("exposed", visitor))
                while len(deck) < 5:
                    deck.append(("empty-handed", None))
                if len(visitors) > 5:
                    for i in range(len(visitors) - 5):
                        deck.append(("empty-handed", None))

                # at most one person can be in the stocks; this simplifies some later logic
                target = list(stocks_players)[0] if stocks_players else None
                target_role = get_main_role(var, target) if target else None
                random.shuffle(deck)
                for i, visitor in enumerate(visitors):
                    role = get_main_role(var, visitor)
                    card, actor = deck[i]
                    # certain roles treat their own cards as evidence instead (or empty-handed if stocks are empty)
                    if ((role == "wolf" and card == "hunted") or (role == "vampire" and card == "drained")
                       or (role == "vigilante" and card == "exposed")):
                        card = "evidence" if stocks_players else "empty-handed"

                    if role == "wolf" and card == "evidence":
                        # wolves kill the player in the stocks (even vampires)
                        if target_role == "wolf":
                            # but don't kill other wolves
                            visitor.send(messages["pactbreaker_square_empty"])
                        elif target in self.night_kills:
                            killer_role = get_main_role(var, self.night_kills[target])
                            if killer_role in ("wolf", "vigilante"):
                                # target is already being killed; treat as empty-handed instead
                                visitor.send(messages["pactbreaker_square_empty"])
                            else:
                                visitor.send(messages["pactbreaker_hunter_square"].format(target))
                                self.night_kills[target] = visitor
                        else:
                            visitor.send(messages["pactbreaker_hunter_square"].format(target))
                            self.night_kills[target] = visitor
                    elif role == "vampire" and card == "evidence":
                        # vampires drain the player in the stocks
                        # this is tracked in night_deaths and resolved to a drain later,
                        # so that wolves/vigilantes can override with actual kills
                        if target_role == "vampire":
                            # but don't drain other vampires
                            visitor.send(messages["pactbreaker_square_empty"])
                        elif target not in self.night_kills:
                            self.night_kills[target] = visitor
                        else:
                            # target is already being killed; treat as empty-handed instead
                            visitor.send(messages["pactbreaker_square_empty"])
                    elif role == "vigilante" and card == "evidence":
                        # vigilantes kill the player in the stocks if they have hard evidence on them,
                        # otherwise they gain hard evidence
                        if "hard" in self.collected_evidence[visitor][target]:
                            if target in self.night_kills:
                                killer_role = get_main_role(var, self.night_kills[target])
                                if killer_role in ("wolf", "vigilante"):
                                    # target is already being killed; treat as empty-handed instead
                                    visitor.send(messages["pactbreaker_square_empty"])
                                else:
                                    visitor.send(messages["pactbreaker_square_kill"].format(target, target_role))
                                    self.night_kills[target] = visitor
                            else:
                                visitor.send(messages["pactbreaker_square_kill"].format(target, target_role))
                                self.night_kills[target] = visitor
                        else:
                            self.collected_evidence[visitor][target].add("hard")
                            visitor.send(messages["pactbreaker_stocks"].format(target, get_main_role(var, target)))
                    elif card == "evidence":
                        # villagers gain hard evidence on the players in the stocks
                        for target in stocks_players:
                            self.collected_evidence[visitor][target].add("hard")
                            visitor.send(messages["pactbreaker_stocks"].format(target, get_main_role(var, target)))
                    elif role == "vampire" and card == "hunted":
                        # vampires give wolves hard evidence when a hunted card is drawn
                        actor.send(messages["pactbreaker_hunter_vampire"].format(visitor))
                        visitor.send(messages["pactbreaker_hunted_vampire"])
                    elif card == "hunted":
                        # vigilantes and villagers get killed by the wolf
                        self.night_kills[visitor] = actor
                        actor.send(messages["pactbreaker_hunter"].format(visitor))
                        visitor.send(messages["pactbreaker_hunted"])
                    elif card == "drained":
                        # non-vampires get drained by the vampire (messages deferred until night kill resolution)
                        self.night_kills[visitor] = actor
                    elif card == "exposed":
                        # non-vigilantes gain hard evidence about the vigilante
                        # (the vigilante is not aware of this)
                        self.collected_evidence[visitor][actor].add("hard")
                        visitor.send(messages["pactbreaker_exposed"].format(actor))
                    else:
                        visitor.send(messages["pactbreaker_square_empty"])
            else:
                # location is a house
                owner = None
                for player in get_players(var):
                    if get_home(var, player) is location:
                        owner = player
                        break

                assert owner is not None
                is_home = owner in visitors
                visitors.discard(owner)
                num_visitors = len(visitors)
                num_vampires = len([x for x in visitors if get_main_role(var, x) == "vampire"])
                owner_role = get_main_role(var, owner)
                deck = ["empty-handed",
                        "empty-handed",
                        "empty-handed",
                        "empty-handed" if owner_role in ("villager", "vampire", "vigilante") else "evidence",
                        "empty-handed" if owner_role == "villager" or is_home else "evidence"]
                if num_visitors > 5:
                    for i in range(num_visitors - 5):
                        deck.append("empty-handed")
                random.shuffle(deck)
                for i, visitor in enumerate(visitors):
                    card = deck[i]
                    role = get_main_role(var, visitor)
                    if (is_home and role == "vigilante" and "hard" in self.collected_evidence[visitor][owner]
                       and owner_role in ("wolf", "vampire")):
                        # vigilantes will murder a known wolf or vampire if they're home
                        self.night_kills[owner] = visitor
                        visitor.send(messages["pactbreaker_house_kill"].format(owner, owner_role))
                        owner.send(messages["pactbreaker_house_killed"])
                    elif (not is_home and "hard" in self.collected_evidence[visitor][owner]
                          and owner_role == "vampire" and role != "vampire"):
                        # non-vampires destroy known vampires that aren't home
                        # no message to the vampire yet because I can't figure out a good way to do this;
                        # might need to re-do the entire night death message system to postpone them until night_kills
                        # (e.g. vampire might be in stocks and murdered more directly by vigilante)
                        self.night_kills[owner] = visitor
                        visitor.send(messages["pactbreaker_house_vampire"].format(owner))
                    elif "hobby" not in self.collected_evidence[visitor][owner]:
                        # if the visitor doesn't have hobby evidence yet, that's what they get
                        # 100% chance if the owner isn't home, 50% if they are
                        if not is_home:
                            self.collected_evidence[visitor][owner].add("hobby")
                            visitor.send(messages.get("pactbreaker_hobby_evidence_1", self.hobbies[owner]).format(owner))
                        elif random.choice([True, False]):
                            self.collected_evidence[visitor][owner].add("hobby")
                            visitor.send(messages.get("pactbreaker_hobby_evidence_2", self.hobbies[owner]).format(owner))
                    elif card == "evidence":
                        self.collected_evidence[visitor][owner].add("hard")
                        if not is_home:
                            visitor.send(messages["pactbreaker_house_evidence_1"].format(owner, owner_role))
                        else:
                            visitor.send(messages["pactbreaker_house_evidence_2"].format(owner, owner_role))
                    elif is_home:
                        visitor.send(messages["pactbreaker_house_empty_2"].format(owner))
                    else:
                        visitor.send(messages["pactbreaker_house_empty_1"].format(owner))

                if not is_home and num_vampires > 0 and num_vampires >= num_visitors / 2:
                    # vampires outnumber non-vampires; drain the non-vampires
                    vampires = [x for x in visitors if get_main_role(var, x) == "vampire"]
                    i = 0
                    for visitor in visitors:
                        if get_main_role(var, visitor) == "vampire":
                            continue
                        if visitor not in self.night_kills:
                            self.night_kills[visitor] = vampires[i]
                            i += 1

    def on_night_kills(self, evt: Event, var: GameState):
        for victim, killer in self.night_kills.items():
            victim_role = get_main_role(var, victim)
            killer_role = get_main_role(var, killer)
            if killer_role == "vampire" and victim not in self.drained:
                # first hit from a vampire drains the target instead of killing them
                self.drained.add(victim)
                victim.send(messages["pactbreaker_drained"])
                killer.send(messages["pactbreaker_drain"].format(victim))
            elif killer_role == "vampire" and victim_role == "vigilante":
                # if the vampire fully drains a vigilante, they turn into a vampire instead of dying
                killer.send(messages["pactbreaker_drain_turn"].format(victim))
                change_role(var, victim, victim_role, "vampire", message="pactbreaker_drain_turn")
                # get rid of the new vampire's drained condition and all hard evidence against the former vigilante
                self.drained.discard(victim)
                for collector, evidence in self.collected_evidence.items():
                    evidence[victim].discard("hard")
            elif killer_role == "vampire":
                # death, but also give messages
                evt.data["victims"].add(victim)
                evt.data["killers"][victim].append(killer)
                victim.send(messages["pactbreaker_drained_dead"])
                killer.send(messages["pactbreaker_drain_kill"].format(victim))
            else:
                # actual death
                evt.data["victims"].add(victim)
                evt.data["killers"][victim].append(killer)

    def on_begin_day(self, evt: Event, var: GameState):
        # every player is active again (stocks only lasts for one night)
        self.active_players.clear()
        self.active_players.update(get_players(var))
        self.visiting.clear()
        self.night_kills.clear()

    def on_lynch(self, evt: Event, var: GameState, votee: User, voters: Iterable[User]):
        channels.Main.send(messages["pactbreaker_vote"].format(votee))
        self.active_players.discard(votee)
        # don't kill the votee
        evt.prevent_default = True

    def on_wolf_numkills(self, evt: Event, var: GameState, wolf):
        evt.data["numkills"] = 0

    def on_update_stats(self, evt: Event, var: GameState, player, main_role, reveal_role, all_roles):
        if main_role == "vampire":
            evt.data["possible"].add("vigilante")

    def on_chk_win(self, evt: Event, var: GameState, rolemap, mainroles, lpl, lwolves, lrealwolves, lvampires):
        num_vigilantes = len(get_players(var, ("vigilante",), mainroles=mainroles))

        if evt.data["winner"] == "villagers":
            evt.data["message"] = messages["pactbreaker_vigilante_win"]
        elif evt.data["winner"] in ("wolves", "vampires"):
            # This isn't a win unless all vigilantes are dead
            if num_vigilantes == 0:
                evt.data["winner"] = None
            else:
                # All vigilantes are dead, so this is an actual win
                # Message keys used: pactbreaker_wolf_win pactbreaker_vampire_win
                key = LocalRole.from_en(evt.data["winner"]).singular
                evt.data["message"] = messages["pactbreaker_{0}_win".format(key)]
        elif num_vigilantes == 0 and lvampires == 0:
            # wolves (and villagers) win even if there is a minority of wolves as long as
            # the vigilantes and vampires are all dead
            evt.data["winner"] = "wolves"
            evt.data["message"] = messages["pactbreaker_wolf_win"]
        elif lvampires >= lpl / 2:
            # vampires can win even with wolves and vigilante alive if they outnumber the village
            evt.data["winner"] = "vampires"
            evt.data["message"] = messages["pactbreaker_vampire_win"]

    def on_team_win(self, evt: Event, var: GameState, player: User, main_role: str, all_roles: Iterable[str], winner: str):
        if winner == "wolves" and main_role == "villager":
            evt.data["team_win"] = True

    def stay_home(self, wrapper: MessageDispatcher, message: str):
        """Stay at home tonight."""
        self.visiting[wrapper.source] = get_home(wrapper.source.game_state, wrapper.source)
        wrapper.pm(messages["no_visit"])

    def visit(self, wrapper: MessageDispatcher, message: str):
        """Visit a location to collect evidence."""
        if wrapper.source not in self.active_players:
            wrapper.pm(messages["pactbreaker_no_visit"])
            return

        var = wrapper.game_state
        prefix = re.split(" +", message)[0]
        aliases = {
            "forest": messages.raw("_commands", "forest"),
            "square": messages.raw("_commands", "square"),
        }

        # We do a user match here, but since we also support locations, we make fake users for them.
        # It's rather hacky, but the most elegant implementation since it allows for correct disambiguation messages.
        # These fakes all use the bot account to ensure they are selectable even when someone has the same nick.
        scope = get_players(var)
        scope.extend(FakeUser(None, als, loc, loc, users.Bot.account) for loc, x in aliases.items() for als in x)
        target_player = get_target(wrapper, prefix, allow_self=True, scope=scope)
        if not target_player:
            return

        if target_player.account == users.Bot.account:
            target_location = Location(target_player.host)
            is_special = True
        elif target_player is wrapper.source:
            self.stay_home(wrapper, message)
            return
        else:
            target_location = get_home(var, target_player)
            is_special = False

        self.visiting[wrapper.source] = target_location
        if is_special:
            wrapper.pm(messages["pactbreaker_visiting_{0}".format(target_location.name)])
        else:
            wrapper.pm(messages["pactbreaker_visiting_house"].format(target_player))

        # relay to wolfchat/vampire chat as appropriate
        if is_special:
            relay_key = "pactbreaker_relay_visit_{0}".format(target_location.name)
        else:
            relay_key = "pactbreaker_relay_visit_house"

        player_role = get_main_role(var, wrapper.source)
        if player_role in Wolf:
            # command is "kill" so that this is relayed even if gameplay.wolfchat.only_kill_command is true
            send_wolfchat_message(var,
                                  wrapper.source,
                                  messages[relay_key].format(wrapper.source, target_player),
                                  Wolf,
                                  role="wolf",
                                  command="kill")
        elif player_role in Vampire:
            # same logic as wolfchat for why we use "bite" as the command here
            send_vampire_chat_message(var,
                                      wrapper.source,
                                      messages[relay_key].format(wrapper.source, target_player),
                                      Vampire,
                                      cmd="bite")
