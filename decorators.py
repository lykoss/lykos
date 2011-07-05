from oyoyo.parse import parse_nick
import botconfig;

def generate(fdict):
    def cmd(s, raw_nick=False, admin_only=False):
        def dec(f):
            def innerf(*args):
                largs = list(args)
                if not raw_nick: largs[1] = parse_nick(largs[1])[0]
                if admin_only:
                    if largs[1] in botconfig.ADMINS:
                        return f(*largs)
                    else:
                        largs[0].notice(largs[1], "You are not an admin.")
                        return
                return f(*largs)
            fdict[s] = innerf
            return f
        return dec
    return cmd