import random
import threading
import botconfig
from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src.functions import get_all_players, get_players
from src import events, channels, users


@game_mode("villagergame", minp=4, maxp=9, likelihood=0)
class VillagergameMode(GameMode):
    """This mode definitely does not exist, now please go away."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_GUIDE = {
            4: ["seer"],
            6: ["cursed villager"],
            7: ["shaman"],
            8: ["harlot"],
            9: ["crazed shaman"],
        }

    def can_vote_bot(self, var):
        return True

    def startup(self):
        events.add_listener("chk_win", self.chk_win)
        events.add_listener("chk_nightdone", self.chk_nightdone)
        events.add_listener("transition_day_begin", self.transition_day)
        events.add_listener("retribution_kill", self.on_retribution_kill, priority=4)
        events.add_listener("lynch", self.on_lynch)
        events.add_listener("reconfigure_stats", self.reconfigure_stats)

    def teardown(self):
        events.remove_listener("chk_win", self.chk_win)
        events.remove_listener("chk_nightdone", self.chk_nightdone)
        events.remove_listener("transition_day_begin", self.transition_day)
        events.remove_listener("retribution_kill", self.on_retribution_kill, priority=4)
        events.remove_listener("lynch", self.on_lynch)
        events.remove_listener("reconfigure_stats", self.reconfigure_stats)

    def reconfigure_stats(self, evt, var, roleset, reason):
        if reason == "start":
            pc = len(var.ALL_PLAYERS)
            roleset["wolf"] += 1
            roleset["villager"] -= 1
            if pc == 7:
                roleset["cultist"] += 1
                roleset["villager"] -= 1
            elif pc >= 8:
                roleset["traitor"] += 1
                roleset["villager"] -= 1

    def chk_win(self, evt, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
        # village can only win via unanimous vote on the bot nick
        # villagergame_lose should probably explain that mechanic
        # Note: not implemented here since that needs to work in default too
        pc = len(var.ALL_PLAYERS)
        if (pc >= 8 and lpl <= 4) or lpl <= 2:
            evt.data["winner"] = ""
            evt.data["message"] = messages["villagergame_lose"].format(botconfig.CMD_CHAR, users.Bot.nick)
        else:
            evt.data["winner"] = None

    def chk_nightdone(self, evt, var):
        transition_day = evt.data["transition_day"]
        evt.data["transition_day"] = lambda gameid=0: self.prolong_night(var, gameid, transition_day)

    def prolong_night(self, var, gameid, transition_day):
        nspecials = len(get_all_players(("seer", "harlot", "shaman", "crazed shaman")))
        rand = random.gauss(5, 1.5)
        if rand <= 0 and nspecials > 0:
            transition_day(gameid=gameid)
        else:
            t = threading.Timer(abs(rand), transition_day, kwargs={"gameid": gameid})
            t.start()

    def transition_day(self, evt, var):
        # 30% chance we kill a safe, otherwise kill at random
        # when killing safes, go after seer, then harlot, then shaman
        self.delaying_night = False
        pl = get_players()
        tgt = None
        seer = None
        hlt = None
        hvst = None
        shmn = None
        if len(var.ROLES["seer"]) == 1:
            seer = list(var.ROLES["seer"])[0]
        if len(var.ROLES["harlot"]) == 1:
            hlt = list(var.ROLES["harlot"])[0]
            from src.roles import harlot
            hvst = harlot.VISITED.get(hlt)
            if hvst is not None:
                pl.remove(hlt)
        if len(var.ROLES["shaman"]) == 1:
            shmn = list(var.ROLES["shaman"])[0]
        if random.random() < 0.3:
            if seer:
                tgt = seer
            elif hvst:
                tgt = hvst
            elif shmn:
                tgt = shmn
            elif hlt and not hvst:
                tgt = hlt
        if not tgt:
            tgt = random.choice(pl)
        from src.roles.helper import wolves
        wolves.KILLS[users.Bot] = [tgt]

    def on_retribution_kill(self, evt, var, victim, orig_target):
        # There are no wolves for this totem to kill
        if orig_target == "@wolves":
            evt.data["target"] = None
            evt.stop_processing = True

    def on_lynch(self, evt, var, votee, voters):
        from src import votes
        if votee is users.Bot:
            if len(voters) == evt.params.players:
                channels.Main.send(messages["villagergame_win"])
                from src.wolfgame import stop_game
                stop_game(var, "everyone")
            # we don't want to attempt to kill the bot, and we don't
            # want any votes on the bot to count for ending day
            votes.LYNCHED -= 1
            evt.prevent_default = True
