from __future__ import annotations

import random
import re
from collections import defaultdict
from typing import Iterable, Optional

from src import users, channels
from src.users import User, FakeUser
from src.containers import UserSet, UserDict, DefaultUserDict
from src.decorators import command
from src.dispatcher import MessageDispatcher
from src.events import Event, EventListener
from src.functions import get_players, get_main_role, get_target, change_role
from src.gamemodes import game_mode, GameMode
from src.gamestate import GameState
from src.messages import messages, LocalRole
from src.locations import move_player, get_home, Location, VillageSquare, Forest
from src.cats import Wolf, Vampire
from src.status import add_protection, add_lynch_immunity
from src.roles.helper.wolves import send_wolfchat_message, wolf_kill, wolf_retract
from src.roles.vampire import send_vampire_chat_message, vampire_bite, vampire_retract
from src.roles.vampire import on_player_protected as vampire_drained
from src.roles.vigilante import vigilante_retract, vigilante_pass, vigilante_kill

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
            "night_kills": EventListener(self.on_night_kills),
            "player_protected": EventListener(self.on_player_protected),
            "night_death_message": EventListener(self.on_night_death_message),
            "transition_day_resolve": EventListener(self.on_transition_day_resolve),
            "update_stats": EventListener(self.on_update_stats),
            "begin_day": EventListener(self.on_begin_day),
            "transition_night_begin": EventListener(self.on_transition_night_begin),
            "lynch": EventListener(self.on_lynch),
            "abstain": EventListener(self.on_abstain),
            "lynch_immunity": EventListener(self.on_lynch_immunity),
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

        # messages to send on night kills; only populated during transition_day so user containers are unnecessary
        self.night_kill_messages: dict[tuple[User, User], Optional[Location]] = {}
        self.visiting: UserDict[User, Location] = UserDict()
        self.prev_visiting: UserDict[User, Location] = UserDict()
        self.drained = UserSet()
        self.voted: DefaultUserDict[User, int] = DefaultUserDict(int)
        self.last_voted: Optional[User] = None
        self.active_players = UserSet()
        self.collected_evidence: DefaultUserDict[User, UserSet] = DefaultUserDict(UserSet)
        dfd = lambda: DefaultUserDict(int)
        # keep track of how many times a player has visited another player's house
        # each subsequent visit increases the likelihood of the player discovering evidence
        self.visit_count: DefaultUserDict[User, DefaultUserDict[User, int]] = DefaultUserDict(dfd)
        kwargs = dict(chan=False, pm=True, playing=True, phases=("night",), register=False)
        self.pass_command = command("pass", **kwargs)(self.stay_home)
        self.visit_command = command("visit", **kwargs)(self.visit)

    def startup(self):
        super().startup()
        self.night_kill_messages.clear()
        self.active_players.clear()
        self.voted.clear()
        self.drained.clear()
        self.collected_evidence.clear()
        self.visiting.clear()
        self.prev_visiting.clear()
        # register !visit and !pass, remove all role commands
        self.visit_command.register()
        self.pass_command.register()
        self.last_voted = None
        wolf_kill.remove()
        wolf_retract.remove()
        vampire_bite.remove()
        vampire_retract.remove()
        vampire_drained.remove()
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
        vampire_drained.install()
        vigilante_kill.register()
        vigilante_retract.register()
        vigilante_pass.register()

    def on_del_player(self, evt: Event, var: GameState, player, all_roles, death_triggers):
        # self.night_kills isn't updated because it is short-lived
        # and won't have del_player run in the middle of it in a way that matters
        self.active_players.discard(player)
        self.drained.discard(player)
        del self.visiting[:player:]
        del self.voted[:player:]
        del self.visit_count[:player:]
        if player in self.collected_evidence.items():
            del self.collected_evidence[player]
        for _, others in self.collected_evidence.items():
            others.discard(player)
        for _, others in self.visit_count.items():
            del others[:player:]
        if self.last_voted is player:
            self.last_voted = None

    def on_start_game(self, evt: Event, var: GameState, mode_name: str, mode: GameMode):
        # mark every player as active at start of game
        pl = get_players(var)
        self.active_players.update(pl)

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

    def on_night_kills(self, evt: Event, var: GameState):
        self.night_kill_messages.clear()

        # vampire drained logic
        for player in self.active_players - self.drained:
            # mark un-drained players as eligible for draining (except for players in stocks; they die in one hit)
            add_protection(var, player, None, "vampire", Vampire)

        for player in set(get_players(var, ("vigilante",))):
            # mark vigilantes as eligible for turning into vampires
            add_protection(var, player, None, "vigilante", Vampire, 10)

        # resolve night visits on a per-location basis
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
                    deck.append(("evidence", wolf))
                    if wolf in visitors:
                        deck.append(("hunted", wolf))
                        deck.append(("hunted", wolf))
                while len(deck) < max(8, len(non_wolves)):
                    deck.append(("empty-handed", None))

                random.shuffle(deck)
                for i, visitor in enumerate(non_wolves):
                    role = get_main_role(var, visitor)
                    card, wolf = deck[i]
                    if card == "evidence":
                        wolf_list = [wolf]
                        choices = [x for x in get_players(var) if x not in (wolf, visitor)]
                        if role != "vampire" and len(choices) >= 4:
                            wolf_list.extend(random.sample(choices, int(len(choices) / 4) + 2))
                        # give a list of potential wolves (at least one of which is wolf)
                        if len(wolf_list) == 1:
                            visitor.send(messages["pactbreaker_forest_evidence_single"].format(wolf))
                            self.collected_evidence[visitor].add(wolf)
                        else:
                            visitor.send(messages["pactbreaker_forest_evidence"].format(wolf_list))
                    elif card == "hunted" and role == "vampire":
                        self.collected_evidence[wolf].add(visitor)
                        wolf.send(messages["pactbreaker_hunter_vampire"].format(visitor))
                        wolf.send(messages["pactbreaker_hunted_vampire"])
                    elif card == "hunted":
                        evt.data["victims"].add(visitor)
                        evt.data["killers"][visitor].append(wolf)
                        self.night_kill_messages[(wolf, visitor)] = location
                    else:
                        visitor.send(messages["pactbreaker_forest_empty"])
            elif location is VillageSquare:
                deck = [("empty-handed", None)]
                # figure out who is in the stocks (if anyone)
                stocks_players = set(get_players(var)) - self.active_players
                for visitor in visitors:
                    role = get_main_role(var, visitor)
                    if role == "wolf":
                        deck.append(("hunted", visitor))
                    elif role == "vampire":
                        # vampires have a higher chance of draining people when hunting in the square
                        deck.append(("drained", visitor))
                        deck.append(("drained", visitor))
                    elif role == "vigilante":
                        deck.append(("exposed", visitor))
                while len(deck) < 8:
                    deck.append(("evidence", None))
                if len(visitors) > 8:
                    for i in range(len(visitors) - 8):
                        deck.append(("empty-handed", None))

                # at most one person can be in the stocks; this simplifies some later logic
                target = list(stocks_players)[0] if stocks_players else None
                target_role = get_main_role(var, target) if target else None
                evidence_sharing = []
                random.shuffle(deck)
                for i, visitor in enumerate(visitors):
                    role = get_main_role(var, visitor)
                    card, actor = deck[i]
                    # killing roles with evidence on the person in the stocks treat drawing an evidence
                    # card as drawing the card that lets them kill the person in the stocks instead
                    evidence_special = card == "evidence" and target in self.collected_evidence[visitor]
                    if role == "wolf" and (card == "hunted" or evidence_special):
                        # wolves kill the player in the stocks (even vampires)
                        if not target or target_role == "wolf":
                            # but don't kill other wolves
                            visitor.send(messages["pactbreaker_square_empty"])
                        else:
                            evt.data["victims"].add(target)
                            evt.data["killers"][target].append(visitor)
                            self.night_kill_messages[(visitor, target)] = location
                    elif role == "vampire" and (card == "drained" or evidence_special):
                        # vampires fully drain the player in the stocks
                        if not target or target_role == "vampire":
                            # but don't drain other vampires
                            visitor.send(messages["pactbreaker_square_empty"])
                        else:
                            evt.data["victims"].add(target)
                            evt.data["killers"][target].append(visitor)
                            evt.data["kill_priorities"][actor] = 10
                            self.night_kill_messages[(visitor, target)] = location
                    elif role == "vigilante" and (card == "exposed" or evidence_special):
                        # vigilantes kill the player in the stocks if they have hard evidence on them,
                        # otherwise they gain hard evidence
                        if not target:
                            # nobody in the stocks
                            visitor.send(messages["pactbreaker_square_empty"])
                        elif target in self.collected_evidence[visitor]:
                            evt.data["victims"].add(target)
                            evt.data["killers"][target].append(visitor)
                            self.night_kill_messages[(visitor, target)] = location
                        else:
                            # vigilante is the only role capable of gaining evidence from people in the stocks
                            self.collected_evidence[visitor].add(target)
                            visitor.send(messages["pactbreaker_stocks"].format(target, get_main_role(var, target)))
                    elif role == "vampire" and card == "hunted":
                        # vampires give wolves evidence when a hunted card is drawn
                        actor.send(messages["pactbreaker_hunter_vampire"].format(visitor))
                        visitor.send(messages["pactbreaker_hunted_vampire"])
                    elif card == "hunted":
                        # vigilantes and villagers get killed by the wolf
                        evt.data["victims"].add(visitor)
                        evt.data["killers"][visitor].append(actor)
                        self.night_kill_messages[(actor, visitor)] = location
                    elif card == "drained":
                        # non-vampires get drained by the vampire
                        evt.data["victims"].add(visitor)
                        evt.data["killers"][visitor].append(actor)
                        evt.data["kill_priorities"][actor] = 10
                        self.night_kill_messages[(actor, visitor)] = location
                    elif card == "exposed":
                        # non-vigilantes gain evidence about the vigilante
                        # (the vigilante is not aware of this)
                        self.collected_evidence[visitor].add(actor)
                        visitor.send(messages["pactbreaker_exposed"].format(actor))
                    elif card == "evidence":
                        # share evidence with every other player who has drawn an evidence card
                        evidence_sharing.append(visitor)
                    else:
                        visitor.send(messages["pactbreaker_square_empty"])

                # calculate shared evidence
                shared_evidence = set()
                for visitor in evidence_sharing:
                    # extra set() wrapper to make PyCharm infer the types correctly
                    shared_evidence.update(set(self.collected_evidence[visitor]))
                for visitor in evidence_sharing:
                    if not shared_evidence:
                        # nobody has evidence to share, so everyone treats this as empty-handed instead
                        visitor.send(messages["pactbreaker_square_empty"])
                        continue
                    if shared_evidence - self.collected_evidence[visitor] - {visitor}:
                        entries = []
                        for target in shared_evidence - self.collected_evidence[visitor] - {visitor}:
                            entries.append(messages["players_list_entry"].format(target, "", (get_main_role(var, target),)))
                        visitor.send(messages["pactbreaker_square_share"].format(entries))
                        self.collected_evidence[visitor].update(shared_evidence - {visitor})
                    else:
                        visitor.send(messages["pactbreaker_square_share_nothing"])
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
                total_draws = 0
                for visitor in visitors:
                    self.visit_count[visitor][owner] += 1
                    total_draws += self.visit_count[visitor][owner]

                vampires = [x for x in visitors if get_main_role(var, x) == "vampire"]
                num_vampires = len(vampires)
                owner_role = get_main_role(var, owner)
                deck = ["empty-handed",
                        "empty-handed" if owner_role != "wolf" else "evidence",
                        "empty-handed" if owner_role != "villager" or is_home else "evidence",
                        "empty-handed" if is_home else "evidence"]
                if total_draws > 4:
                    for i in range(total_draws - 4):
                        deck.append("empty-handed")
                random.shuffle(deck)
                i = 0
                for visitor in visitors:
                    draws = self.visit_count[visitor][owner]
                    cards = deck[i:i+draws]
                    i += draws
                    role = get_main_role(var, visitor)
                    have_evidence = owner in self.collected_evidence[visitor]
                    if role == "vigilante" and have_evidence and owner_role in ("wolf", "vampire"):
                        # vigilantes will murder a known wolf or vampire by visiting their house
                        evt.data["victims"].add(owner)
                        evt.data["killers"][owner].append(visitor)
                        self.night_kill_messages[(visitor, owner)] = location
                    elif not is_home and have_evidence and owner_role == "vampire" and role != "vampire":
                        # non-vampires destroy known vampires that aren't home
                        evt.data["victims"].add(owner)
                        evt.data["killers"][owner].append(visitor)
                        evt.data["kill_priorities"][visitor] = 5
                        self.night_kill_messages[(visitor, owner)] = location
                    elif "evidence" in cards:
                        self.collected_evidence[visitor].add(owner)
                        if not is_home:
                            visitor.send(messages["pactbreaker_house_evidence_1"].format(owner, owner_role))
                        else:
                            visitor.send(messages["pactbreaker_house_evidence_2"].format(owner, owner_role))
                    elif is_home and role == "vampire" and owner_role != "vampire":
                        # vampires bite the owner if they're staying at home (unless they got evidence above)
                        evt.data["victims"].add(owner)
                        evt.data["killers"][owner].append(visitor)
                        evt.data["kill_priorities"][visitor] = 10
                        self.night_kill_messages[(visitor, owner)] = location
                    elif is_home:
                        visitor.send(messages["pactbreaker_house_empty_2"].format(owner))
                    else:
                        visitor.send(messages["pactbreaker_house_empty_1"].format(owner))

                if not is_home and num_vampires > 0 and num_vampires >= num_visitors / 2:
                    # vampires outnumber non-vampires; drain the non-vampires
                    i = 0
                    for visitor in visitors:
                        if get_main_role(var, visitor) == "vampire":
                            continue
                        evt.data["victims"].add(visitor)
                        evt.data["killers"][visitor].append(vampires[i])
                        evt.data["kill_priorities"][vampires[i]] = 10
                        self.night_kill_messages[(vampires[i], visitor)] = location
                        i += 1

    def on_player_protected(self,
                            evt: Event,
                            var: GameState,
                            target: User,
                            attacker: Optional[User],
                            attacker_role: str,
                            protector: Optional[User],
                            protector_role: str,
                            reason: str):
        if protector_role == "vampire":
            self.drained.add(target)
            attacker.send(messages["pactbreaker_drain"].format(target))
            target.send(messages["pactbreaker_drained"])
            # mark that the player has successfully killed so we don't give them an empty-handed message later
            self.night_kill_messages[(attacker, target)] = None
        elif protector_role == "vigilante":
            # if the vampire fully drains a vigilante, they might turn into a vampire instead of dying
            # this protection triggering means they should turn
            attacker.send(messages["pactbreaker_drain_turn"].format(target))
            change_role(var, target, get_main_role(var, target), "vampire", message="pactbreaker_drained_vigilante")
            # get rid of the new vampire's drained condition and all evidence against the former vigilante
            # this is a subtle info leak as the vigilante's name will disappear in lists when sharing evidence,
            # but it's probably not worth introducing a new concept of stale evidence to counteract that
            # Note: if we ever introduce a command (or put it into !myrole) to check your own collected evidence
            # then we would need to do the stale evidence thing to avoid making it *too* easy to discern a turned vig
            self.drained.discard(target)
            for _, targets in self.collected_evidence.items():
                targets.discard(target)

    def on_night_death_message(self, evt: Event, var: GameState, victim: User, killer: User | str):
        victim_role = get_main_role(var, victim)
        killer_role = get_main_role(var, killer)
        location = self.night_kill_messages[(killer, victim)]

        if killer_role == "vampire":
            victim.send(messages["pactbreaker_drained_dead"])
            killer.send(messages["pactbreaker_drain_kill"].format(victim))
        elif killer_role == "wolf" and victim not in self.active_players and location is VillageSquare:
            victim.send(messages["pactbreaker_hunted"])
            killer.send(messages["pactbreaker_hunter_square"].format(victim))
        elif victim_role == "vampire" and location is get_home(var, victim):
            victim.send(messages["pactbreaker_house_daylight"])
            killer.send(messages["pactbreaker_house_vampire"].format(victim))
        elif killer_role == "wolf":
            victim.send(messages["pactbreaker_hunted"])
            killer.send(messages["pactbreaker_hunter"].format(victim))
        elif killer_role == "vigilante" and location is get_home(var, victim):
            victim.send(messages["pactbreaker_bolted"])
            killer.send(messages["pactbreaker_house_kill"].format(victim, victim_role))
        elif killer_role == "vigilante" and location is VillageSquare:
            victim.send(messages["pactbreaker_bolted"])
            killer.send(messages["pactbreaker_square_kill"].format(victim, victim_role))
        else:
            # shouldn't happen; indicates a bug in the mode
            raise RuntimeError("Unknown night death situation")

        # mark that the player has successfully killed so we don't give them an empty-handed message later
        self.night_kill_messages[(killer, victim)] = None

    def on_transition_day_resolve(self, evt: Event, var: GameState, dead: set[User], killers: dict[User, User | str]):
        # check for players meant to kill someone but got their kill pre-empted by someone else
        # report the appropriate empty-handed message to them instead
        # this happens if *all* of their entries still have a location defined
        killed = {p for (p, _), l in self.night_kill_messages.items() if l is None}

        for (player, _), location in self.night_kill_messages.items():
            if player in killed:
                continue

            if location is Forest:
                player.send(messages["pactbreaker_forest_empty"])
            elif location is VillageSquare:
                player.send(messages["pactbreaker_square_empty"])
            else:
                # we can no longer tell whether or not the owner stayed home; they've already been
                # cleared from visitor lists. So, always give the message as if house was unoccupied
                owner = [x for x in get_players(var) if get_home(var, x) is location][0]
                player.send(messages["pactbreaker_house_empty_1"].format(owner))

        self.night_kill_messages.clear()

    def on_begin_day(self, evt: Event, var: GameState):
        # every player is active again (stocks only lasts for one night)
        self.active_players.clear()
        self.active_players.update(get_players(var))
        self.prev_visiting.clear()
        self.prev_visiting.update(self.visiting)
        self.visiting.clear()
        # if someone was locked up last night, ensure they can't be locked up again tonight
        if self.last_voted is not None:
            add_lynch_immunity(var, self.last_voted, "pactbreaker")

    def on_lynch(self, evt: Event, var: GameState, votee: User, voters: Iterable[User]):
        self.last_voted = votee
        self.voted[votee] += 1
        if self.voted[votee] < 3:
            channels.Main.send(messages["pactbreaker_vote"].format(votee))
            self.active_players.discard(votee)
            # don't kill the votee
            evt.prevent_default = True

    def on_abstain(self, evt: Event, var: GameState, abstains):
        self.last_voted = None

    def on_lynch_immunity(self, evt: Event, var: GameState, player: User, reason: str):
        if reason == "pactbreaker":
            channels.Main.send(messages["pactbreaker_stocks_escape"].format(player))
            evt.data["immune"] = True

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
            # Wolves don't win unless all vigilantes are dead
            if evt.data["winner"] == "wolves" and num_vigilantes > 0:
                evt.data["winner"] = None
            else:
                # Wolves won and all vigilantes are dead, or vampire met normal win cond, so this is an actual win
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
        if wrapper.source not in self.active_players:
            wrapper.pm(messages["pactbreaker_no_visit"])
            return

        self.visiting[wrapper.source] = get_home(wrapper.source.game_state, wrapper.source)
        wrapper.pm(messages["no_visit"])

    def visit(self, wrapper: MessageDispatcher, message: str):
        """Visit a location to collect evidence."""
        var = wrapper.game_state
        if wrapper.source not in self.active_players:
            wrapper.pm(messages["pactbreaker_no_visit"])
            return

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

        # Don't let a person visit the same location multiple nights in a row, with the following exceptions:
        # 1. Everyone can stay home multiple nights in a row
        # 2. Wolves can hunt in the forest multiple nights in a row
        # 3. Vampires can hunt in the square multiple nights in a row

        player_home = get_home(var, wrapper.source)
        # default to home if n1 or they were in the stocks, to let them visit any location
        prev_location = self.prev_visiting.get(wrapper.source, player_home)
        player_role = get_main_role(var, wrapper.source)
        prev_name = prev_location.name if prev_location in (Forest, VillageSquare) else "house"
        target_name = target_location.name if target_location in (Forest, VillageSquare) else "house"
        if prev_name == target_name and prev_location is not player_home:
            if target_location is Forest and player_role in Wolf:
                pass
            elif target_location is VillageSquare and player_role in Vampire:
                pass
            else:
                wrapper.pm(messages["pactbreaker_no_visit_twice_{0}".format(target_name)])
                return

        self.visiting[wrapper.source] = target_location
        if is_special:
            wrapper.pm(messages["pactbreaker_visiting_{0}".format(target_location.name)])
        else:
            wrapper.pm(messages["pactbreaker_visiting_house"].format(target_player))

        # relay to wolfchat/vampire chat as appropriate
        relay_key = "pactbreaker_relay_visit_{0}".format(target_name)
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
