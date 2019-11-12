import random
import time
import threading
import botconfig
from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src.functions import get_all_players, get_players
from src.events import EventListener
from src import channels, users

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
        self.EVENTS = {
            "chk_win": EventListener(self.chk_win),
            "chk_nightdone": EventListener(self.chk_nightdone),
            "transition_day_begin": EventListener(self.transition_day),
            "retribution_kill": EventListener(self.on_retribution_kill, priority=4),
            "lynch": EventListener(self.on_lynch),
            "reconfigure_stats": EventListener(self.reconfigure_stats)
        }
        self.saved_timers = {}

    def can_vote_bot(self, var):
        return True

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
            evt.data["message"] = messages["villagergame_lose"].format(users.Bot)
        else:
            evt.data["winner"] = None

    def chk_nightdone(self, evt, var):
        self.saved_timers = var.TIMERS
        transition_day = evt.data["transition_day"]
        evt.data["transition_day"] = lambda gameid=0: self.prolong_night(var, gameid, transition_day)

    def prolong_night(self, var, gameid, transition_day):
        nspecials = len(get_all_players(("seer", "harlot", "shaman", "crazed shaman")))
        rand = random.gauss(5, 1.5)
        if rand <= 0 and nspecials > 0:
            transition_day(gameid=gameid)
        else:
            # rejig the night ending timer to cleanup what we're doing
            # NOTE: this relies on implementation details in CPython and may not work across python versions
            # or with other python implementations. If this becomes problematic, we may want to use our own timer impl
            # rather than rely on threading.Timer; we can mostly just lift what CPython has for that
            if "night" in self.saved_timers:
                oldid = self.saved_timers["night"][0].kwargs["gameid"]
                self.saved_timers["night"][0].kwargs = {
                    "var": var,
                    "gameid": oldid,
                    "transition_day": transition_day
                }
                self.saved_timers["night"][0].function = self.prolong_night_end

            # bootstrap villagergame delay timer
            current = time.time()
            delay = abs(rand)
            t = threading.Timer(delay, self.prolong_night_end,
                                kwargs={"var": var, "gameid": gameid, "transition_day": transition_day})
            self.saved_timers["villagergame"] = (t, current, delay)

            # restart saved timers (they were cancelled before prolong_night was called)
            for name, t in self.saved_timers.items():
                elapsed = current - t[1]
                remaining = t[2] - elapsed
                if remaining > 0:
                    new_timer = threading.Timer(remaining, t[0].function, t[0].args, t[0].kwargs)
                    var.TIMERS[name] = (new_timer, t[1], t[2])
                    new_timer.daemon = True
                    new_timer.start()

            self.saved_timers = {}

    def prolong_night_end(self, var, gameid, transition_day):
        # clean up timers again before calling transition_day
        for x, t in var.TIMERS.items():
            if t[0].is_alive():
                t[0].cancel()
        self.saved_timers = {}
        var.TIMERS = {}
        transition_day(gameid=gameid)

    def transition_day(self, evt, var):
        # 30% chance we kill a safe, otherwise kill at random
        # when killing safes, go after seer, then harlot, then shaman
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
                evt.stop_processing = True
            # we don't want to attempt to kill the bot, and we don't
            # want any votes on the bot to count for ending day
            votes.LYNCHED -= 1
            evt.prevent_default = True
