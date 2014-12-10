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

def generate(fdict, permissions=True, **kwargs):
    """Generates a decorator generator.  Always use this"""
    def cmd(*s, raw_nick=False, admin_only=False, owner_only=False, hookid=-1):
        def dec(f):
            def innerf(*args):
                largs = list(args)
                if len(largs) > 1 and largs[1]:
                    nick, _, _, cloak = parse_nick(largs[1])

                    if cloak is None:
                        cloak = ""
                else:
                    nick = ""
                    cloak = ""
                if len(largs) > 3 and largs[2] and largs[2][0] == "#":
                    chan = largs[2]
                else:
                    chan = ""
                if not raw_nick and len(largs) > 1 and largs[1]:
                    largs[1] = nick
                if not permissions:
                    return f(*largs)
                if chan and not chan == botconfig.CHANNEL and not admin_only and not owner_only:
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
                                    return f(*largs)  # no questions
                if owner_only:
                    if var.is_owner(nick):
                        return f(*largs)
                    else:
                        largs[0].notice(nick, "You are not the owner.")
                        return
                if admin_only:
                    if var.is_admin(nick):
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
