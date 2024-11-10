from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src.functions import get_players
from src.gamestate import GameState
from src.events import EventListener, Event
from src import channels, users
from src.cats import Village

@game_mode("evilvillage", minp=6, maxp=18)
class EvilVillageMode(GameMode):
    """Majority of the village is wolf aligned, safes must secretly try to kill the wolves."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.CUSTOM_SETTINGS.abstain_enabled = False
        self.CUSTOM_SETTINGS.default_role = "cultist"
        self.CUSTOM_SETTINGS.hidden_role = "cultist"
        self.ROLE_GUIDE = {
            6:  ["wolf", "hunter"],
            8:  ["seer"],
            10: ["minion", "guardian angel"],
            12: ["shaman"],
            15: ["wolf(2)", "hunter(2)"],
        }
        self.EVENTS = {
            "chk_win": EventListener(self.chk_win)
        }

    def chk_win(self, evt: Event, var: GameState, rolemap, mainroles, lpl, lwolves, lrealwolves, lvampires):
        lsafes = len(get_players(var, Village, mainroles=mainroles))
        lcultists = len(get_players(var, ["cultist"], mainroles=mainroles))
        evt.stop_processing = True

        if evt.data["winner"] == "fools":
            return
        elif lrealwolves == 0 and lsafes == 0:
            evt.data["winner"] = "no_team_wins"
            evt.data["message"] = messages["evil_no_win"]
        elif lrealwolves == 0:
            evt.data["winner"] = "villagers"
            evt.data["message"] = messages["evil_villager_win"]
        elif lsafes == 0:
            evt.data["winner"] = "wolves"
            evt.data["message"] = messages["evil_wolf_win"]
        elif lcultists == 0:
            evt.data["winner"] = "villagers"
            evt.data["message"] = messages["evil_cultists_dead"]
        elif lsafes == lpl / 2:
            evt.data["winner"] = "villagers"
            evt.data["message"] = messages["evil_villager_tie"]
        elif lsafes > lpl / 2:
            evt.data["winner"] = "villagers"
            evt.data["message"] = messages["evil_more_villagers"]
        else:
            evt.data["winner"] = None
