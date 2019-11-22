# Imports all gamemode definitions
import os.path
import glob
import importlib
import src.settings as var
from src.messages import messages
from src.events import Event, EventListener
from src.cats import All, Cursed, Wolf, Innocent, Village, Neutral, Hidden, Team_Switcher, Win_Stealer, Nocturnal, Killer, Spy

__all__ = ["InvalidModeException", "game_mode", "GameMode"]

class InvalidModeException(Exception):
    pass

def game_mode(name, minp, maxp, likelihood=0):
    def decor(c):
        c.name = name
        var.GAME_MODES[name] = (c, minp, maxp, likelihood)
        return c
    return decor

class GameMode:
    def __init__(self, arg=""):
        # Default values for the role sets and secondary roles restrictions
        self.ROLE_SETS = {
            "gunner/sharpshooter": {"gunner": 4, "sharpshooter": 1},
        }
        self.SECONDARY_ROLES = {
            "cursed villager"   : All - Cursed - Wolf - Innocent - {"seer", "oracle"},
            "gunner"            : Village + Neutral + Hidden - Innocent - Team_Switcher,
            "sharpshooter"      : Village + Neutral + Hidden - Innocent - Team_Switcher,
            "mayor"             : All - Innocent - Win_Stealer,
            "assassin"          : All - Nocturnal + Killer - Wolf - Innocent - Spy - Team_Switcher - {"traitor"}, # inaccurate, but best bet for now
            "blessed villager"  : ["villager"],
        }
        self.DEFAULT_TOTEM_CHANCES = self.TOTEM_CHANCES = {}
        self.NUM_TOTEMS = {}

        self.EVENTS = {}

        # Support all shamans and totems
        # Listeners should add their custom totems with non-zero chances, and custom roles in evt.data["shaman_roles"]
        # Totems (both the default and custom ones) get filled with every shaman role at a chance of 0
        # Add totems with a priority of 1 and shamans with a priority of 3
        # Listeners at priority 5 can make use of this information freely
        evt = Event("default_totems", {"shaman_roles": set()})
        evt.dispatch(self.TOTEM_CHANCES)

        shamans = evt.data["shaman_roles"]
        for chances in self.TOTEM_CHANCES.values():
            if chances.keys() != shamans:
                for role in shamans:
                    if role not in chances:
                        chances[role] = 0 # default to 0 for new totems/shamans

        for role in shamans:
            if role not in self.NUM_TOTEMS:
                self.NUM_TOTEMS[role] = 1 # shamans get 1 totem per night by default

        if not arg:
            return

        arg = arg.replace("=", ":").replace(";", ",")

        pairs = [arg]
        while pairs:
            pair, *pairs = pairs[0].split(",", 1)
            change = pair.lower().replace(":", " ").strip().rsplit(None, 1)
            if len(change) != 2:
                raise InvalidModeException(messages["invalid_mode_args"].format(arg))

            key, val = change
            if key in ("role reveal", "reveal roles"):
                if val not in ("on", "off", "team"):
                    raise InvalidModeException(messages["invalid_reveal"].format(val))
                self.ROLE_REVEAL = val
                if val == "off" and not hasattr(self, "STATS_TYPE"):
                    self.STATS_TYPE = "disabled"
                elif val == "team" and not hasattr(self, "STATS_TYPE"):
                    self.STATS_TYPE = "team"
            elif key in ("stats type", "stats"):
                if val not in ("default", "accurate", "team", "disabled"):
                    raise InvalidModeException(messages["invalid_stats"].format(val))
                self.STATS_TYPE = val
            elif key == "abstain":
                if val not in ("enabled", "restricted", "disabled"):
                    raise InvalidModeException(messages["invalid_abstain"].format(val))
                if val == "enabled":
                    self.ABSTAIN_ENABLED = True
                    self.LIMIT_ABSTAIN = False
                elif val == "restricted":
                    self.ABSTAIN_ENABLED = True
                    self.LIMIT_ABSTAIN = True
                elif val == "disabled":
                    self.ABSTAIN_ENABLED = False

    def startup(self):
        for event, listeners in self.EVENTS.items():
            if isinstance(listeners, EventListener):
                listeners.install(event)
            else:
                for listener in listeners:
                    listener.install(event)

    def teardown(self):
        for event, listeners in self.EVENTS.items():
            if isinstance(listeners, EventListener):
                listeners.remove(event)
            else:
                for listener in listeners:
                    listener.remove(event)

    def can_vote_bot(self, var):
        return False

    def set_default_totem_chances(self):
        if self.TOTEM_CHANCES is self.DEFAULT_TOTEM_CHANCES:
            return # nothing more we can do
        for totem, chances in self.TOTEM_CHANCES.items():
            if totem not in self.DEFAULT_TOTEM_CHANCES or self.DEFAULT_TOTEM_CHANCES[totem].keys() == chances.keys():
                continue
            for role, value in self.DEFAULT_TOTEM_CHANCES[totem].items():
                if role not in chances:
                    chances[role] = value

    # Here so any game mode can use it
    def lovers_chk_win(self, evt, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
        winner = evt.data["winner"]
        if winner in Win_Stealer:
            return # fool won, lovers can't win even if they would
        from src.roles.matchmaker import get_lovers
        all_lovers = get_lovers()
        if len(all_lovers) != 1:
            return # we need exactly one cluster alive for this to trigger

        lovers = all_lovers[0]

        if len(lovers) == lpl:
            evt.data["winner"] = "lovers"
            evt.data["message"] = messages["lovers_win"]

    def all_dead_chk_win(self, evt, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
        if evt.data["winner"] == "no_team_wins":
            evt.data["winner"] = "everyone"
            evt.data["message"] = messages["everyone_died_won"]

path = os.path.dirname(os.path.abspath(__file__))
search = os.path.join(path, "*.py")

for f in glob.iglob(search):
    f = os.path.basename(f)
    n, _ = os.path.splitext(f)
    if f.startswith("_"):
        continue
    importlib.import_module("." + n, package="src.gamemodes")
