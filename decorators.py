from oyoyo.parse import parse_nick
import botconfig

def generate(fdict, **kwargs):
    """Generates a decorator generator.  Always use this"""
    def cmd(*s, raw_nick=False, admin_only=False, owner_only=False):
        def dec(f):
            def innerf(*args):
                largs = list(args)
                if not raw_nick and largs[1]:
                    cloak = parse_nick(largs[1])[3]
                    largs[1] = parse_nick(largs[1])[0]
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
                fdict[x] = innerf
            return innerf
            
        return dec
        
    return lambda *args, **kwarargs: cmd(*args, **kwarargs) if kwarargs else cmd(*args, **kwargs)