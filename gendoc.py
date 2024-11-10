import copy
from collections import OrderedDict, Counter
from io import StringIO
from pathlib import Path
import sys
from typing import Optional
from requests import Session
import hashlib
import json
import re
from ruamel.yaml import YAML, RoundTripRepresenter, SafeRepresenter

from src.config import Config, Empty, merge
from src.gamemodes import GAME_MODES
from src.cats import all_cats, all_roles, role_order, Category

class Undefined:
    pass

class CategoryEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Category):
            return str(o)
        return super().default(o)

Conf = Config()

def add_section(section, indent=2, path="", name=None):
    if not name:
        name = section["_name"]
    path = f"{path}.{name}" if path else name
    heading = "=" * indent
    desc = section["_desc"]
    if "_name" in section and indent > 2:
        desc = f"Instance of [[#{section['_name']}|{section['_name']}]]."
    nullable_note = ""
    if section.get("_nullable", False):
        nullable_note = "\n\nCan be null."
    markup = f"{heading} {path} {heading}\n{desc.strip()}{nullable_note}\n\n"
    if indent == 2 or "_name" not in section:
        markup += add_values(section, indent=indent, path=path)
    return markup

def add_values(section, indent, path):
    markup = ""
    t = section["_type"]
    nullable = section.get("_nullable", False)
    default_null = nullable and section.get("_default", "placeholder") is None
    if isinstance(t, dict):
        # complex type
        section = t
        t = section["_type"]

    if isinstance(t, list):
        t = set(t)

    if "_name" in section and indent > 2:
        return f"Instance of [[#{section['_name']}|{section['_name']}]].\n"

    default = section.get("_default", "''(none)''")
    if default == "''(none)''":
        pass
    elif default_null:
        default = "<code>null</code>"
    elif t == "str":
        default = f'<code>"{default}"</code>'
    elif t == "bool":
        default = "<code>true</code>" if default else "<code>false</code>"
    elif t in ("int", "float", "enum") or (isinstance(t, set) and t & {"int", "float", "enum"} == t):
        default = f'<code>{default}</code>'
    elif t == "list":
        if not default:
            default = "''(empty list)''"
        else:
            default = yaml_dump(default)
    elif t == "dict":
        munged = OrderedDict()
        for key, item_metadata in sorted(default.items(), key=lambda x: x[0]):
            if "_name" in item_metadata:
                munged[key] = f"(see {item_metadata['_name']})"
            else:
                try:
                    value = merge(item_metadata, Empty, Empty)
                except TypeError:
                    value = Undefined()
                munged[key] = value
        default = yaml_dump(munged)
    else:
        default = f"UNHANDLED TYPE {t}\n"

    markup += f"'''Default Value:''' {default}\n"

    if t == "dict":
        # Make subsections with the valid keys, in alphabetical order
        for key, value in sorted(section["_default"].items(), key=lambda x: x[0]):
            markup += add_section(value, indent=indent+1, path=path, name=key)
    elif t == "enum":
        # Make a list of the valid enum choices
        markup += "\n'''Allowed Values:'''\n"
        for value in section["_values"]:
            markup += f"* {value}\n"

    return markup

def yaml_dump(obj):
    with StringIO() as buffer:
        with YAML(output=buffer) as y:
            y.dump(obj)
        dump = buffer.getvalue()
        return f"\n<syntaxhighlight lang=\"yaml\">{dump}</syntaxhighlight>\n"

def generate_config_page():
    # Initialize markup with our intro (as a template so we can easily edit it without needing to push code changes)
    markup = "{{config intro}}\n"
    # Add in the root
    markup += add_section(Conf.metadata)
    # Add the rest of the sections in alphabetical order
    sorted_keys = sorted([x for x in Conf.metadata.keys() if x[0] != "_"])
    for key in sorted_keys:
        markup += add_section(Conf.metadata[key])
    return markup

def generate_roles_page():
    obj = {
        "categories": {k: sorted(v.roles) for k, v in all_cats().items()},
        "order": list(role_order()),
        "roles": all_roles()
    }

    # pretty-print for easier human parsing
    # sort keys to ensure that page content remains stable between executions (as otherwise dict order is arbitrary)
    return json.dumps(obj, indent=2, sort_keys=True, cls=CategoryEncoder)

