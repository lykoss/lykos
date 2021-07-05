from __future__ import annotations

from src import config

__all__ = ["get_ircd", "get_services"]

def get_ircd() -> IRCD_Base:
    module = config.Main.get("transports[0].module")
    if module == "hybrid":
        return IRCD_Hybrid()
    elif module == "inspircd":
        return IRCD_Inspire()
    elif module == "generic":
        return IRCD_Generic()
    elif module == "solanum":
        return IRCD_Solanum()
    elif module == "unrealircd":
        return IRCD_Unreal()
    else:
        raise config.InvalidConfigValue(f"unknown IRCd value {module}")

def get_services() -> Services_Base:
    module = config.Main.get("transports[0].authentication.services.module")
    if module == "anope":
        return Services_Anope()
    elif module == "atheme":
        return Services_Atheme()
    elif module == "generic":
        return Services_Generic()
    elif module == "none":
        return Services_None()
    elif module == "undernet":
        return Services_Undernet()
    else:
        raise config.InvalidConfigValue(f"unknown services value {module}")

class IRCD_Base:
    name = ""
    quiet_mode = ""
    quiet_prefix = ""

    def supports_quiet(self):
        return False

class IRCD_Hybrid(IRCD_Base):
    name = "hybrid"

class IRCD_Inspire(IRCD_Base):
    name = "inspircd"

class IRCD_Generic(IRCD_Base):
    name = "generic"

class IRCD_Solanum(IRCD_Base):
    name = "solanum"
    quiet_mode = "q"

    def supports_quiet(self):
        return True

class IRCD_Unreal(IRCD_Base):
    name = "unrealircd"


class Services_Base:
    name = ""
    nickserv = ""
    command = ""

    def supports_auth(self):
        return False

class Services_Anope(Services_Base):
    name = "anope"
    nickserv = "NickServ"
    command = "IDENTIFY {account} {password}"

    def supports_auth(self):
        return True

class Services_Atheme(Services_Base):
    name = "atheme"
    nickserv = "NickServ"
    command = "IDENTIFY {account} {password}"

    def supports_auth(self):
        return True

class Services_Generic(Services_Base):
    name = "generic"
    nickserv = "NickServ"
    command = "IDENTIFY {account} {password}"

    def supports_auth(self):
        return True

class Services_None(Services_Base):
    name = "none"

class Services_Undernet(Services_Base):
    name = "undernet"
    nickserv = "x@channels.undernet.org"
    command = "LOGIN {account} {password}"

    def supports_auth(self):
        return True
