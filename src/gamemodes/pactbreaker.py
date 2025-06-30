from __future__ import annotations

import functools
import logging
import math
import re
from collections import defaultdict
from typing import Iterable, Optional

from src import channels, config
from src.match import match_one
from src.trans import NIGHT_IDLE_EXEMPT
from src.users import User
from src.containers import UserSet, UserDict, DefaultUserDict
from src.decorators import command
from src.dispatcher import MessageDispatcher
from src.events import Event, EventListener
from src.functions import get_players, get_main_role, get_target, change_role, get_all_players
from src.gamemodes import game_mode, GameMode
from src.gamestate import GameState
from src.messages import messages, LocalRole
from src.locations import move_player, Location, VillageSquare, Forest, Graveyard, Streets
from src.cats import Wolf, Vampire, Category, Wolfteam, Vampire_Team, Village
from src.status import add_protection, add_day_vote_immunity, get_all_protections
from src.roles.helper.wolves import send_wolfchat_message, wolf_kill, wolf_retract, is_known_wolf_ally
from src.roles.vampire import send_vampire_chat_message, vampire_bite, vampire_retract, is_known_vampire_ally
from src.roles.vampire import on_player_protected as vampire_drained
from src.roles.vampire import GameState as VampireGameState
from src.roles.vigilante import vigilante_retract, vigilante_pass, vigilante_kill
from src.random import random

# dummy location for wolves/vigilantes/vampires that have elected to kill/bite instead of visit a location
Limbo = Location("<<hunting>>")
_logger = logging.getLogger("game.pactbreaker")

