__all__ = ["plural", "singular"]

def plural(role, count=2): # FIXME: deprecated, use translation metadata
    if count == 1:
        return role
    bits = role.split()
    if bits[-1][-2:] == "'s":
        bits[-1] = plural(bits[-1][:-2], count)
        bits[-1] += "'" if bits[-1][-1] == "s" else "'s"
    else:
        bits[-1] = {"person": "people",
                    "wolf": "wolves",
                    "has": "have",
                    "succubus": "succubi",
                    "child": "children"}.get(bits[-1], bits[-1] + "s")
    return " ".join(bits)

def singular(plural): # FIXME: deprecated, use translation metadata
    # converse of plural above (kinda)
    # this is used to map plural team names back to singular,
    # so we don't need to worry about stuff like possessives
    # Note that this is currently only ever called on team names,
    # and will require adjustment if one wishes to use it on roles.
    # fool is present since we store fool wins as 'fool' rather than
    # 'fools' as only a single fool wins, however we don't want to
    # chop off the l and have it report 'foo wins'
    # same thing with 'everyone'
    conv = {"wolves": "wolf",
            "succubi": "succubus",
            "fool": "fool",
            "everyone": "everyone"}
    if plural in conv:
        return conv[plural]
    # otherwise we just added an s on the end
    return plural[:-1]
