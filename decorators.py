from oyoyo.parse import parse_nick

def generate(fdict):
    def cmd(s, raw_nick=False):
        def dec(f):
            def innerf(*args):
                largs = list(args)
                largs[1] = parse_nick(largs[1])[0]
                return f(*largs)
            if raw_nick: fdict[s] = f
            else: fdict[s] = innerf
            return f
        return dec
    return cmd