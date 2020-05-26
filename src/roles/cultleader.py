from src.decorators import event_listener
from src.roles.helper.wolves import register_wolf

register_wolf("cult leader")

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["cult leader"] = {"Wolfchat", "Wolfteam"}
