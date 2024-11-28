from __future__ import annotations

import random
import re
from collections import defaultdict
from collections.abc import Callable
from typing import Iterable, Optional

from src import users, channels
from src.trans import NIGHT_IDLE_EXEMPT
from src.users import User, FakeUser
from src.containers import UserSet, UserDict, DefaultUserDict
from src.decorators import command
from src.dispatcher import MessageDispatcher
from src.events import Event, EventListener
from src.functions import get_players, get_main_role, get_target, change_role
from src.gamemodes import game_mode, GameMode
from src.gamestate import GameState
from src.messages import messages, LocalRole
from src.locations import move_player, get_home, Location, VillageSquare, Forest, Graveyard
from src.cats import Wolf, Vampire
from src.status import add_protection, add_lynch_immunity
from src.roles.helper.wolves import send_wolfchat_message, wolf_kill, wolf_retract, is_known_wolf_ally
from src.roles.vampire import send_vampire_chat_message, vampire_bite, vampire_retract, is_known_vampire_ally
from src.roles.vampire import on_player_protected as vampire_drained
from src.roles.vigilante import vigilante_retract, vigilante_pass, vigilante_kill

# dummy location for wolves/vampires that have elected to kill instead of visit a location
Limbo = Location("<<hunting>>")

@game_mode("pactbreaker", minp=6, maxp=24)
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
            "myrole": EventListener(self.on_myrole),
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
        self.killing: UserDict[User, User] = UserDict()
        self.prev_visiting: UserDict[User, Location] = UserDict()
        self.drained = UserSet()
        self.turned = UserSet()
        self.voted: DefaultUserDict[User, int] = DefaultUserDict(int)
        self.last_voted: Optional[User] = None
        self.active_players = UserSet()
        self.in_stocks: Optional[User] = None
        self.collected_evidence: DefaultUserDict[User, UserSet] = DefaultUserDict(UserSet)
        self.stale_evidence: DefaultUserDict[User, UserSet] = DefaultUserDict(UserSet)
        self.clue_pool = 0
        self.clue_tokens: DefaultUserDict[User, int] = DefaultUserDict(int)
        dfd = lambda: DefaultUserDict(int)
        # keep track of how many times a player has visited another player's house
        # each subsequent visit increases the likelihood of the player discovering evidence
        self.visit_count: DefaultUserDict[User, DefaultUserDict[User, int]] = DefaultUserDict(dfd)
        kwargs = dict(chan=False, pm=True, playing=True, phases=("night",), register=False)
        self.pass_command = command("pass", **kwargs)(self.stay_home)
        self.visit_command = command("visit", **kwargs)(self.visit)

        # id is a day command
        kwargs["phases"] = ("day",)
        self.id_command = command("id", **kwargs)(self.identify)

        # kill is only usable by wolves, vigilantes, and vampires
        kwargs["phases"] = ("night",)
        kwargs["roles"] = ("wolf", "vigilante", "vampire")
        self.kill_command = command("kill", **kwargs)(self.kill)

    def startup(self):
        super().startup()
        self.night_kill_messages.clear()
        self.active_players.clear()
        self.in_stocks = None
        self.voted.clear()
        self.drained.clear()
        self.turned.clear()
        self.collected_evidence.clear()
        self.stale_evidence.clear()
        self.visiting.clear()
        self.killing.clear()
        self.prev_visiting.clear()
        self.clue_tokens.clear()
        # register !visit and !pass, remove all role commands
        self.visit_command.register()
        self.pass_command.register()
        self.id_command.register()
        self.kill_command.register()
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
        self.id_command.remove()
        self.kill_command.remove()
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
        del self.killing[:player:]
        del self.voted[:player:]
        del self.visit_count[:player:]
        self.clue_pool += self.clue_tokens[player]
        del self.clue_tokens[player]
        for attacker, victim in list(self.killing.items()):
            if victim is player:
                NIGHT_IDLE_EXEMPT.add(attacker)
                del self.killing[attacker]
        if player in self.collected_evidence.items():
            del self.collected_evidence[player]
        for _, others in self.collected_evidence.items():
            others.discard(player)
        if player in self.stale_evidence.items():
            del self.stale_evidence[player]
        for _, others in self.stale_evidence.items():
            others.discard(player)
        for _, others in self.visit_count.items():
            del others[:player:]
        if self.last_voted is player:
            self.last_voted = None

    def on_start_game(self, evt: Event, var: GameState, mode_name: str, mode: GameMode):
        # mark every player as active at start of game
        pl = get_players(var)
        self.active_players.update(pl)
        # initialize clue pool
        self.clue_pool = 2 * len(pl)

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
        if not self.collected_evidence[player] and not self.stale_evidence[player]:
            player.send(messages["pactbreaker_info_no_evidence"])
        else:
            entries = []
            for target in self.collected_evidence[player]:
                entries.append(messages["pactbreaker_info_evidence_entry"].format(target, get_main_role(var, target)))
            for target in self.stale_evidence[player]:
                if target not in self.collected_evidence[player]:
                    entries.append(messages["pactbreaker_info_evidence_entry"].format(target, "vigilante"))
            player.send(messages["pactbreaker_info_evidence"].format(sorted(entries)))

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

    def build_deck(self, var: GameState, location: Location, visitors: set[User]) -> tuple[list[str], Callable[[User], int], Optional[str]]:
        num_visitors = len(visitors)
        num_wolves = sum(1 for v in visitors if get_main_role(var, v) == "wolf")
        num_other = num_visitors - num_wolves
        owner = None

        if location is Forest:
            deck = (["empty-handed", "empty-handed", "evidence"]
                    + (["hunted", "empty-handed"] * num_wolves)
                    + (["evidence", "evidence"] * num_other))
            draw_func = lambda _: 2
        elif location is VillageSquare:
            deck = (["empty_handed"] * (5 + 2 * max(0, num_visitors - 4))
                    + ["evidence"] * 3
                    + ["share", "evidence"] * num_visitors)
            draw_func = lambda _: 4
        elif location is Graveyard:
            deck = ["clue", "clue", "clue"] + ["hunted"] * num_wolves + ["empty-handed"] * num_other
            draw_func = lambda _: 1
        else:
            # location is a house
            for player in get_players(var):
                if get_home(var, player) is location:
                    owner = player
                    break

            assert owner is not None
            is_home = owner in visitors
            num_visitors -= 1
            total_draws = 0
            for visitor in visitors:
                if visitor is owner:
                    continue
                self.visit_count[visitor][owner] += 1
                total_draws += (self.visit_count[visitor][owner] - 1) * 2 + 1

            deck = (["empty-handed", "evidence", "evidence"]
                    + (["empty_handed", "empty_handed"] if is_home else [])
                    + ["evidence"] * num_visitors)
            deck += ["empty-handed"] * max(0, total_draws - len(deck))
            draw_func = lambda v: self.visit_count[v][owner]

        random.shuffle(deck)
        return deck, draw_func, owner

    def location_key(self, location: Location):
        assert location is not Limbo
        return location.name if location in (Forest, VillageSquare, Graveyard) else "house"

    def on_night_kills(self, evt: Event, var: GameState):
        self.night_kill_messages.clear()

        for player in self.active_players - self.drained:
            # mark un-drained players as eligible for draining
            add_protection(var, player, None, "vampire", Vampire)

        for player in set(get_players(var, ("vigilante",))):
            # mark vigilantes as eligible for turning into vampires
            add_protection(var, player, None, "vigilante", Vampire, 10)

        # resolve kill command usages
        witness = None
        for killer, victim in self.killing.items():
            killer_role = get_main_role(var, killer)
            victim_role = get_main_role(var, victim)
            have_evidence = victim in self.collected_evidence[killer]
            victim_visiting = self.visiting.get(victim)
            is_home = victim_visiting is get_home(var, victim)
            if victim_role == "wolf":
                is_safe = is_home or victim_visiting is Forest
            elif victim_role == "vigilante":
                is_safe = is_home or victim_visiting is VillageSquare
            elif victim_role == "vampire":
                is_safe = is_home or victim_visiting is Graveyard
            else:
                # unused default fallback, but villagers are only safe if at home
                is_safe = is_home

            # all roles with !kill access can target someone in the stocks and are (mostly) treated the same way
            if victim is self.in_stocks:
                evt.data["victims"].add(victim)
                evt.data["killers"][victim].append(killer)
                self.night_kill_messages[(killer, victim)] = VillageSquare
                if killer_role == "vampire":
                    evt.data["kill_priorities"][killer] = 10
                    if victim_role != "vigilante":
                        witness = "vampire" if witness is None else witness
                elif killer_role == "wolf":
                    evt.data["kill_priorities"][killer] = 5
                    witness = "wolf" if witness != "vigilante" else witness
                else:
                    witness = "vigilante"
            elif not have_evidence or is_safe:
                killer.send(messages["pactbreaker_kill_fail"].format(victim))
            elif ((killer_role != "vampire" and victim_role == "vampire")
                  or (killer_role == "wolf" and victim_role == "vigilante")
                  or (killer_role == "vigilante" and victim_role == "wolf")):
                evt.data["victims"].add(victim)
                evt.data["killers"][victim].append(killer)
                self.night_kill_messages[(killer, victim)] = Limbo
            else:
                killer.send(messages["pactbreaker_kill_fail"].format(victim))

        # resolve night visits on a per-location basis
        visited: dict[Location, set[User]] = defaultdict(set)
        for player, location in self.visiting.items():
            # if they died from !kill, don't have them draw cards or count them as visiting a location
            if player not in evt.data["victims"]:
                visited[location].add(player)

        shares: list[User] = list()
        for location, visitors in visited.items():
            if location is Limbo or not visitors:
                continue

            deck, draw_func, owner = self.build_deck(var, location, visitors)
            loc = self.location_key(location)
            i = 0
            # for hunted card messaging and forest evidence
            all_wolves = set(get_players(var, ("wolf",)))
            wolves = list(visitors & all_wolves)
            random.shuffle(wolves)
            # for bites
            all_vamps = set(get_players(var, ("vampire",)))
            vamps = list(visitors & all_vamps)
            random.shuffle(vamps)
            # ensure that clue tokens are randomly distributed in case there are not enough by randomizing visitor list
            vl = list(visitors)
            random.shuffle(vl)
            for visitor in vl:
                if visitor is owner:
                    # people staying home don't draw cards, nor get told they are empty-handed because that'd be weird
                    continue

                num_draws = draw_func(visitor)
                visitor_role = get_main_role(var, visitor)
                cards = deck[i:i + num_draws]
                i += num_draws
                empty = True

                if "hunted" in cards:
                    if visitor_role == "wolf":
                        cards.append("evidence")
                    elif visitor_role != "vampire":
                        wolf = wolves.pop()
                        evt.data["victims"].add(visitor)
                        evt.data["killers"][visitor].append(wolf)
                        evt.data["kill_priorities"][wolf] = 5
                        self.night_kill_messages[(wolf, visitor)] = location
                        # they're dying so don't process any other cards they may have drawn
                        continue
                if vamps and visitor_role != "vampire":
                    vampire = vamps.pop()
                    evt.data["victims"].add(visitor)
                    evt.data["killers"][visitor].append(vampire)
                    evt.data["kill_priorities"][vampire] = 10
                    self.night_kill_messages[(vampire, visitor)] = location
                    # if they die from this, don't process any other cards they may have drawn
                    if visitor in self.drained:
                        continue

                if location is VillageSquare and witness and self.clue_pool > 0:
                    self.clue_pool -= 1
                    self.clue_tokens[visitor] += 1
                    visitor.send(messages[f"pactbreaker_square_witness_{witness}"].format(self.in_stocks))
                if "share" in cards:
                    # has to be handled after everyone finishes drawing
                    shares.append(visitor)
                    empty = False
                if "clue" in cards and self.clue_pool > 0:
                    self.clue_pool -= 1
                    self.clue_tokens[visitor] += 1
                    visitor.send(messages[f"pactbreaker_{loc}_clue"])
                    empty = False

                # handle evidence card
                num_evidence = sum(1 for c in cards if c == "evidence")
                evidence_target = owner
                if location is Forest:
                    if visitor not in all_wolves:
                        wl = list(all_wolves)
                        random.shuffle(wl)
                        for wolf in wl:
                            if wolf not in self.collected_evidence[visitor]:
                                evidence_target = wolf
                                break
                    # is a wolf or has evidence on every wolf
                    if evidence_target is None:
                        for other in vl:
                            if other not in all_wolves and other not in self.collected_evidence[visitor]:
                                evidence_target = other
                                break

                if num_evidence >= 2 and evidence_target is not None:
                    empty = False
                    # give fake evidence?
                    if num_evidence == 2 and get_main_role(var, evidence_target) == "vampire":
                        fake_role = "vigilante" if evidence_target in self.turned else "villager"
                        if fake_role == "vigilante":
                            # let wolves attempt to !kill with this fake evidence
                            self.stale_evidence[visitor].add(evidence_target)
                        visitor.send(messages[f"pactbreaker_{loc}_evidence"].format(evidence_target, fake_role))
                    else:
                        real_role = get_main_role(var, evidence_target)
                        self.collected_evidence[visitor].add(evidence_target)
                        visitor.send(messages[f"pactbreaker_{loc}_evidence"].format(evidence_target, real_role))

                if empty:
                    visitor.send(messages[f"pactbreaker_{loc}_empty"].format(owner))

        # handle share cards
        if len(shares) == 1:
            for visitor in shares:
                loc = self.location_key(self.visiting[visitor])
                # safe to omit param here as loc will never be a house
                visitor.send(messages[f"pactbreaker_{loc}_empty"])
        else:
            random.shuffle(shares)
            for visitor in shares:
                loc = self.location_key(self.visiting[visitor])
                if self.clue_pool > 0:
                    self.clue_pool -= 1
                    self.clue_tokens[visitor] += 1
                    visitor.send(messages[f"pactbreaker_{loc}_share"])
                else:
                    # safe to omit param here as loc will never be a house
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
        if protector_role == "vampire":
            self.drained.add(target)
            attacker.send(messages["pactbreaker_drain"].format(target))
            target.send(messages["pactbreaker_drained"])
            # don't tell a vampire that their kill "failed" since they never killed in the first place
            del self.night_kill_messages[(attacker, target)]
        elif protector_role == "vigilante":
            # if the vampire fully drains a vigilante, they might turn into a vampire instead of dying
            # this protection triggering means they should turn
            attacker.send(messages["pactbreaker_drain_turn"].format(target))
            change_role(var, target, get_main_role(var, target), "vampire", message="pactbreaker_drained_vigilante")
            self.turned.add(target)
            self.drained.discard(target)
            for player, targets in self.collected_evidence.items():
                if target in targets:
                    targets.discard(target)
                    self.stale_evidence[player].add(target)

    def on_night_death_message(self, evt: Event, var: GameState, victim: User, killer: User | str):
        assert isinstance(killer, User)
        victim_role = get_main_role(var, victim)
        killer_role = get_main_role(var, killer)
        location = self.night_kill_messages.pop((killer, victim))

        if killer_role == "vampire":
            victim.send(messages["pactbreaker_drained_dead"])
            killer.send(messages["pactbreaker_drain_kill"].format(victim))
        elif killer_role == "wolf" and victim not in self.active_players and location is VillageSquare:
            victim.send(messages["pactbreaker_hunted_stocks"])
            killer.send(messages["pactbreaker_hunter_stocks"].format(victim))
        elif killer_role == "wolf":
            victim.send(messages["pactbreaker_hunted"])
            killer.send(messages["pactbreaker_hunter"].format(victim))
        elif killer_role == "vigilante" and victim not in self.active_players and location is VillageSquare:
            victim.send(messages["pactbreaker_shot_stocks"])
            killer.send(messages["pactbreaker_shooter_stocks"].format(victim))
        elif killer_role == "vigilante":
            victim.send(messages["pactbreaker_shot"])
            killer.send(messages["pactbreaker_shooter"].format(victim))
        else:
            # shouldn't happen; indicates a bug in the mode
            raise RuntimeError(f"Unknown night death situation ({killer_role}/{victim_role}/{location.name})")

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
        self.prev_visiting.clear()
        self.prev_visiting.update(self.visiting)
        self.visiting.clear()
        # if someone was locked up last night, ensure they can't be locked up again tonight
        if self.last_voted is not None:
            add_lynch_immunity(var, self.last_voted, "pactbreaker")
        # alert people about clue tokens they have
        for player, amount in self.clue_tokens.items():
            if amount == 0:
                continue
            player.send(messages["pactbreaker_clue_notify"].format(amount))

    def on_lynch(self, evt: Event, var: GameState, votee: User, voters: Iterable[User]):
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

        del self.killing[:wrapper.source:]
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
            "graveyard": messages.raw("_commands", "graveyard"),
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
        # 2. Wolves can visit the forest multiple nights in a row
        # 3. Vampires can visit the graveyard multiple nights in a row

        player_home = get_home(var, wrapper.source)
        # default to home if n1 or they were in the stocks, to let them visit any location
        prev_location = self.prev_visiting.get(wrapper.source, player_home)
        player_role = get_main_role(var, wrapper.source)
        prev_name = prev_location.name if prev_location in (Forest, VillageSquare, Graveyard) else "house"
        target_name = target_location.name if target_location in (Forest, VillageSquare, Graveyard) else "house"
        if prev_name == target_name and prev_location is not player_home:
            if target_location is Forest and player_role in Wolf:
                pass
            elif target_location is Graveyard and player_role in Vampire:
                pass
            elif target_location is VillageSquare and player_role == "vigilante":
                pass
            else:
                wrapper.pm(messages["pactbreaker_no_visit_twice_{0}".format(target_name)])
                return

        del self.killing[:wrapper.source:]
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

    def kill(self, wrapper: MessageDispatcher, message: str):
        """Kill a player in the stocks or that you have collected evidence on."""
        var = wrapper.game_state
        if wrapper.source not in self.active_players:
            wrapper.pm(messages["pactbreaker_no_kill_stocks"])
            return

        target = get_target(wrapper, re.split(" +", message)[0], not_self_message="no_suicide")
        if not target:
            return

        player_role = get_main_role(var, wrapper.source)
        target_role = get_main_role(var, target)
        if is_known_wolf_ally(var, wrapper.source, target):
            wrapper.pm(messages["wolf_no_target_wolf"])
            return

        if is_known_vampire_ally(var, wrapper.source, target):
            wrapper.send(messages["no_target_vampire"])
            return

        if target is not self.in_stocks and player_role == "vampire":
            wrapper.send(messages["pactbreaker_no_kill_vampire"])
            return

        have_evidence = target in self.collected_evidence[wrapper.source]
        have_stale_evidence = target in self.stale_evidence[wrapper.source]
        thinks_is_vigilante = ((target_role == "vampire" and not have_evidence and have_stale_evidence)
                               or (target_role == "vigilante" and have_evidence))
        if target is not self.in_stocks and not have_evidence and not have_stale_evidence:
            wrapper.send(messages["pactbreaker_no_kill_evidence"].format(target))
            return

        if target_role == "villager" or (player_role == "vigilante" and thinks_is_vigilante):
            wrapper.send(messages["pactbreaker_no_kill_villager"].format(target))
            return

        self.killing[wrapper.source] = target
        self.visiting[wrapper.source] = Limbo
        wrapper.pm(messages["player_kill"].format(target))
        msg = messages["wolfchat_kill"].format(wrapper.source, target)

        if player_role in Wolf:
            send_wolfchat_message(var, wrapper.source, msg, Wolf, role="wolf", command="kill")
        elif player_role in Vampire:
            send_vampire_chat_message(var, wrapper.source, msg, Vampire, cmd="bite")

    def identify(self, wrapper: MessageDispatcher, message: str):
        """Spend clue tokens to learn about a player's role."""
        var = wrapper.game_state
        target = get_target(wrapper, re.split(" +", message)[0], not_self_message="no_investigate_self")
        if not target:
            return

        num_tokens = self.clue_tokens[wrapper.source]
        if num_tokens < 2:
            wrapper.send(messages["pactbreaker_no_id"])
            return

        self.clue_pool += num_tokens
        self.clue_tokens[wrapper.source] = 0
        target_role = get_main_role(var, target)
        if num_tokens == 2 and target_role == "vampire":
            target_role = "vigilante" if target in self.turned else "villager"
            if target_role == "vigilante":
                # let wolves attempt to !kill with this fake evidence
                self.stale_evidence[wrapper.source].add(target)
        else:
            self.collected_evidence[wrapper.source].add(target)

        wrapper.send(messages["investigate_success"].format(target, target_role))