@game_mode("pactbreaker", minp=6, maxp=24)
class PactBreakerMode(GameMode):
    """Help a rogue vigilante take down the terrors of the night or re-establish your pact with the werewolves!"""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.CUSTOM_SETTINGS.limit_abstain = False
        self.CUSTOM_SETTINGS.self_vote_allowed = False
        self.CUSTOM_SETTINGS.always_pm_role = True
        self.ROLE_GUIDE = {
            6: ["wolf", "vampire", "vigilante", "cursed villager"],
            8: ["wolf(2)"],
            10: ["vampire(2)"],
            12: ["vigilante(2)", "cursed villager(2)"],
            14: ["wolf(3)"],
            16: ["vampire(3)"],
            18: ["wolf(4)"],
            20: ["vigilante(3)", "cursed villager(3)"],
            24: ["wolf(5)", "vampire(4)"],
        }
        self.SECONDARY_ROLES["cursed villager"] = {"villager", "vigilante"}
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
            "day_vote": EventListener(self.on_day_vote),
            "abstain": EventListener(self.on_abstain),
            "day_vote_immunity": EventListener(self.on_day_vote_immunity),
            "del_player": EventListener(self.on_del_player),
            "myrole": EventListener(self.on_myrole),
            "revealroles": EventListener(self.on_revealroles),
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
        self.night_kill_messages: set[tuple[User, User]] = set()
        self.visiting: UserDict[User, Location] = UserDict()
        self.killing: UserDict[User, User] = UserDict()
        self.drained = UserSet()
        self.protected = UserSet()
        self.turned = UserSet()
        self.voted: DefaultUserDict[User, int] = DefaultUserDict(int)
        self.last_voted: Optional[User] = None
        self.active_players = UserSet()
        self.in_stocks: Optional[User] = None
        self.collected_evidence: DefaultUserDict[User, DefaultUserDict[str, UserSet]] = DefaultUserDict(lambda: DefaultUserDict(UserSet))
        self.clue_pool = 0
        self.clue_tokens: DefaultUserDict[User, int] = DefaultUserDict(int)
        kwargs = dict(chan=False, pm=True, playing=True, register=False)
        self.visit_command = command("visit", phases=("night",), **kwargs)(self.visit)
        self.id_command = command("id", phases=("day",), **kwargs)(self.identify)
        self.observe_command = command("observe", phases=("day",), **kwargs)(self.observe)
        self.kill_command = command("kill", phases=("night",), roles=("wolf", "vigilante"), **kwargs)(self.kill)
        self.bite_command = command("bite", phases=("night",), roles=("vampire",), **kwargs)(self.bite)
        self.stats_command = command("stats", pm=True, in_game_only=True, register=False)(self.stats)

    def startup(self):
        super().startup()
        # register !visit, !id, and !kill, remove all role commands
        self.visit_command.register()
        self.id_command.register()
        self.observe_command.register()
        self.kill_command.register()
        self.bite_command.register()
        self.stats_command.register()
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
        self.id_command.remove()
        self.observe_command.remove()
        self.kill_command.remove()
        self.bite_command.remove()
        self.stats_command.remove()
        wolf_kill.register()
        wolf_retract.register()
        vampire_bite.register()
        vampire_retract.register()
        vampire_drained.install()
        vigilante_kill.register()
        vigilante_retract.register()
        vigilante_pass.register()
        # clear user containers
        self.visiting.clear()
        self.killing.clear()
        self.drained.clear()
        self.protected.clear()
        self.turned.clear()
        self.voted.clear()
        self.active_players.clear()
        self.collected_evidence.clear()
        self.clue_tokens.clear()

    def on_del_player(self, evt: Event, var: GameState, player, all_roles, death_triggers):
        # self.night_kills isn't updated because it is short-lived
        # and won't have del_player run in the middle of it in a way that matters
        self.active_players.discard(player)
        self.drained.discard(player)
        self.protected.discard(player)
        del self.visiting[:player:]
        del self.killing[:player:]
        del self.voted[:player:]
        self.clue_pool += self.clue_tokens[player]
        del self.clue_tokens[player]
        for attacker, victim in list(self.killing.items()):
            if victim is player:
                NIGHT_IDLE_EXEMPT.add(attacker)
                del self.killing[attacker]
        if player in self.collected_evidence.items():
            del self.collected_evidence[player]
        for _, mapping in self.collected_evidence.items():
            for _, others in mapping.items():
                others.discard(player)
        if self.last_voted is player:
            self.last_voted = None

    def on_start_game(self, evt: Event, var: GameState, mode_name: str, mode: GameMode):
        # mark every player as active at start of game
        pl = get_players(var)
        self.active_players.update(pl)
        # initialize clue pool
        self.clue_pool = math.ceil(config.Main.get("gameplay.modes.pactbreaker.clue.pool") * len(pl))

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

    def on_myrole(self, evt: Event, var: GameState, player: User):
        player.send(messages["pactbreaker_info_clues"].format(self.clue_tokens[player]))
        evidence: dict[User, str] = {}
        # roles earlier in the order can be fake evidence for later roles
        # iterate such that real evidence is always displayed if available by putting those roles last
        role_order = ("wolf", "villager", "vigilante", "vampire")
        for role in role_order:
            for target in self.collected_evidence[player][role]:
                evidence[target] = role

        if not evidence:
            evt.data["messages"].append(messages["pactbreaker_info_no_evidence"])
        else:
            entries = []
            for target, role in evidence.items():
                entries.append(messages["pactbreaker_info_evidence_entry"].format(target, role))
            evt.data["messages"].append(messages["pactbreaker_info_evidence"].format(sorted(entries)))

    def on_revealroles(self, evt: Event, var: GameState):
        tlist = []
        for player, tokens in self.clue_tokens.items():
            if tokens > 0:
                tlist.append("{0} ({1})".format(player.name, tokens))
        if tlist:
            evt.data["output"].append(messages["pactbreaker_revealroles"].format(sorted(tlist)))

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

    def build_deck(self, var: GameState, location: Location, visitors: set[User]) -> tuple[list[str], int]:
        num_visitors = len(visitors)
        num_wolves = sum(1 for v in visitors if get_main_role(var, v) == "wolf")
        num_other = num_visitors - num_wolves

        if location is Forest:
            deck = (["empty-handed"] * 2
                    + ["evidence"] * 4
                    + (["hunted", "hunted", "empty-handed"] * num_wolves)
                    + (["evidence", "evidence", "empty-handed"] * num_other))
            num_draws = 2
        elif location is VillageSquare:
            deck = (["empty_handed"] * (2 * max(0, num_visitors - 4))
                    + ["evidence"] * 8
                    + ["clue", "clue"] * num_visitors)
            num_draws = 4
        elif location is Graveyard:
            deck = (["clue"] * 3
                    + ["empty-handed"] * 2
                    + ["hunted", "empty-handed"] * num_wolves
                    + ["empty-handed", "empty-handed"] * num_other)
            num_draws = 1
        elif location is Streets:
            deck = (["evidence"] * 7
                    + ["hunted", "evidence", "empty-handed"] * num_wolves
                    + ["evidence", "evidence", "empty-handed"] * num_other)
            num_draws = 3
        else:
            raise RuntimeError(f"No deck defined for location {location.name}")

        random.shuffle(deck)
        return deck, num_draws

    def on_night_kills(self, evt: Event, var: GameState):
        self.night_kill_messages.clear()
        all_wolves = set(get_players(var, ("wolf",)))
        all_vamps = set(get_players(var, ("vampire",)))
        all_cursed = get_all_players(var, ("cursed villager",))
        wl = list(all_wolves | all_cursed)
        extra = (("vampire", Graveyard), ("wolf", Forest))

        for player in self.active_players & all_wolves - self.protected:
            # wolves need to be drained 3 times to die
            add_protection(var, player, None, "wolf", Vampire)

        for player in self.active_players - self.drained:
            # mark un-drained players as eligible for draining
            add_protection(var, player, None, "vampire", Vampire, 5)

        for player in set(get_players(var, ("vigilante",))):
            # mark vigilantes as eligible for turning into vampires
            if random.random() < config.Main.get("gameplay.modes.pactbreaker.turn"):
                add_protection(var, player, None, "vigilante", Vampire, 10)

        # resolve kill command usages
        for killer, victim in self.killing.items():
            killer_role = get_main_role(var, killer)
            victim_role = get_main_role(var, victim)
            have_evidence = victim in self.collected_evidence[killer][victim_role]

            if victim is not self.in_stocks and not have_evidence and victim_role == "vampire":
                killer.send(messages["pactbreaker_kill_fail"].format(victim))
            else:
                evt.data["victims"].add(victim)
                evt.data["killers"][victim].append(killer)
                self.night_kill_messages.add((killer, victim))
                if killer_role == "vampire":
                    evt.data["kill_priorities"][killer] = 10
                elif killer_role == "wolf":
                    evt.data["kill_priorities"][killer] = 5
                elif killer_role == "vigilante" and victim_role not in ("wolf", "vampire"):
                    evt.data["kill_priorities"]["@vigilante"] = 15
                    evt.data["victims"].add(killer)
                    evt.data["killers"][killer].append("@vigilante")

        # resolve night visits on a per-location basis
        visited: dict[Location, set[User]] = defaultdict(set)
        for player, location in self.visiting.items():
            # if they died from !kill or !bite, don't have them draw cards or count them as visiting a location
            if player not in evt.data["victims"] or (len(evt.data["killers"][player]) == 1
                                                     and evt.data["killers"][player][0] in all_vamps
                                                     and get_all_protections(var, player, Vampire)):
                visited[location].add(player)

        shares: set[User] = set()
        for location, visitors in visited.items():
            if location is Limbo or not visitors:
                continue

            deck, num_draws = self.build_deck(var, location, visitors)
            loc = location.name
            i = 0
            # for hunted card messaging and forest evidence
            wolves = list(visitors & all_wolves)
            random.shuffle(wolves)
            # ensure that clue tokens are randomly distributed in case there are not enough by randomizing visitor list
            vl = list(visitors)
            random.shuffle(vl)
            for visitor in vl:
                visitor_role = get_main_role(var, visitor)
                # vamps draw 2 cards at graveyard instead of 1
                # wolves draw 3 cards at forest instead of 2
                extra_draws = 1 if (visitor_role, location) in extra else 0
                cards = deck[i:i + num_draws + extra_draws]
                i += num_draws + extra_draws
                empty = True
                _logger.debug("[{0}] {1}: {2}", loc, visitor.name, ", ".join(cards))

                if "hunted" in cards:
                    num_hunted = sum(1 for c in cards if c == "hunted")
                    kill_threshold = 2 if visitor_role == "vigilante" else 1
                    if visitor_role == "wolf" or num_hunted < kill_threshold:
                        cards.extend(["evidence"] * num_hunted)
                    elif wolves and visitor_role != "vampire":
                        wolf = wolves.pop()
                        evt.data["victims"].add(visitor)
                        evt.data["killers"][visitor].append(wolf)
                        evt.data["kill_priorities"][wolf] = 5
                        self.night_kill_messages.add((wolf, visitor))
                        # they're dying so don't process any other cards they may have drawn
                        continue

                if "clue" in cards and self.clue_pool > 0:
                    empty = False
                    if location is Graveyard:
                        tokens = min(self.clue_pool, config.Main.get("gameplay.modes.pactbreaker.clue.graveyard"))
                        self.clue_pool -= tokens
                        self.clue_tokens[visitor] += tokens
                        visitor.send(messages[f"pactbreaker_{loc}_clue"].format(tokens))
                    elif location is VillageSquare:
                        # has to be handled after everyone finishes drawing
                        shares.add(visitor)

                # handle evidence card
                num_evidence = sum(1 for c in cards if c == "evidence")
                evidence_target = None
                if location is Forest and visitor not in all_wolves:
                    random.shuffle(wl)
                    for wolf in wl:
                        if wolf is not visitor and wolf not in self.collected_evidence[visitor]["wolf"]:
                            evidence_target = wolf
                            break
                    else:
                        # give non-wolves a higher chance of gaining clues after exhausting all wolf evidence
                        num_evidence += 1
                elif location is Streets and num_evidence == 3:
                    # refute fake evidence that the visitor may have collected
                    # if there's no fake evidence, fall back to giving a clue token
                    collected = functools.reduce(lambda x, y: x | y, self.collected_evidence[visitor].values(), set())
                    role_order = ("wolf", "villager", "vigilante")
                    for role in role_order:
                        for target in self.collected_evidence[visitor][role]:
                            real_role = get_main_role(var, target)
                            if real_role != role and target not in self.collected_evidence[visitor][real_role]:
                                evidence_target = target
                                break
                        if evidence_target is not None:
                            break

                    # no evidence to refute? give a special message indicating that
                    if collected and evidence_target is None:
                        tokens = min(self.clue_pool, config.Main.get(f"gameplay.modes.pactbreaker.clue.{loc}"))
                        self.clue_pool -= tokens
                        self.clue_tokens[visitor] += tokens
                        visitor.send(messages[f"pactbreaker_{loc}_special"].format(tokens))
                        # process the next player since we've fully handled this one here
                        continue
                elif location is Streets:
                    # streets is guaranteed to give a clue token each night (as long as clue tokens remain)
                    num_evidence = 2

                if num_evidence >= 2:
                    if evidence_target is not None:
                        empty = False
                        # give fake evidence?
                        if num_evidence == 2 and evidence_target in all_cursed:
                            target_role = "wolf"
                        elif num_evidence == 2 and get_main_role(var, evidence_target) == "vampire":
                            target_role = "vigilante" if evidence_target in self.turned else "villager"
                        else:
                            target_role = get_main_role(var, evidence_target)
                        # also hide vigi evidence (or vigi fake evidence) from vills
                        if num_evidence == 2 and target_role == "vigilante" and visitor_role == "villager":
                            target_role = "villager"
                        self.collected_evidence[visitor][target_role].add(evidence_target)
                        visitor.send(messages[f"pactbreaker_{loc}_evidence"].format(evidence_target, target_role))
                    elif self.clue_pool > 0 and location is not VillageSquare:
                        empty = False
                        tokens = min(self.clue_pool, config.Main.get(f"gameplay.modes.pactbreaker.clue.{loc}"))
                        self.clue_pool -= tokens
                        self.clue_tokens[visitor] += tokens
                        visitor.send(messages[f"pactbreaker_{loc}_clue"].format(tokens))

                if empty:
                    visitor.send(messages[f"pactbreaker_{loc}_empty"])

        # handle share cards
        if len(shares) <= 1:
            for visitor in shares:
                loc = self.visiting[visitor].name
                visitor.send(messages[f"pactbreaker_{loc}_empty"])
        elif len(shares) > 1:
            num_tokens = min(math.floor(self.clue_pool / len(shares)),
                             config.Main.get("gameplay.modes.pactbreaker.clue.square"))
            for visitor in shares:
                loc = self.visiting[visitor].name
                if num_tokens > 0:
                    self.clue_pool -= num_tokens
                    self.clue_tokens[visitor] += num_tokens
                    visitor.send(messages[f"pactbreaker_{loc}_clue"].format(num_tokens))
                else:
                    visitor.send(messages[f"pactbreaker_{loc}_empty"])

    def on_player_protected(self,
                            evt: Event,
                            var: GameState,
                            target: User,
                            attacker: Optional[User],
                            attacker_role: str,
                            protector: Optional[User],
                            protector_role: str,
                            reason: str):
        if protector_role in ("vampire", "wolf"):
            # mark them for internal gameplay purposes (wolves go into protected before drained)
            self.protected.add(target) if protector_role == "wolf" else self.drained.add(target)
            # mark them for vampires' private player listings (during !stats or nighttime notification messages)
            vvar = var # type: VampireGameState
            vvar.vampire_drained.add(target)
            attacker.send(messages["pactbreaker_drain"].format(target))
            target.send(messages["pactbreaker_drained"])
            # give the victim tokens before vamp so that pool exhaustion doesn't overly benefit vamp
            victim_tokens = min(config.Main.get("gameplay.modes.pactbreaker.clue.bitten"), self.clue_pool)
            self.clue_pool -= victim_tokens
            self.clue_tokens[target] += victim_tokens
            vamp_tokens = min(config.Main.get("gameplay.modes.pactbreaker.clue.bite"), self.clue_pool)
            self.clue_pool -= vamp_tokens
            self.clue_tokens[attacker] += vamp_tokens
        elif protector_role == "vigilante":
            # if the vampire fully drains a vigilante, they might turn into a vampire instead of dying
            # this protection triggering means they should turn
            attacker.send(messages["pactbreaker_drain_turn"].format(target))
            change_role(var, target, get_main_role(var, target), "vampire", message="pactbreaker_drained_vigilante")
            self.turned.add(target)
            self.drained.discard(target)

        # don't tell the attacker that their kill failed in case someone else also attacks the target the same night
        self.night_kill_messages.discard((attacker, target))

    def on_night_death_message(self, evt: Event, var: GameState, victim: User, killer: User | str):
        if not isinstance(killer, User):
            # vigilante self-kill
            return

        killer_role = get_main_role(var, killer, mainroles=evt.params.mainroles)

        if killer_role == "vampire":
            victim.send(messages["pactbreaker_drained_dead"])
            killer.send(messages["pactbreaker_drain_kill"].format(victim))
        elif killer_role == "wolf" and victim is self.in_stocks:
            victim.send(messages["pactbreaker_hunted_stocks"])
            killer.send(messages["pactbreaker_hunter_stocks"].format(victim))
        elif killer_role == "wolf":
            victim.send(messages["pactbreaker_hunted"])
            killer.send(messages["pactbreaker_hunter"].format(victim))
        elif killer_role == "vigilante" and victim is self.in_stocks:
            victim.send(messages["pactbreaker_shot_stocks"])
            killer.send(messages["pactbreaker_shooter_stocks"].format(victim))
        elif killer_role == "vigilante":
            victim.send(messages["pactbreaker_shot"])
            killer.send(messages["pactbreaker_shooter"].format(victim))
        else:
            # shouldn't happen; indicates a bug in the mode
            raise RuntimeError(f"Unknown night death situation ({killer_role})")

    def on_transition_day_resolve(self, evt: Event, var: GameState, dead: set[User], killers: dict[User, User | str]):
        # check for players meant to kill someone but got their kill pre-empted by someone else
        for killer, victim in self.killing.items():
            if victim in dead and killers[victim] is not killer and (killer, victim) in self.night_kill_messages:
                killer.send(messages["pactbreaker_kill_fail"].format(victim))

        self.night_kill_messages.clear()

    def on_begin_day(self, evt: Event, var: GameState):
        # every player is active again (stocks only lasts for one night)
        self.in_stocks = None
        self.active_players.clear()
        self.active_players.update(get_players(var))
        self.visiting.clear()
        self.killing.clear()
        # if someone was locked up last night, ensure they can't be locked up again tonight
        if self.last_voted is not None:
            add_day_vote_immunity(var, self.last_voted, "pactbreaker")
        # alert people about clue tokens they have
        observe_tokens = config.Main.get("gameplay.modes.pactbreaker.clue.observe")
        id_tokens = config.Main.get("gameplay.modes.pactbreaker.clue.identify")
        for player, amount in self.clue_tokens.items():
            if amount == 0:
                continue
            player.send(messages["pactbreaker_clue_notify"].format(amount, observe_tokens, id_tokens))

    def on_day_vote(self, evt: Event, var: GameState, votee: User, voters: Iterable[User]):
        self.last_voted = votee
        self.voted[votee] += 1
        if self.voted[votee] < 3:
            channels.Main.send(messages["pactbreaker_vote"].format(votee))
            self.active_players.discard(votee)
            self.in_stocks = votee
            # don't kill the votee
            evt.prevent_default = True

    def on_abstain(self, evt: Event, var: GameState, abstains):
        self.last_voted = None

    def on_day_vote_immunity(self, evt: Event, var: GameState, player: User, reason: str):
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
        num_villagers = len(get_players(var, ("villager",), mainroles=mainroles))

        if evt.data["winner"] is Village:
            evt.data["message"] = messages["pactbreaker_vigilante_win"]
        elif evt.data["winner"] in (Wolfteam, Vampire_Team):
            # Wolves don't win unless all vigilantes are dead
            if evt.data["winner"] is Wolfteam and num_vigilantes > 0:
                evt.data["winner"] = None
            else:
                # Wolves won and all vigilantes are dead, or vampire met normal win cond, so this is an actual win
                # Message keys used: pactbreaker_wolf_win pactbreaker_vampire_win
                key = "wolf" if evt.data["winner"] is Wolfteam else "vampire"
                evt.data["message"] = messages["pactbreaker_{0}_win".format(key)]
        elif num_vigilantes == 0 and lvampires == 0:
            # wolves (and villagers) win even if there is a minority of wolves as long as
            # the vigilantes and vampires are all dead
            evt.data["winner"] = Wolfteam
            evt.data["message"] = messages["pactbreaker_wolf_win"]
        elif lvampires and (num_villagers == 0 or (num_vigilantes == 0 and lwolves == 0)):
            # vampires can win even with wolves and vigilante alive if they kill the rest of the village
            # or if all wolves and vigilantes are dead even if the remainder of the village outnumbers them
            evt.data["winner"] = Vampire_Team
            evt.data["message"] = messages["pactbreaker_vampire_win"]

    def on_team_win(self, evt: Event, var: GameState, player: User, main_role: str, all_roles: Iterable[str], winner: Category):
        if winner is Wolfteam and main_role == "villager":
            evt.data["team_win"] = True

    def visit(self, wrapper: MessageDispatcher, message: str):
        """Visit a location to collect evidence."""
        var = wrapper.game_state
        if wrapper.source is self.in_stocks:
            wrapper.pm(messages["pactbreaker_no_visit"])
            return

        prefix = re.split(" +", message)[0]
        aliases = {
            "forest": messages.raw("_commands", "forest"),
            "square": messages.raw("_commands", "square"),
            "streets": messages.raw("_commands", "streets"),
            "graveyard": messages.raw("_commands", "graveyard"),
        }

        flipped = {alias: loc for loc, x in aliases.items() for alias in x}
        match = match_one(prefix, flipped.keys())
        if match is None:
            return

        target_location = Location(match)

        player_role = get_main_role(var, wrapper.source)
        target_name = target_location.name
        del self.killing[:wrapper.source:]
        self.visiting[wrapper.source] = target_location
        wrapper.pm(messages["pactbreaker_visiting_{0}".format(target_location.name)])

        # relay to wolfchat/vampire chat as appropriate
        relay_key = "pactbreaker_relay_visit_{0}".format(target_name)
        if player_role in Wolf:
            # command is "kill" so that this is relayed even if gameplay.wolfchat.only_kill_command is true
            send_wolfchat_message(var,
                                  wrapper.source,
                                  messages[relay_key].format(wrapper.source),
                                  Wolf,
                                  role="wolf",
                                  command="kill")
        elif player_role in Vampire:
            # same logic as wolfchat for why we use "bite" as the command here
            send_vampire_chat_message(var,
                                      wrapper.source,
                                      messages[relay_key].format(wrapper.source),
                                      Vampire,
                                      cmd="bite")

    def kill(self, wrapper: MessageDispatcher, message: str):
        """Kill a player in the stocks or that you have collected evidence on."""
        var = wrapper.game_state
        if wrapper.source is self.in_stocks:
            wrapper.pm(messages["pactbreaker_no_kill_stocks"])
            return

        target = get_target(wrapper, re.split(" +", message)[0], not_self_message="no_suicide")
        if not target:
            return

        player_role = get_main_role(var, wrapper.source)
        if is_known_wolf_ally(var, wrapper.source, target):
            wrapper.pm(messages["wolf_no_target_wolf"])
            return

        have_evidence = False
        if player_role == "wolf":
            for role in ("vigilante", "vampire"):
                if target in self.collected_evidence[wrapper.source][role]:
                    have_evidence = True
                    break

            if target is not self.in_stocks and not have_evidence:
                wrapper.send(messages["pactbreaker_no_kill_evidence"].format(target))
                return

        self.killing[wrapper.source] = target
        self.visiting[wrapper.source] = Limbo
        wrapper.pm(messages["player_kill"].format(target))
        msg = messages["wolfchat_kill"].format(wrapper.source, target)

        if player_role in Wolf:
            send_wolfchat_message(var, wrapper.source, msg, Wolf, role="wolf", command="kill")

    def bite(self, wrapper: MessageDispatcher, message: str):
        """Bite a player to drain their blood; those in the stocks will be killed entirely."""
        var = wrapper.game_state
        if wrapper.source is self.in_stocks:
            wrapper.pm(messages["pactbreaker_no_kill_stocks"])
            return

        target = get_target(wrapper, re.split(" +", message)[0], not_self_message="no_suicide")
        if not target:
            return

        if is_known_vampire_ally(var, wrapper.source, target):
            wrapper.send(messages["no_target_vampire"])
            return

        for killer, victim in self.killing.items():
            if wrapper.source is killer:
                # let the vampire target the same person multiple times in succession
                # doesn't really do anything but giving an error is even weirder
                continue
            if target is victim and is_known_vampire_ally(var, wrapper.source, killer):
                wrapper.send(messages["already_bitten_tonight"].format(target))
                return

        self.killing[wrapper.source] = target
        self.visiting[wrapper.source] = Limbo
        wrapper.pm(messages["vampire_bite"].format(target))
        send_vampire_chat_message(var,
                                  wrapper.source,
                                  messages["vampire_bite_vampchat"].format(wrapper.source, target),
                                  Vampire,
                                  cmd="bite")

    def observe(self, wrapper: MessageDispatcher, message: str):
        """Spend clue tokens to learn about a player's role, however some roles may give inaccurate results."""
        var = wrapper.game_state
        target = get_target(wrapper, re.split(" +", message)[0], not_self_message="no_observe_self")
        if not target:
            return

        num_tokens = self.clue_tokens[wrapper.source]
        min_tokens = config.Main.get("gameplay.modes.pactbreaker.clue.observe")
        if num_tokens < min_tokens:
            wrapper.send(messages["pactbreaker_no_observe"].format(min_tokens, num_tokens))
            return

        self.clue_pool += min_tokens
        self.clue_tokens[wrapper.source] -= min_tokens
        player_role = get_main_role(var, wrapper.source)
        target_role = get_main_role(var, target)
        if target in get_all_players(var, ("cursed villager",)):
            target_role = "wolf"
        elif target_role == "vampire":
            target_role = "vigilante" if target in self.turned else "villager"

        # also hide vigi evidence (or vigi fake evidence) from vills
        if target_role == "vigilante" and player_role == "villager":
            target_role = "villager"

        self.collected_evidence[wrapper.source][target_role].add(target)
        wrapper.send(messages["pactbreaker_observe_success"].format(target, target_role))

    def identify(self, wrapper: MessageDispatcher, message: str):
        """Spend clue tokens to accurately learn about a player's role."""
        var = wrapper.game_state
        target = get_target(wrapper, re.split(" +", message)[0], not_self_message="no_investigate_self")
        if not target:
            return

        num_tokens = self.clue_tokens[wrapper.source]
        min_tokens = config.Main.get("gameplay.modes.pactbreaker.clue.identify")
        if num_tokens < min_tokens:
            wrapper.send(messages["pactbreaker_no_id"].format(min_tokens, num_tokens))
            return

        self.clue_pool += min_tokens
        self.clue_tokens[wrapper.source] -= min_tokens
        target_role = get_main_role(var, target)
        self.collected_evidence[wrapper.source][target_role].add(target)
        wrapper.send(messages["investigate_success"].format(target, target_role))

    def stats(self, wrapper: MessageDispatcher, message: str):
        wrapper.reply(messages["pactbreaker_stats"].format(self.clue_pool))
