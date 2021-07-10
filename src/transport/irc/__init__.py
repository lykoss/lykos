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

# Services

class Services_Base:
    name = ""
    nickserv = ""
    command = ""
    regain = ""
    release = ""
    ghost = ""

    def supports_auth(self):
        return bool(self.command)

    def supports_regain(self):
        return bool(self.regain)

    def supports_release(self):
        return bool(self.release)

    def supports_ghost(self):
        return bool(self.ghost)

class Services_Anope(Services_Base):
    name = "anope"
    nickserv = "NickServ"
    command = "IDENTIFY {account} {password}"
    regain = "RECOVER {nick} {password}"
    release = "RELEASE {nick} {password}"
    ghost = "GHOST {nick} {password}"

class Services_Atheme(Services_Base):
    name = "atheme"
    nickserv = "NickServ"
    command = "IDENTIFY {account} {password}"
    regain = "REGAIN {nick} {password}"
    release = "RELEASE {nick} {password}"
    ghost = "GHOST {nick} {password}"

class Services_Generic(Services_Base):
    name = "generic"
    nickserv = "NickServ"
    command = "IDENTIFY {account} {password}"
    ghost = "GHOST {nick} {password}"

class Services_None(Services_Base):
    name = "none"

class Services_Undernet(Services_Base):
    # undernet does not support GHOST, because it sucks. why are you even on undernet
    name = "undernet"
    nickserv = "x@channels.undernet.org"
    command = "LOGIN {account} {password}"