def generate_gamemodes_page():
    obj = {
        "modes": {}
    }
    total_likelihood = 0
    for mode, min_players, max_players in GAME_MODES.values():
        if mode.name in ("roles",):
            continue
        likelihood = Conf.get(f"gameplay.modes.{mode.name}.weight", 0)
        mode_inst = mode()
        role_guide = {}
        default_role = mode_inst.CUSTOM_SETTINGS.default_role
        mode_obj = {
            "min": min_players,
            "max": max_players,
            "likelihood": likelihood,
            "default role": default_role,
            "defined counts": sorted(mode_inst.ROLE_GUIDE.keys())
        }
        c = Counter({default_role: min_players})
        seen_roles = set()
        set_only_roles = set()
        strip = lambda x: re.sub(r"\(.*\)", "", x)
        for role_defs in mode_inst.ROLE_GUIDE.values():
            seen_roles.update(strip(x) for x in role_defs if x[0] != "-")
        for role_set, set_roles in mode_inst.ROLE_SETS.items():
            if role_set not in seen_roles:
                continue
            set_only_roles.update(set_roles.keys() - seen_roles)
            seen_roles.update(set_roles.keys())

        for role in seen_roles:
            if role in set_only_roles:
                continue
            c[role] = 0

        exclude = set(mode_inst.SECONDARY_ROLES.keys()) | set(mode_inst.ROLE_SETS.keys()) | {default_role}
        for i in range(min_players, max_players + 1):
            if i in mode_inst.ROLE_GUIDE:
                for role in mode_inst.ROLE_GUIDE[i]:
                    role = strip(role)
                    if role[0] == "-":
                        role = role[1:]
                        c[role] -= 1
                    else:
                        c[role] += 1
            c[default_role] = i - sum(v for k, v in c.items() if k not in exclude)
            role_guide[i] = {k: v for k, v in c.items()}
        mode_obj["role guide"] = role_guide
        secondary_roles = sorted(iter(mode_inst.SECONDARY_ROLES.keys() & seen_roles))
        mode_obj["secondary roles"] = {r: str(mode_inst.SECONDARY_ROLES[r]) for r in secondary_roles}
        mode_obj["role sets"] = {k: v for k, v in mode_inst.ROLE_SETS.items() if k in seen_roles}
        obj["modes"][mode.name] = mode_obj

        total_likelihood += likelihood

    obj["total likelihood"] = total_likelihood

    return json.dumps(obj, indent=2, sort_keys=True)

def generate_docs(doc_type):
    if doc_type == "config":
        return generate_config_page()
    elif doc_type == "roles":
        return generate_roles_page()
    elif doc_type == "gamemodes":
        return generate_gamemodes_page()
    else:
        print(f"Unknown documentation type {doc_type}")
        sys.exit(1)

def wiki_api(session: Session,
             url: str,
             params: dict,
             data: Optional[dict] = None,
             method: Optional[str] = None,
             assert_bot: Optional[str] = None):
    method = method or ("POST" if data else "GET")
    params = copy.copy(params)
    params.update({"format": "json", "formatversion": 2})
    if assert_bot:
        params.update({"assert": "bot", "assertuser": assert_bot})
    response = session.request(method, url, params, data)
    response.raise_for_status()
    parsed = response.json()
    if "error" in parsed:
        print(f"[{parsed['error']['code']}] {parsed['error']['info']}", file=sys.stderr)
        sys.exit(1)
    return parsed

def edit_page(session: Session,
              url: str,
              page: str,
              text: str,
              summary: str,
              edit_token: str,
              assert_bot: Optional[str] = None):
    edit_params = {"action": "edit", "title": page}
    md5 = hashlib.md5()
    md5.update(text.encode("utf-8"))
    edit_data = {"bot": 1,
                 "nocreate": 1,
                 "text": text,
                 "summary": summary,
                 "md5": md5.hexdigest(),
                 "token": edit_token}
    return wiki_api(session, url, edit_params, edit_data, assert_bot=assert_bot)

if __name__ == "__main__":
    file = Path(__file__).parent / "src" / "defaultsettings.yml"
    Conf.load_metadata(file)
    # make sure we always print a literal null when dumping None values
    RoundTripRepresenter.add_representer(type(None), SafeRepresenter.represent_none)
    # emit an empty string if the default is undefined
    RoundTripRepresenter.add_representer(Undefined, lambda r, d: r.represent_scalar("tag:yaml.org,2002:null", ""))
    # omit !!omap tag from our OrderedDict dumps; we use ordering just to make things alphabetical
    RoundTripRepresenter.add_representer(OrderedDict, SafeRepresenter.represent_dict)
    if len(sys.argv) < 2 or sys.argv[1] == "-h" or sys.argv[1] == "--help":
        print("Manual usage: gendoc.py config|roles|gamemodes")
        print("CI usage: gendoc.py <API-url> <username> <password> <git-commit-sha>")
        sys.exit(1)
    elif len(sys.argv) < 5:
        print(generate_docs(sys.argv[1]))
    else:
        # if passing arguments:
        # the first argument should be the URL to the wiki's api.php (e.g. 'https://werewolf.chat/w/api.php')
        # the second argument should be the username to authenticate with
        # the third argument should be the password to authenticate with
        # the fourth argument should be the id (hash) of the git commit that prompted this script to run
        api, username, password, commit = sys.argv[1:]
        with Session() as s:
            token_params = {"action": "query", "meta": "tokens", "type": "login"}
            login_token = wiki_api(s, api, token_params)["query"]["tokens"]["logintoken"]
            login_data = {"lgname": username, "lgpassword": password, "lgtoken": login_token}
            login_result = wiki_api(s, api, {"action": "login"}, login_data)
            if login_result["login"]["result"] == "Failed":
                print(f"[loginfailed] {login_result['login']['reason']}")
                sys.exit(1)
            username = login_result["login"]["lgusername"]
            token_params["type"] = "csrf"
            csrf_token = wiki_api(s, api, token_params, assert_bot=username)["query"]["tokens"]["csrftoken"]

            print("Updating Configuration page...")
            print(edit_page(s, api, "Configuration", generate_docs("config"),
                            f"Configuration update from [[git:{commit}]]", csrf_token, assert_bot=username))

            print("Updating Roles page...")
            print(edit_page(s, api, "Module:Roles/data.json", generate_docs("roles"),
                            f"Role data update from [[git:{commit}]]", csrf_token, assert_bot=username))

            print("Updating Game modes page...")
            print(edit_page(s, api, "Module:Gamemodes/data.json", generate_docs("gamemodes"),
                            f"Game mode data update from [[git:{commit}]]", csrf_token, assert_bot=username))
