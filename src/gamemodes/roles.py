from collections import Counter
import src.settings as var  # FIXME: remove dependency on var here; use DI to inject into ctor
from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src import events, channels, users, cats

@game_mode("roles", minp=4, maxp=35)
class ChangedRolesMode(GameMode):
    """Example: !fgame roles=wolf:1,seer:0,guardian angel:1"""

    def __init__(self, arg=""):
        super().__init__(arg)
        self.MAX_PLAYERS = 35
        self.ROLE_GUIDE = {1: []}
        arg = arg.replace("=", ":").replace(";", ",")

        pairs = [arg]
        while pairs:
            pair, *pairs = pairs[0].split(",", 1)
            change = pair.replace(":", " ").strip().rsplit(None, 1)
            if len(change) != 2:
                raise InvalidModeException(messages["invalid_mode_roles"].format(arg))
            role, num = change
            role = role.lower()
            num = num.lower()
            try:
                if role in var.DISABLED_ROLES:
                    raise InvalidModeException(messages["role_disabled"].format(role))
                elif role in cats.ROLES:
                    self.ROLE_GUIDE[1].extend((role,) * int(num))
                elif "/" in role:
                    choose = role.split("/")
                    for c in choose:
                        if c not in cats.ROLES:
                            raise InvalidModeException(messages["specific_invalid_role"].format(c))
                        elif c in var.DISABLED_ROLES:
                            raise InvalidModeException(messages["role_disabled"].format(c))
                    self.ROLE_SETS[role] = Counter(choose)
                    self.ROLE_GUIDE[1].extend((role,) * int(num))
                elif role == "default" and num in cats.ROLES:
                    self.DEFAULT_ROLE = num
                elif role.lower() == "hidden" and num in ("villager", "cultist"):
                    self.HIDDEN_ROLE = num
                elif role.lower() in ("role reveal", "reveal roles", "stats type", "stats", "abstain", "lover wins with fool"):
                    # handled in parent constructor
                    pass
                else:
                    raise InvalidModeException(messages["specific_invalid_role"].format(role))
            except ValueError:
                raise InvalidModeException(messages["bad_role_value"])
