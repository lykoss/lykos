from src.functions import get_all_roles
from src.decorators import event_listener
from src.roles.helper.wolves import register_wolf

register_wolf("werekitten")

@event_listener("gun_shoot")
def on_gun_shoot(evt, var, user, target, role):
    if "werekitten" in get_all_roles(target):
        evt.data["hit"] = False
        evt.data["kill"] = False

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["werekitten"] = {"Wolf", "Wolfchat", "Wolfteam", "Innocent", "Killer", "Nocturnal", "Village Objective", "Wolf Objective"}
