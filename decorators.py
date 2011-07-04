def generate(fdict):
    def cmd(s):
        def dec(f):
            fdict[s] = f
            return f
        return dec
    return cmd