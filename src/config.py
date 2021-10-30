from __future__ import annotations

import copy
from pathlib import Path
import os
import sys
from typing import Optional, Any
from ruamel.yaml import YAML

__all__ = ["Main", "Config", "Empty", "merge", "init"]

# Empty is meant to be used as a singleton, so EmptyType is *not* in __all__
class EmptyType:
    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self

Empty = EmptyType()

class InvalidConfigValue(ValueError):
    pass

def init():
    bp = Path(__file__).parent
    Main.load_metadata(bp / "defaultsettings.yml")

    p = bp.parent / "botconfig.yml"
    if p.is_file():
        Main.load_config(bp.parent / "botconfig.yml")

    if os.environ.get("BOTCONFIG", False):
        cp = Path(os.environ["BOTCONFIG"])
        if not cp.is_file():
            print("BOTCONFIG environment variable does not point to a valid file", file=sys.stderr)
            sys.exit(1)
        Main.load_config(cp)

    if os.environ.get("DEBUG", False):
        Main.set("debug.enabled", True)
        logs = Main.get("logging.logs")
        for i, log in enumerate(logs):
            if log["group"] == "main":
                Main.set("logging.logs[{}].level".format(i), "debug")
        dp = bp.parent / "botconfig.debug.yml"
        if dp.is_file():
            Main.load_config(dp)

class Config:
    def __init__(self):
        self._metadata: Optional[dict[str, Any]] = None
        self._metadata_file: Optional[str | Path] = None
        self._settings: Any = Empty
        self._files: list[str | Path] = []

    def load_metadata(self, file: str | Path) -> None:
        """Load metadata into the current Config instance.

        :param file: Path to metadata file to load
        :raises AssertionError: If metadata has already been loaded
        """
        assert self._metadata is None
        self._metadata_file = file
        y = YAML()
        with open(file, "rt") as f:
            self._metadata = y.load(f)
        # load default settings
        self._settings = merge(self._metadata, Empty, Empty, "<root>")

    def load_config(self, file: str | Path) -> None:
        """Load configuration file into the current Config instance.
        
        :param file: Path to configuration file to load
        :raises RuntimeError: If the configuration file has already been loaded
        :raises AssertionError: If metadata has not yet been loaded
        :raises TypeError: If the configuration file is invalid according to metadata
        """
        assert self._metadata is not None
        if file in self._files:
            raise RuntimeError("the specified configuration file has already been loaded for this Config instance")

        self._files.append(file)
        y = YAML()
        with open(file) as f:
            config = y.load(f)
            self._settings = merge(self._metadata, self._settings, config, "<root>")

    def reload(self, refresh_metadata=False):
        """Reload configuration files to pick up any changes.
        
        If the new configuration would error, the configuration is unmodified.
        
        :param refresh_metadata: If True, reload the metadata file.
            If False, keep the current set of metadata.
        :raises TypeError: If any of the configuration files are invalid
        :raises AssertionError: If no metadata has been loaded yet
        """
        assert self._metadata is not None
        new_config = Config()
        if refresh_metadata:
            self.load_metadata(self._metadata_file)
        else:
            new_config._metadata = self._metadata
            new_config._metadata_file = self._metadata_file

        for file in self._files:
            new_config.load_config(file)

        self._metadata = new_config._metadata
        self._settings = new_config._settings

    def _resolve_key(self, key: str) -> tuple[Any, dict[str, Any]]:
        parts = key.split(".")
        cur = self._settings
        meta = self._metadata
        for part in parts:
            if "[" in part:
                key_part, idx_part = part.split("[", maxsplit=1)
                idx_part = int(idx_part[:-1])  # strip trailing "]"
            else:
                key_part = part
                idx_part = None
            if key_part not in cur:
                raise KeyError("configuration key not found: {}".format(key))
            cur = cur[key_part]
            meta = meta["_default"][key_part]
            meta_type = meta["_type"]
            if idx_part is not None:
                if idx_part >= len(cur):
                    raise KeyError("configuration key not found: {}".format(key))
                cur = cur[idx_part]
                meta = meta["_items"]
                meta_type = meta["_type"]
            if isinstance(meta_type, dict):
                # complex meta_type, obtain the actual type metadata
                meta = meta["_type"]
                meta_type = meta["_type"]
            if isinstance(meta_type, list) and isinstance(cur, dict):
                # union type and cur is a complex type; determine exactly which type it is
                # a union can contain at most one untagged complex type
                if "type" in cur:
                    # cur is tagged, handle that below
                    meta_type = "tagged"
                else:
                    # take the first untagged type in the list and use that
                    untagged = [t for t in meta_type if isinstance(t, dict)]
                    # this assert may be better off in merge() to enforce that a union
                    # has at most one untagged complex type
                    assert len(untagged) == 1
                    meta = untagged[0]
                    meta_type = meta["_type"]
            if meta_type == "tagged":
                new_meta = copy.deepcopy(meta["_tags"][cur["type"]])
                new_meta["_default"]["type"] = {"_type": "enum", "_values": list(meta["_tags"].keys())}
                meta = new_meta

        return cur, meta

    def get(self, key: str, default=Empty):
        """Get the value of a configuration item.
        
        In general, values retrieved should not be cached,
        but can be passed into other functions for dependency injection.
        Caching values can lead to inconsistencies in the event the configuration
        files are reloaded during runtime.

        A copy of the value is returned, so it is safe for the caller to mutate without
        impacting any other call sites.
        
        :param key: Configuration key to load, using dots to separate object
            keys and index syntax to retrieve particular elements of lists.
            Ex: foo.bar[0].baz
        :param default: If the configuration key is not found, this is the returned value.
            If set to config.Empty (the default), a KeyError is raised if the key is not found.
            Generally this should only ever be set for backwards compatibility purposes.
        :returns: The value of the configuration key, or the default value if one
            was specified.
        :raises KeyError: If default is not specified and the key is not found.
        :raises AssertionError: If called before configuration is initialized.
        """
        assert self._settings is not Empty
        try:
            cur, _ = self._resolve_key(key)
        except KeyError:
            if default is not Empty:
                return default
            raise

        # return a copy so that the caller cannot mutate our actual settings
        # this lets them mutate the returned value to serve their own purposes without needing to worry
        # about causing issues with other call sites that need the setting
        return copy.deepcopy(cur)

    def set(self, key: str, value, merge_strategy: Optional[str] = None) -> None:
        """Modify a single config key.

        These changes are not persistent and will be lost if the configuration
        is reloaded.

        :param key: Configuration key to set, using dots to separate object
            keys and index syntax to retrieve particular elements of lists.
            Ex: foo.bar[0].baz
        :param value: Value to set, must be of the correct type
        :param merge_strategy: How to set the value. The allowed merge strategies
            vary based on the type of value being set. If none, uses the configured
            merge strategy from the metadata.
        :raises KeyError: If the configuration key does not exist.
        :raises TypeError: If the value is of the incorrect type.
        :raises AssertionError: If called before configuration is initialized.
        """
        assert self._settings is not Empty
        cur, meta = self._resolve_key(key)
        parts = key.split(".")
        new = merge(meta, cur, value, *parts, strategy_override=merge_strategy)
        cur = self._settings
        for i, part in enumerate(parts):
            set_value = i == len(parts) - 1
            if "[" in part:
                key_part, idx_part = part.split("[", maxsplit=1)
                idx_part = int(idx_part[:-1])  # strip trailing "]"
            else:
                key_part = part
                idx_part = None
            if idx_part is not None:
                cur = cur[key_part]
                if set_value:
                    cur[idx_part] = new
                cur = cur[idx_part]
            else:
                if set_value:
                    cur[key_part] = new
                cur = cur[key_part]

    @property
    def metadata(self):
        return self._metadata


