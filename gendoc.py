from collections import OrderedDict
from io import StringIO
from pathlib import Path
from ruamel.yaml import YAML, RoundTripRepresenter, SafeRepresenter

from src.config import Config, Empty, merge

class Undefined:
    pass

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
    elif t in ("int", "float", "enum"):
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

def generate_docs():
    file = Path(__file__).parent / "src" / "defaultsettings.yml"
    Conf.load_metadata(file)
    # Initialize markup with our intro (as a template so we can easily edit it without needing to push code changes)
    markup = "{{config intro}}\n"
    # Add in the root
    markup += add_section(Conf.metadata)
    # Add the rest of the sections in alphabetical order
    sorted_keys = sorted([x for x in Conf.metadata.keys() if x[0] != "_"])
    for key in sorted_keys:
        markup += add_section(Conf.metadata[key])
    return markup

if __name__ == "__main__":
    # make sure we always print a literal null when dumping None values
    RoundTripRepresenter.add_representer(type(None), SafeRepresenter.represent_none)
    # emit an empty string if the default is undefined
    RoundTripRepresenter.add_representer(Undefined, lambda r, d: r.represent_scalar("tag:yaml.org,2002:null", ""))
    # omit !!omap tag from our OrderedDict dumps; we use ordering just to make things alphabetical
    RoundTripRepresenter.add_representer(OrderedDict, SafeRepresenter.represent_dict)
    print(generate_docs())
