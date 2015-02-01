# Copyright (c) 2011, Jimmy Cao
# All rights reserved.

# Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

# Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
# Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


from oyoyo.parse import parse_nick
import fnmatch
import botconfig
import settings.wolfgame as var
from tools import logger

adminlog = logger(None)

def generate(fdict, permissions=True, **kwargs):
    """Generates a decorator generator.  Always use this"""
    def cmd(*s, raw_nick=False, admin_only=False, owner_only=False, chan=True, pm=False,
                game=False, join=False, none=False, playing=False, roles=(), hookid=-1):
        def dec(f):
            def innerf(*args):
                largs = list(args)
                rawnick = largs[1]
                if not permissions:
                    return f(*largs)
                if len(largs) > 1 and largs[1]:
                    nick, _, _, cloak = parse_nick(largs[1])

                    if cloak is None:
                        cloak = ""
                else:
                    nick = ""
                    cloak = ""
                if not raw_nick and len(largs) > 1 and largs[1]:
                    largs[1] = nick
                if nick == "<console>":
                    return f(*largs) # special case; no questions
                if not pm and largs[2] == nick: # PM command
                    return
                if not chan and largs[2] != nick: # channel command
                    return
                if largs[2].startswith("#") and largs[2] != botconfig.CHANNEL and not admin_only and not owner_only:
                    if "" in s:
                        return # Don't have empty commands triggering in other channels
                    allowed = False
                    for cmdname in s:
                        if cmdname in botconfig.ALLOWED_ALT_CHANNELS_COMMANDS:
                            allowed = True
                            break
                    if not allowed:
                        return
                if nick in var.USERS.keys() and var.USERS[nick]["account"] != "*":
                    acc = var.USERS[nick]["account"]
                else:
                    acc = None
                if "" in s:
                    return f(*largs)
                if game and var.PHASE not in ("day", "night") + (("join",) if join else ()):
                    largs[0].notice(nick, "No game is currently running.")
                    return
                if ((join and none and var.PHASE not in ("join", "none"))
                        or (none and not join and var.PHASE != "none")):
                    largs[0].notice(nick, "Sorry, but the game is already running. Try again next time.")
                    return
                if join and not none:
                    if var.PHASE == "none":
                        largs[0].notice(nick, "No game is currently running.")
                        return
                    if var.PHASE != "join" and not game:
                        largs[0].notice(nick, "Werewolf is already in play.")
                        return
                if playing and nick not in var.list_players() or nick in var.DISCONNECTED.keys():
                    largs[0].notice(nick, "You're not currently playing.")
                    return
                if roles:
                    for role in roles:
                        if nick in var.ROLES[role]:
                            break
                    else:
                        return
                if acc:
                    for pattern in var.DENY_ACCOUNTS.keys():
                        if fnmatch.fnmatch(acc.lower(), pattern.lower()):
                            for cmdname in s:
                                if cmdname in var.DENY_ACCOUNTS[pattern]:
                                    largs[0].notice(nick, "You do not have permission to use that command.")
                                    return
                    for pattern in var.ALLOW_ACCOUNTS.keys():
                        if fnmatch.fnmatch(acc.lower(), pattern.lower()):
                            for cmdname in s:
                                if cmdname in var.ALLOW_ACCOUNTS[pattern]:
                                    if admin_only or owner_only:
                                        adminlog(largs[2], rawnick, s[0], largs[3])
                                    return f(*largs)
                if not var.ACCOUNTS_ONLY and cloak:
                    for pattern in var.DENY.keys():
                        if fnmatch.fnmatch(cloak.lower(), pattern.lower()):
                            for cmdname in s:
                                if cmdname in var.DENY[pattern]:
                                    largs[0].notice(nick, "You do not have permission to use that command.")
                                    return
                    for pattern in var.ALLOW.keys():
                        if fnmatch.fnmatch(cloak.lower(), pattern.lower()):
                            for cmdname in s:
                                if cmdname in var.ALLOW[pattern]:
                                    if admin_only or owner_only:
                                        adminlog(largs[2], rawnick, s[0], largs[3])
                                    return f(*largs)  # no questions
                if owner_only:
                    if var.is_owner(nick, cloak):
                        adminlog(largs[2], rawnick, s[0], largs[3])
                        return f(*largs)
                    else:
                        largs[0].notice(nick, "You are not the owner.")
                        return
                if admin_only:
                    if var.is_admin(nick, cloak):
                        adminlog(largs[2], rawnick, s[0], largs[3])
                        return f(*largs)
                    else:
                        largs[0].notice(nick, "You are not an admin.")
                        return
                return f(*largs)
            alias = False
            innerf.aliases = []
            for x in s:
                if x not in fdict.keys():
                    fdict[x] = []
                else:
                    for fn in fdict[x]:
                        if (fn.owner_only != owner_only or
                            fn.admin_only != admin_only):
                            raise Exception("Command: "+x+" has non-matching protection levels!")
                fdict[x].append(innerf)
                if alias:
                    innerf.aliases.append(x)
                alias = True
            innerf.owner_only = owner_only
            innerf.raw_nick = raw_nick
            innerf.admin_only = admin_only
            innerf.chan = chan
            innerf.pm = pm
            innerf.none = none
            innerf.join = join
            innerf.game = game
            innerf.playing = playing
            innerf.roles = roles
            innerf.hookid = hookid
            innerf.__doc__ = f.__doc__
            return innerf
            
        return dec
        
    return lambda *args, **kwarargs: cmd(*args, **kwarargs) if kwarargs else cmd(*args, **kwargs)
    
    
def unhook(hdict, hookid):
    for cmd in list(hdict.keys()):
        for x in hdict[cmd]:
            if x.hookid == hookid:
                hdict[cmd].remove(x)
        if not hdict[cmd]:
            del hdict[cmd]
