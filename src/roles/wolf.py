from src.decorators import event_listener
from src.roles.helper.wolves import register_killer

register_killer("wolf")

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["wolf"] = {"Wolf", "Wolfchat", "Wolfteam", "Killer", "Nocturnal"}