Main = Config()

def merge(metadata: dict[str, Any], base, settings, *path: str,
          type_override: Optional[str] = None,
          strategy_override: Optional[str] = None,
          tagged: bool = False) -> Any:
    """Merge settings into a base settings object.

    This calls itself recursively and does not mutate any passed-in objects.

    :param metadata: Typing metadata for current merge
    :param base: Current value to merge with, or Empty if no current value
    :param settings: Settings value to merge into base, without any metadata
    :param path: Path from the root for the current object being merged, for error messages
    :param type_override: Override the type from metadata. For internal use only.
    :param strategy_override: Override the merge strategy from metadata. For internal use only.
    :param tagged: If true, we expect a "type" key to exist in settings. For internal use only.
    :returns: Merged settings object
    :raises TypeError: If settings is of an incorrect type
    :raises AssertionError: If metadata is ill-formed
    """
    if not path:
        path = ["<root>"]

    settings_type = metadata["_type"]
    assert settings_type is not None
    if type_override is not None:
        settings_type = type_override

    merge_type = metadata.get("_merge", None)
    if strategy_override is not None:
        merge_type = strategy_override

    nullable = metadata.get("_nullable", False)
    if nullable:
        if settings is None:
            return settings
        elif settings is Empty and base is not Empty:
            return base
        elif settings is Empty and base is Empty:
            if "_default" not in metadata:
                raise TypeError("Value for path '{}' is required".format(".".join(path)))
            return metadata["_default"]

    ctors = metadata.get("_ctors", [])
    if ctors:
        assert settings_type == "dict" and "_default" in metadata
    if ctors and not isinstance(settings, dict):
        for ctor in ctors:
            # if a constructor fits our current data type, we'll merge that
            # into the default object and return it
            set_metadata = metadata["_default"][ctor["_set"]]
            assert ctor["_type"] == set_metadata["_type"]
            try:
                value = {ctor["_set"]: merge(set_metadata, Empty, settings, *path, ctor["_set"])}
                return merge(metadata, base, value, *path, strategy_override="replace")
            except TypeError:
                continue

    if settings_type == "str":
        if settings is not Empty and not isinstance(settings, str):
            raise TypeError("Expected type str for path '{}', got {} instead".format(".".join(path), type(settings)))
        # str only supports one merge type: replace
        if merge_type is None:
            merge_type = "replace"
        assert merge_type in ("replace",)

        if settings is not Empty:
            return settings
        elif base is not Empty:
            return base
        elif "_default" not in metadata:
            raise TypeError("Value for path '{}' is required".format(".".join(path)))
        else:
            return metadata["_default"]

    elif settings_type == "int":
        # bool is a subclass of int, so needs special handling
        if settings is not Empty and (not isinstance(settings, int) or isinstance(settings, bool)):
            raise TypeError("Expected type int for path '{}', got {} instead".format(".".join(path), type(settings)))
        # int supports three merge types: replace (default), max, min
        if merge_type is None:
            merge_type = "replace"
        assert merge_type in ("replace", "max", "min")

        if settings is not Empty:
            value = settings
        elif base is not Empty:
            value = base
        elif "_default" not in metadata:
            raise TypeError("Value for path '{}' is required".format(".".join(path)))
        else:
            value = metadata["_default"]

        if merge_type == "replace":
            return value
        elif merge_type == "max":
            if isinstance(metadata["_default"], int):
                value = max(value, metadata["_default"])
            if isinstance(base, int):
                value = max(value, base)
            return value
        elif merge_type == "min":
            if isinstance(metadata["_default"], int):
                value = min(value, metadata["_default"])
            if isinstance(base, int):
                value = min(value, base)
            return value

    elif settings_type == "bool":
        if settings is not Empty and not isinstance(settings, bool):
            raise TypeError("Expected type bool for path '{}', got {} instead".format(".".join(path), type(settings)))
        # bool supports three merge types: replace (default), and, or
        if merge_type is None:
            merge_type = "replace"
        assert merge_type in ("replace", "and", "or")

        if settings is not Empty:
            value = settings
        elif base is not Empty:
            value = base
        elif "_default" not in metadata:
            raise TypeError("Value for path '{}' is required".format(".".join(path)))
        else:
            value = metadata["_default"]

        if merge_type == "replace":
            return value
        elif merge_type == "and":
            if isinstance(metadata["_default"], bool):
                value = value and metadata["_default"]
            if isinstance(base, bool):
                value = value and base
            return value
        elif merge_type == "or":
            if isinstance(metadata["_default"], bool):
                value = value or metadata["_default"]
            if isinstance(base, bool):
                value = value or base
            return value

    elif settings_type == "float":
        if settings is not Empty and not isinstance(settings, float):
            raise TypeError("Expected type float for path '{}', got {} instead".format(".".join(path), type(settings)))
        # float supports three merge types: replace (default), max, min
        if merge_type is None:
            merge_type = "replace"
        assert merge_type in ("replace", "max", "min")

        if settings is not Empty:
            value = settings
        elif base is not Empty:
            value = base
        elif "_default" not in metadata:
            raise TypeError("Value for path '{}' is required".format(".".join(path)))
        else:
            value = metadata["_default"]

        if merge_type == "replace":
            return value
        elif merge_type == "max":
            if isinstance(metadata["_default"], float):
                value = max(value, metadata["_default"])
            if isinstance(base, float):
                value = max(value, base)
            return value
        elif merge_type == "min":
            if isinstance(metadata["_default"], float):
                value = min(value, metadata["_default"])
            if isinstance(base, float):
                value = min(value, base)
            return value

    elif settings_type == "enum":
        if settings is not Empty and not isinstance(settings, str):
            raise TypeError("Expected type str for path '{}', got {} instead".format(".".join(path), type(settings)))
        # need to know valid enum values
        assert "_values" in metadata
        if settings is not Empty and settings not in metadata["_values"]:
            raise TypeError("Enum value {} for path '{}' is not valid".format(settings, ".".join(path)))
        # enum supports one merge type: replace
        if merge_type is None:
            merge_type = "replace"
        assert merge_type in ("replace",)

        if settings is not Empty:
            return settings
        elif base is not Empty:
            return base
        elif "_default" not in metadata:
            raise TypeError("Value for path '{}' is required".format(".".join(path)))
        else:
            return metadata["_default"]

    elif settings_type == "list":
        if settings is not Empty and not isinstance(settings, list):
            raise TypeError("Expected type list for path '{}', got {} instead".format(".".join(path), type(settings)))
        # need to know what type of items we can have in the list
        assert "_items" in metadata

        if settings is Empty and base is Empty and "_default" not in metadata:
            raise TypeError("Value for path '{}' is required".format(".".join(path)))

        # validate that each item in the list is of the correct type
        settings_values = []
        if settings is not Empty:
            for i, item in enumerate(settings):
                munged = list(path[:-1])
                munged.append("{}[{}]".format(path[-1], i))
                settings_values.append(merge(metadata["_items"], Empty, item, *munged))

        base_values = []
        if isinstance(base, list):
            for i, item in enumerate(base):
                munged = list(path)
                munged.append("<base>[{}]".format(i))
                base_values.append(merge(metadata["_items"], Empty, item, *munged))

        default_values = []
        if isinstance(metadata["_default"], list):
            for i, item in enumerate(metadata["_default"]):
                munged = list(path)
                munged.append("<default>[{}]".format(i))
                default_values.append(merge(metadata["_items"], Empty, item, *munged))

        # list supports two merge types: append (default), replace
        if merge_type is None:
            merge_type = "append"
        assert merge_type in ("append", "replace")

        if merge_type == "append":
            values = []
            if isinstance(base, list):
                values.extend(base_values)
            else:
                values.extend(default_values)
            values.extend(settings_values)
            return values
        elif merge_type == "replace":
            if settings is not Empty:
                return settings_values
            elif base is not Empty:
                if isinstance(base, list):
                    return base_values
                else:
                    return base
            else:
                if isinstance(metadata["_default"], list):
                    return default_values
                else:
                    return metadata["_default"]

    elif settings_type == "dict":
        if settings is not Empty and not isinstance(settings, dict):
            raise TypeError("Expected type dict for path '{}', got {} instead".format(".".join(path), type(settings)))
        # need to know what keys are valid in the dict
        assert "_default" in metadata and isinstance(metadata["_default"], dict)

        if settings is not Empty:
            extra = list(settings.keys() - metadata["_default"].keys())
            if tagged and "type" in extra:
                extra.remove("type")
            if extra and not metadata.get("_extra", False):
                raise TypeError("Value on path '{}' has unrecognized key {}".format(".".join(path), extra[0]))

        # dict supports two merge types: merge (default), replace
        if merge_type is None:
            merge_type = "merge"
        assert merge_type in ("merge", "replace")

        value = {}
        if tagged:
            value["type"] = settings["type"]

        for key, item_metadata in metadata["_default"].items():
            if isinstance(base, dict) and (merge_type == "merge" or settings is Empty):
                base_value = base.get(key, Empty)
            else:
                base_value = Empty
            if settings is Empty:
                settings_value = Empty
            else:
                settings_value = settings.get(key, Empty)
            value[key] = merge(item_metadata, base_value, settings_value, *path, key)
        return value

    elif settings_type == "tagged":
        # dict with a type key that indicates the type of dict
        if settings is not Empty and not isinstance(settings, dict):
            raise TypeError("Expected type dict for path '{}', got {} instead".format(".".join(path), type(settings)))
        assert "_tags" in metadata
        # non-nullable tagged types don't have a default; nullable default already handled above
        if settings is Empty and base is Empty:
            raise TypeError("Value for path '{}' is required".format(".".join(path)))
        elif settings is Empty:
            return base

        if "type" not in settings:
            raise TypeError("Value on path '{}' is missing required key type".format(".".join(path)))
        tagged_type = settings["type"]
        if tagged_type not in metadata["_tags"]:
            raise TypeError("Value on path '{}' has unrecognized type {}".format(".".join(path), tagged_type))
        return merge(metadata["_tags"][tagged_type], base, settings, *path, tagged=True)

    elif isinstance(settings_type, dict):
        # complex type
        return merge(settings_type, base, settings, *path, tagged=tagged)

    elif isinstance(settings_type, list):
        # union type
        e1 = None
        for t in settings_type:
            assert t is not None
            try:
                return merge(metadata, base, settings, *path, type_override=t)
            except TypeError as e2:
                e2.__cause__ = e1
                e1 = e2
        else:
            raise TypeError(("None of the candidate types for path '{}' matched actual type {}.".format(".".join(path), type(settings))
                             + " See inner exceptions for more details on each candidate tried.")) from e1

    else:
        assert False, "Unknown settings type {}".format(settings_type)
