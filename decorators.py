from oyoyo.parse import parse_nick
import botconfig

def generate(fdict, **kwargs):
    """Generates a decorator generator.  Always use this"""
    def cmd(*s, raw_nick=False, admin_only=False, owner_only=False):
        def dec(f):
            def innerf(*args):
                largs = list(args)
                if largs[1]:
                    cloak = parse_nick(largs[1])[3]
                else:
                    cloak = ""
                if not raw_nick and largs[1]:
                    largs[1] = parse_nick(largs[1])[0]  # username
                    #if largs[1].startswith("#"):       
                if owner_only:
                    if cloak and cloak == botconfig.OWNER:
                        return f(*largs)
                    elif cloak:
                        largs[0].notice(largs[1], "You are not the owner.")
                        return
                if admin_only:
                    if cloak and cloak in botconfig.ADMINS:
                        return f(*largs)
                    elif cloak:
                        largs[0].notice(largs[1], "You are not an admin.")
                        return
                return f(*largs)
            for x in s:
                if x not in fdict.keys():
                    fdict[x] = []
                else:
                    for fn in fdict[x]:
                        if (fn.owner_only != owner_only or
                            fn.admin_only != admin_only):
                            raise Exception("Command: "+x+" has non-matching protection levels!")
                fdict[x].append(innerf)
            innerf.owner_only = owner_only
            innerf.raw_nick = raw_nick
            innerf.admin_only = admin_only
            return innerf
            
        return dec
        
    return lambda *args, **kwarargs: cmd(*args, **kwarargs) if kwarargs else cmd(*args, **kwargs)