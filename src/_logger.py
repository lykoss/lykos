__license__ = """
Copyright (c) 2015, Emanuel Barry
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:

* Redistributions of source code must retain the above copyright
  notice, this list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright
  notice, this list of conditions and the following disclaimer in the
  documentation and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

__author__ = "Emanuel 'Vgr' Barry"
__version__ = "0.1"

__doc__ = """Improved Logger module

This is an advanced logger module for various purposes. This is
intended as a third-party library for software dealing with a general
userbase, where there is a need to log what the program does, or even
simply as a general logger to note down what the program did at some
point, errors that occurred and so on.

This module exposes seven logging classes and one singleton.
They are described below.

Logger:
            Basic class to use for general logging purposes. See the
            Logger's documentation for a list and explanation of each
            argument. This class defines the following methods:

            logger:
                        Basic logger, used for writing and printing to
                        screen based on settings defined on call,
                        defaulting to the class' default (defined when
                        instantiating).

            multiple:
                        Small wrapper around the logger method, used to
                        write to more than one file at a time. The
                        types given have to be an iterable, and passing
                        '*' means to write to all possible files.

            show:
                        Small wrapper around the logger method, used
                        solely to not write to any file. This is a
                        shortcut of having to do write=False on many
                        calls.

            docstring: 
                        Wrapper around the logger method, used to print
                        documentation strings. It handles tabs and
                        spaces in a proper manner.

Translater:
            Advanced class used to translate lines matching a certain
            pattern, by replacing the line by the one found under the
            module or modules given, through some lookup rules. These
            rules can be viewed by accessing the Translater's
            documentation itself. It defines the following methods:

            translate:
                        A method used to translate the output using the
                        corresponding lines, and then formatting the
                        resulting output using the provided formatting
                        options. This method operates through side
                        effect, which means it directly alters the
                        output, and returns None. For a more detailed
                        explanation, see the Translater class'
                        documentation.

            logger:
                        Wrapper around the Logger's logger method,
                        which will translate the lines using the
                        aforementioned translate method, then call
                        super().logger to do the logging operations.

LevelLogger:
            Light wrapper around the Logger class, which uses integers
            to determine if a line should be logger. This supports the
            "level" argument for the bypassers. It has the exact same
            methods as the Logger class, but the logger method is
            tweaked to care about level.

            logger:
                        Wrapper around Logger's logger method, which
                        accepts only one more positional argument,
                        level, and must be an integer or None. If
                        undefined or None, it will log no matter
                        what.

TranslatedLevelLogger:
            Wrapper around LevelLogger and Translater, in that order.
            It is highly recommended to use named parameters instead of
            positional ones, to ensure the parameters are passed to
            the correct arguments.

NamedLevelsLogger:
            Wrapper around LevelLogger, to support named levels.

TranslatedNamedLevelsLogger:
            Used to translate lines with named levels.

NoValue:
            This is the sole instance of the class with the same name.
            It has no value other than its string representation,
            'NoValue', and its always False boolean value. This is used
            with the Bypassers through the Logger class. A default
            bypasser setting has NoValue assigned to both the module
            and attribute. This is used when checking for settings to
            bypass; if either is NoValue, then no bypassing will occur.
            It's not possible to assign or re-assign NoValue to any
            setting. Rather, passing NoValue will tell the Bypassers to
            use the already-stored value. The Bypassers will never
            return this (lack of) value.

            NoValue is a singleton in the meaning that there is one,
            and only one, instance of it. type(NoValue)() effectively
            yields the same singleton. It is identical to None in all
            regards except for the fact that NoValue can be re-assigned
            to, while None cannot, and type(NoValue) can be used as a
            based in subclassing. However, subclassing will still yield
            the same singleton.

The BaseLogger class can be used to make custom classes, useful for
multiple inheritence. It defines a few private methods, that should
only be ever used by itself or its subclasses, and not from outside.

------------

To use this module, you will need to write a small wrapper around it.
An example of such a wrapper can be found below. See each of the
individual classes' documentation for more detailed explanation on each
of the different parameters.

myLogger = Logger(ts_format="Fake timestamp here",
                  logfiles={"hello": "world"})

logged = myLogger.logger("hello there!", type="hello")

This will print "hello there!" to the screen, and write the following
to the file "world":

Fake timestamp here hello there!

The 'logged' variable will hold the "hello there!" string

That was simple enough. Now let's say we want it to write to the file
only if the value assigned to the key "foo" in the mapping "bar"
evaluates to True. We'll do it like this:

bar = {"foo": False}

myLogger = Logger(bypassers=[("write", set(), {(bar, "foo")},
                                                None, True)])

The syntax for the bypassers may seem slightly complicated when first
looking at it, but it's actually easy once you learn how to use it. The
documentation for how to use this parameter can be found under the
Logger's documentation.

myLogger.logger("hello there!", type="hello", write=False)

This call will check for any possible bypasses. However, the value of
bar["foo"] is False, therefore, no bypassing happens. It will print to
screen, but the result will not be written to a file. Remember that we
passed the 'bar' dict in one of the parameters? Let's alter it now.

bar["foo"] = True

myLogger.logger("hello there!", type="hello", write=False)

Now, however, the value of bar["foo"] is True, and the bypassing
happens. It again prints to screen, but this time it will also write to
the file named "world".

There is currently no way to make the bypassers look to see if a
certain variable is of a certain value, it will only care about its
boolean value, True or False. To check for specific values, you will
need to write a wrapper around it and make it toggle another value
between True and False.

Now, let's take it a step further. Let's say you deal with a larger
userbase, and you need to have some lines automatically translated in
the user's language, which may or may not be the language your program
was programmed in. You will need to use the Translater class for that.
The lines that will need to be translated need to match a regex
pattern. It can be customized to fit your needs, and defaults to
UNDERSCORED_UPPERCASE names.

translaterDict = {"English": {"LINE1": "This is the first line.",
                              "LINE2": "This is the {0} line.",
                              "LINE3": "This is the {pos} line.",
                              "LINE4": "This is the %s line.",
                              "LINE5": "{0} is {t} %s line.",
                              "LINE6": "They can even {0}!"}}

myTranslater = Translater(all_languages={"English": "en"},
                          main="English",
                          module=translaterDict)

myTranslater.logger("LINE1")

Will print "This is the first line." to the screen

myTranslater.logger("LINE2", format=["second"])

Will result in "This is the second line."

myTranslater.logger("LINE3", format_dict={"pos": "third"})

Will output "This is the third line."

myTranslater.logger("LINE4", format_mod=["fourth"])

Will output "This is the fourth line."

myTranslater.logger("LINE5", format=["This"], format_dict={"t": "the"},
                             format_mod=["fifth"])

Will print "This is the fifth line."

myTranslater.logger("LINE6", format=["be %s"], format_mod=["combined"])

Will result in "They can even be combined!"

Refer to the Translater documentation for more in-depth documentation
on the Translater class.

-----------

All classes' instantiation arguments must be explicitely named, as
multiple inheritence would make the ordering confusing and inconsistent
between the various classes. Every class passes the keyword arguments
it cannot get to the superclass' __init__ method, up to the 'object'
class itself, which expects no arguments. It is the end user's
responsibility to make sure that all arguments will be consumed by the
time it reaches object.
"""

__all__ = ["BaseLogger", "Logger", "Translater", "LevelLogger",
           "TranslatedLevelLogger", "NamedLevelsLogger",
           "TranslatedNamedLevelsLogger", "NoValue"]

from datetime import datetime
import random
import shutil
import time
import sys
import re

class MetaNoValue(type):
    """Metaclass responsible for ensuring uniqueness."""

    def __new__(meta, cls, bases, clsdict):
        """Ensure there is one (and only one) NoValue singleton."""
        if "_novalue" not in sys.modules:
            nv = super().__new__(meta, cls, bases, clsdict)()
            nv.__class__.__new__ = lambda cls: nv
            sys.modules["_novalue"] = nv
            return nv
        return NoValue

class NoValue(sys.__class__, metaclass=MetaNoValue):
    """Express the lack of value, as None has a special meaning."""

    def __init__(self):
        """Instantiate the module with the class' name."""
        cls = self.__class__
        super(cls, self).__init__(cls.__name__, cls.__doc__)

    def __repr__(self):
        """Return the explicit NoValue string."""
        return 'NoValue'

    def __bool__(self):
        """Return False no matter what."""
        return False

    def __lt__(self, other):
        """NoValue will always be last when ordering."""
        return False

    def __le__(self, other):
        """Will only be True if self is other."""
        return self is other

    def __gt__(self, other):
        """Will be True if self is not other."""
        return self is not other

    def __ge__(self, other):
        """Will always be greater or equal than anything else."""
        return True

    def __eq__(self, other):
        """Return True if self is other."""
        return self is other

    def __ne__(self, other):
        """Return True if self is not other."""
        return self is not other

class RunnerIterator:
    """Generate an iterator of sorted items.

    This iterator runs over all the items of the given items, sorted in
    alphabetical order. It will raise RuntimeError if the items are
    changed during iteration.
    """

    def __init__(self, items):
        """Create a new iterator."""
        self.items = items
        self.original = items
        if hasattr(items, "copy"):
            self.original = items.copy()
        self.forced = list(items)
        self.items_ = sorted(items)
        self.index_ = len(items) + 1

    def __iter__(self):
        """Return the iterator."""
        return self

    def __next__(self):
        """Return the items of self."""
        if self.index_ == 1:
            raise StopIteration

        if self.items != self.original or self.forced != list(self.items):
            raise RuntimeError("container changed size during iteration")

        self.index_ -= 1

        return self.items_[-self.index_]

class Container:
    """Base container class for various purposes."""

    def __init__(self, items):
        """Create a new items set."""
        self._items = items

    def __iter__(self):
        """Return an iterator over the items of self."""
        return RunnerIterator(self._items)

    def __len__(self):
        """Return the amount of items in self."""
        return len(self._items)

    def __contains__(self, item):
        """Return True if item is in self."""
        return item in self._items

    def __repr__(self):
        """Return a string of all items."""
        return "%s(%s)" % (self.__class__.__name__,
               ", ".join(repr(item) for item in self))

    def __dir__(self):
        """Return a list of all methods."""
        return dir(self.__class__) + list(x for x in self.__dict__
                                   if x[0] != "_" or x[:2] == x[-2:] == "__")

    def __eq__(self, other):
        """Return self == other."""
        try:
            if self._items == other._items:
                return True
            if set(self._items) == set(other):
                return True
        except Exception:
            return False
        return False

    def __ne__(self, other):
        """Return self != other."""
        return not self.__eq__(other)

class BaseMapping(Container):
    """Lightweight class for inner iteration."""

    def __add__(self, items):
        """Return a new iterable with all items."""
        new = self._items.copy()
        new.update(items)
        return self.__class__(new)

    __radd__ = __add__ # same thing

    def __iadd__(self, items):
        """Update and return self with items."""
        self._items.update(items)
        return self._items

    def __lt__(self, other):
        """Return self < other."""
        return sorted(self._items) < sorted(other)

    def __le__(self, other):
        """Return self <= other."""
        return sorted(self._items) <= sorted(other)

    def __gt__(self, other):
        """Return self > other."""
        return sorted(self._items) > sorted(other)

    def __ge__(self, other):
        """Return self >= other."""
        return sorted(self._items) >= sorted(other)

    def __getattr__(self, attr):
        """Delegate an attribute not found to the items set."""
        return getattr(self._items, attr)

_mps = []

for _sub in ("Types", "Pairs"):
    _mp_doc = """Subclass for the %s argument.""" % _sub.lower()
    _mps.append(type(_sub + "Mapping", (BaseMapping,), {'__doc__': _mp_doc}))

class Viewer(Container):
    """Viewer object for the Bypassers mapping."""

    def __init__(self, self_):
        """Create a new viewer handler."""
        self.self = self_
        self._items = self_._items

    def __getitem__(self, index_):
        """Return the matching value."""
        return sorted(self._items)[index_]

    def __repr__(self):
        """Return a representation of self."""
        return "%s(%s)" % (self.self.__class__.__name__,
               ", ".join(repr(item) for item in sorted(self)))

class BaseViewer:
    """Base viewer class for the Bypassers mapping."""

    def __init__(self, self_):
        """Create a new view object."""
        self.self = self_
        self._items = []
        self._viewer = Viewer(self)

    def __getitem__(self, index_):
        """Return the item at the index given."""
        return self._items[index_]

    def __setitem__(self, index_, item):
        """Assign the item at the index given."""
        self._items[index_] = item

    def __delitem__(self, index_):
        """Remove the item at the index given."""
        del self._items[index_]

    def __dir__(self):
        """Return a list of all methods."""
        return dir(self.__class__)

    def __repr__(self):
        """Return a representation of the viewer."""
        return "<%s view object of the %s object at 0x%X>" % (
               self.__class__.__name__,
               self.self.__class__.__name__,
               id(self.self))

    def __call__(self):
        """Return the view object."""
        return self._viewer

    def __getattr__(self, attr):
        """Delegate any attribute not found to the inner list."""
        return getattr(self._items, attr)

def make_sub(name):
    """Generate view objects."""
    subs = []
    for sub in ("Keys", "Types", "Pairs", "Attributes", "Values", "Items"):
        doc = """Return all the %s of the %s class.""" % (sub.lower(), name)
        subs.append(type(name + sub, (BaseViewer,), {'__doc__': doc}))
    return subs

class Bypassers(Container):
    """Special mapping used by the bypassers argument of Logger.

    This mapping is aimed at emulating a dictionnary, and as such has
    the same methods that a dictionnary has. However, due to the fact
    that this mapping takes exactly five arguments instead of the
    standard one or two, more methods were added, named after standard
    methods from other objects, such as sets and lists. This can be
    subclassed for more functionality.

    Functional API:

    Note: This API provides functionality to allow any of the five
    arguments to be read and modified. If you want to use this
    functional API yourself, you must first read this documentation,
    as some methods do not behave as you would expect them to due to
    the unique nature of this mapping.

    bypassers = Bypassers((setting, {types}, {pairs}, module, attr))

    bypassers[setting]
                                        Access the internal mapping

    del bypassers[setting]
                                        Remove the setting's bindings

    str(bypassers) | repr(bypassers)
                                        Show all the settings, types,
                                        pairs, modules and attributes
                                        that are currently active

    len(bypassers)
                                        Return the number of settings

    x in bypassers
                                        Return True if x is a setting,
                                        False otherwise

    for x in bypassers
                                        Iterate over all settings in
                                        alphabetical order

    bool(bypassers)
                                        Return True if at least one 
                                        setting is bound, False
                                        otherwise

    dir(bypassers)
                                        Return a list of all methods

    bypassers.extend(iterable)
                                        Add a new binding; need a
                                        five-tuple, ignored if setting
                                        exists

    bypassers.update(iterable)
                                        Update existing bindings with
                                        five-tuples or add new bindings

    bypassers.add(setting)
                                        Add new unbound settings,
                                        ignored for existing settings

    bypassers.pop(setting)
                                        Return the (types, pairs,
                                        module, attr) iterable bound to
                                        the setting and remove all the
                                        setting's bindings

    bypassers.popitem()
                                        Remove and return a random
                                        binding, five-tuple

    bypassers.get(setting, fallback)
                                        Return the (types, pairs,
                                        module, attr) iterable bound to
                                        the setting. If the setting
                                        does not exist, 'fallback' will
                                        be returned; defaults to None

    bypassers.setdefault(item, fb)
                                        Set the default fallback for
                                        setting 'item' to 'fb'; this
                                        only affects .get

    bypassers.count(iters)
                                        Return the number of settings
                                        which are set to use this
                                        (module, attr) pair

    bypassers.keys()
                                        Return all existing settings

    bypassers.values()
                                        Return all (types, pairs,
                                        module, attr) pairs

    bypassers.items()
                                        Return all existing bindings

    bypassers.types()
                                        Return all types

    bypassers.pairs()
                                        Return all pairs

    bypassers.read()
                                        Return all (module, attr) pairs

    bypassers.copy()
                                        Return a deep copy

    bypassers.clear()
                                        Remove all settings and their
                                        bindings

    Equality testing (== and !=) can be used to compare two different
    instances of the Bypassers mapping. If they have exactly the same
    mapping (same settings bound to the same types, pairs, module and
    attribute), both instances will be considered to be equal. This
    also works even if the other instance is not a Bypassers instance,
    provided they have a similar API. To check if two variables are the
    same instance, use 'is' instead.

    The view objects of this class are changeable. This means that they
    reflect any changes that happened to the mapping. It is also
    guaranteed that the view objects' items will be sorted.
    """

    def __init__(self, *names):
        """Create a new instance of the class."""
        self._fallbacks = {}
        self._names = ("keys", "types", "pairs", "read", "values", "items")
        self._mappers = make_sub(self.__class__.__name__)
        for i, name in enumerate(self._names):
            setattr(self, name, self._mappers[i](self))
        for name in names:
            new = (name,)
            if hasattr(name, "items"):
                new = name.items()
            for setting, types, pairs, module, attr in new:
                types = _mps[0](types)
                pairs = _mps[1](pairs)
                self.keys.append(setting)
                self.types.append(types)
                self.pairs.append(pairs)
                self.read.append((module, attr))
                self.values.append((types, pairs, module, attr))
                self.items.append((setting, types, pairs, module, attr))

    def __getitem__(self, item):
        """Return the internal mapping of the setting."""
        return self.values[self.keys.index(item)]

    def __setitem__(self, item, value):
        """Bind a setting to another setting's bindings."""
        cur = self[value]
        self.update((item, set(cur[0]), set(cur[1])) + cur[2:])

    def __delitem__(self, item):
        """Remove the setting and all its bindings."""
        index_ = self.keys.index(item)
        for name in self._names:
            del getattr(self, name)[index_]

    def __iter__(self):
        """Return an iterator over the items of self."""
        return RunnerIterator(self.keys())

    def __len__(self):
        """Return the total number of items, bound or otherwise."""
        return len(self.keys())

    def __contains__(self, item):
        """Return True if item is a setting, False otherwise."""
        return item in self.keys()

    def __bool__(self):
        """Return True if at least one setting is bound."""
        for mapping in (self.types, self.pairs):
            for inner in mapping():
                if inner:
                    return True
        return False

    def __repr__(self):
        """Return a string of all active attributes."""
        args = []
        for setting, types, pairs, module, attr in self.items():
            args.append("(setting=%r, types=%r, pairs=%r, module=%r, attr=%r)"
                       % (setting, types, pairs, module, attr))
        return '%s(%s)' % (self.__class__.__name__, " | ".join(args))

    def __eq__(self, other):
        """Return self == other."""
        try:
            return self.items() == other.items()
        except Exception:
            return False

    def update(self, *new):
        """Update the setting's bindings."""
        for name in new:
            item = (name,)
            if hasattr(name, "items"):
                item = name.items()
            for setting, types, pairs, module, attr in item:
                if setting in self.keys():
                    index_ = self.keys.index(setting)
                    self.types[index_].update(types)
                    self.pairs[index_].update(pairs)
                else:
                    index_ = len(self.keys())
                    types = _mps[0](types)
                    pairs = _mps[1](pairs)
                    self.keys.append(setting)
                    self.types.append(types)
                    self.pairs.append(pairs)
                    self.read.append((NoValue, NoValue))
                    self.values.append((types, pairs) + self.read[index_])
                    self.items.append((setting,) + self.values[index_])
                if module is NoValue:
                    module = self.read[index_][0]
                if attr is NoValue:
                    attr = self.read[index_][1]
                self.read[index_] = (module, attr)
                self.values[index_] = self.values[index_][:2] + (module, attr)
                self.items[index_] = self.items[index_][:3] + (module, attr)

    def extend(self, items):
        """Add a new binding from a five-tuple."""
        setting, types, pairs, module, attr = items
        if setting in self.keys():
            return
        types = _mps[0](types)
        pairs = _mps[1](pairs)
        self.keys.append(setting)
        self.types.append(types)
        self.pairs.append(pairs)
        self.read.append((module, attr))
        self.values.append((types, pairs, module, attr))
        self.items.append((setting, types, pairs, module, attr))

    def add(self, *settings):
        """Add new unbound settings. Ignored for existing settings."""
        for setting in settings:
            if setting in self.keys():
                continue
            types = _mps[0](set())
            pairs = _mps[1](set())
            self.keys.append(setting)
            self.types.append(types)
            self.pairs.append(pairs)
            self.read.append((NoValue, NoValue))
            self.values.append((types, pairs, NoValue, NoValue))
            self.items.append((setting, types, pairs, NoValue, NoValue))

    def pop(self, item):
        """Remove and return the bindings of setting."""
        index_ = self.keys.index(item)
        types, pairs, module, attr = self.values[index_]
        for name in self._names:
            del getattr(self, name)[index_]
        return (types, pairs, module, attr)

    def popitem(self):
        """Unbind and return all attributes of a random setting."""
        index_ = random.randrange(len(self.keys()))
        setting, types, pairs, module, attr = self.items[index_]
        for name in self._names:
            del getattr(self, name)[index_]
        return (setting, types, pairs, module, attr)

    def get(self, item, fallback=NoValue):
        """Return the settings' bindings or fallback."""
        if item not in self.keys():
            if item in self._fallbacks and fallback is NoValue:
                fallback = self._fallbacks[item]
            return None if fallback is NoValue else fallback
        types, pairs, module, attr = self.values[self.keys.index(item)]
        return (types, pairs, module, attr)

    def setdefault(self, item, fallback=NoValue):
        """Set the default fallback for the get() method."""
        self._fallbacks[item] = fallback
        if fallback is NoValue:
            del self._fallbacks[item]

    def count(self, iters):
        """Return the amount of (module, attr) pairs."""
        cnt = 0
        module, attr = iters
        for mod, att in self.read():
            if mod == module and att == attr:
                cnt += 1
        return cnt

    def copy(self):
        """Return a new instance with the same attributes."""
        new = []
        for setting, types, pairs, module, attr in self.items():
            new.append((setting, types.copy(), pairs.copy(), module, attr))
        return self.__class__(*new)

    def clear(self):
        """Remove all settings and their bindings."""
        for name in self._names:
            getattr(self, name).clear()

def pick(arg, default):
    return default if arg is None else arg

class BaseLogger:
    """Base Logger class for your everyday needs.

    This can be inherited to create custom classes.
    This is not user-faced. For general purposes, please use the Logger
    class. All arguments have a default value of None, and their stated
    default value is assigned after the call. This can be used to pass
    None for a parameter to ensure it always uses the correct default
    value, should it change. Subclasses defined in this module follow
    this rule, and any other class subclassing it should follow it too.
    It is also recommended that any method defined under such classes
    follow this rule, although it is not strongly enforced.

    sep:
                    String to be used to join the lines together.

        Default:    " "

    use_utc:
                    Boolean value to determine if the timestamps should
                    use Universal Coordinated Time or the local time.

        Default:    False

    ts_format:
                    Format string for timestamps. The parameters are
                    the same as the time module's 'strftime' function.
                    However, for the time zone name and offset, use
                    {tzname} and {tzoffset} respectively. This is done
                    to account for the use_utc parameter as well as
                    allow full cross-platformity (some platforms, such
                    as certain versions of Windows, fail to interpret
                    %z properly). The timezone name will be the
                    three-letters abbreviation of the timezone,
                    uppercased.. The time zone offset is a string with
                    + or - following by 4 digits, like +0000 or -0500,
                    the digits being HHMM.

        Default:    "[%Y-%m-%-d] (%H:%M:%S UTC{tzoffset})"

    print_ts:
                    Boolean value to determine whether the timestamps
                    should be printed to screen as well as to files.

        Default:    False

    """

    def __init__(self, *, sep=None, use_utc=None, ts_format=None,
                          print_ts=None, split=None, **kwargs):
        """Create a new base instance."""

        super().__init__(**kwargs)

        self.separator = pick(sep, " ")

        self.use_utc = pick(use_utc, False)
        self.print_ts = pick(print_ts, False)
        self.split = pick(split, True)

        # this can have {tzname} and {tzoffset} for formatting
        # this adds respectively a timezone in the format UTC or EST
        # and an offset from UTC in the form +0000 or -0500
        self.ts_format = ts_format or "[%Y-%m-%d] (%H:%M:%S UTC{tzoffset})"

    def __dir__(self):
        """Return a list of all non-private methods and attributes."""
        items = dir(self.__class__) + list(self.__dict__)
        for item in items[:]:
            if item[0] == "_" and not item[:2] == item[-2:] == "__":
                items.remove(item)
        return items

    def _get_timestamp(self, use_utc=None, ts_format=None):
        """Return a timestamp with timezone + offset from UTC."""
        use_utc = self.use_utc if use_utc is None else use_utc
        ts_format = self.ts_format if ts_format is None else ts_format

        if use_utc:
            tmf = datetime.utcnow().strftime(ts_format)
            tz = "UTC"
            offset = "+0000"
        else:
            tmf = time.strftime(ts_format)
            tz = time.tzname[0]
            offset = "+"
            if datetime.utcnow().hour > datetime.now().hour:
                offset = "-"
            offset += str(time.timezone // 36).zfill(4)
        return tmf.format(tzname=tz, tzoffset=offset).strip().upper() + " "

    def _split_lines(self, out):
        """Split long lines at clever points."""
        col = shutil.get_terminal_size()[0]
        lines = [line.rstrip(" ") for line in out.splitlines()]
        splines = [line.split(" ") for line in lines]
        newlines = [] # newline-separated lines
        for i, line in enumerate(lines):
            if len(line) <= col:
                newlines.append(line)
                continue
            newstr = ""
            for word in splines[i]:
                if newstr:
                    new = " ".join((newstr, word))
                else:
                    new = word
                if len(new) >= col and word != new:
                    newlines.append(newstr)
                    newstr = word
                elif len(new) >= col and word == new:
                    if newstr:
                        newlines.append(newstr)
                    newlines.append(new)
                    newstr = ""
                else:
                    newstr = new
            if newstr:
                newlines.append(newstr)
        return "\n".join(newlines)

    def _print(self, *output, sep=None, use_utc=None, ts_format=None,
                              print_ts=None, split=None):
        """Print to screen and remove all invalid characters."""

        sep = pick(sep, self.separator)

        output = self._get_output(output, sep)

        if pick(print_ts, self.print_ts):
            out = output.splitlines()
            ts = self._get_timestamp(use_utc, ts_format)
            for i, line in enumerate(out):
                out[i] = ts + line
            output = "\n".join(out)

        if pick(split, self.split):
            output = self._split_lines(output)

        with open(sys.stdout.fileno(), "w", errors="replace",
                  encoding="utf-8", closefd=False) as file:

            file.write(output + "\n")

            file.flush()

    def _get_output(self, out, sep, ret_list=False):
        """Sanitize output and join iterables together."""
        out = out or [''] # called with no argument, support it anyway
        msg = [] if ret_list else None
        for line in out:
            line = str(line)
            if msg is None:
                msg = line
            elif ret_list:
                msg.append(line)
            else:
                msg = sep.join((msg, line))
        return msg

def check_bypass(func):
    """Decorator for checking bypassability for the Logger class."""
    def inner(self, *output, type=None, file=None, **rest):
        if file is type is None:
            type = "normal"
        if type is None:
            for f, t in self.logfiles.items():
                if f == file:
                    type = t
                    break
            else:
                type = "normal"
        if file is None:
            file = self.logfiles.get(type, self.logfiles["normal"])
        self.bypassed = {} # reset the bypasses everytime
        def get_setting(module, attr, catch=False):
            if module is None:
                return attr
            try:
                value = getattr(module, attr)
            except AttributeError:
                try:
                    value = module[attr]
                except (TypeError, KeyError, IndexError):
                    if catch:
                        return False
                    raise
            return value

        for setting, types, pairs, module, attr in self.bypassers.items():
            if module is NoValue or attr is NoValue:
                continue
            for mod, att in pairs:
                if get_setting(mod, att, True):
                    self.bypassed[setting] = get_setting(module, attr)
                    break
            else:
                if type in types:
                    if get_setting(module, attr):
                        self.bypassed[setting] = get_setting(module, attr)

        return func(self, *output, type=type, file=file, **rest)

    return inner

class Logger(BaseLogger):
    """Main Logger class for general and specific logging purposes.

    This is inherited from the BaseLogger class.

    The options are the same as the base class, with these additions:

    display:
                    Default parameter to determine if the loggers
                    should print to screen. This can be overriden when
                    calling the method, on a per-line basis.

        Default:    True

    write:
                    Default parameter to determine if the loggers
                    should write to a file. This can be overriden when
                    calling the method, on a per-line basis.

        Default:    True

    logfiles:
                    Dictionary of {type:file} pairs. The type is the
                    logging type that the logger expects. The file is
                    the file that tells the logger to write to. This
                    can be used for dynamic file logging.

        Default:    {"normal": "logger.log", "all": "mixed.log"}

    bypassers:
                    This is an iterable of (setting, types, pairs,
                    module, attr) iterables. 'types' is an iterable of
                    all types that can match this bypasser. 'pairs' is
                    an iterable of two-tuples, the first argument is
                    the module, a dictionary or None, the second
                    argument is the attribute to search for in the
                    module or dict; if the module is None, the
                    bypassers will use the attribute as its direct
                    value look-up. After this mangling, if the value is
                    True in a boolean context, then the override will
                    occur, and the setting's value will be overridden
                    by the module and attribute's look-up, in the same
                    way that the pairs are check for truth testing.
                    'setting' is the setting to bypass when the
                    previously-mentioned conditionals evaluate to True,
                    so if at least one of the types matches the type
                    that the logger was called with, or if the value
                    evaluates to True. Do note that the types and pairs
                    parameters expect sets as parameters, and will fail
                    if not given as such. They can, however, be any
                    other object with the same API as sets. This is
                    done to allow the values to be modified and for the
                    modifications to carry over to the bypassers. Do
                    note that this parameter expects an iterable of
                    five-tuples, or an empty iterable.

        Default:    See below

    Available settings for the bypassers:

    These are the available settings to bypass. Do note that the
    default of all these settings is to not do anything, and must be
    explicitely set otherwise.

    "timestamp":
                    Will be used to replace the standard timestamp when
                    writing to file. It will not use that value to
                    perform the timestamp getting operation. Rather, it
                    will use the string given directly. If a different
                    timestamp for various reasons is the desired
                    result, a manual call to the _get_timestamp method
                    will need to be done. This is typically used to
                    remove a timestamp, so it will be used with the
                    pair of (None, ''), effectively removing the
                    timestamp.

    "splitter":
                    This will be used to determine if clever splitting
                    should occur when printing to screen. Clever
                    splitting splits the line at the latest space
                    before the line gets to the end of the terminal's
                    length. By default, this is True, and can be
                    changed when calling, on a per-line basis. This
                    bypasser overrides that.

    "display":
                    This is used to override the per-line setting that
                    decides whether the line should be printed to the
                    screen. This is set to True by default, and can be
                    overriden when calling on a per-line basis. This
                    bypasser can be used to bypass this setting.

    "write":
                    This is used to override the per-line setting that
                    decides whether the line should be written to the
                    file or not. This is set to True by default, and
                    can be overriden when calling on a per-line basis.
                    This bypasser can override that parameter.

    "logall":
                    Defaulting to None, this setting's bypassed value
                    must be a string object, which, if the bypassing
                    occurs, will be the file to write everything to.

    The following parameters are not actual bypassers. Only the types
    bound to the setting are of relevance. The pairs are ignored, and
    so are the module and attribute.

    "files":
                    The types bound to this setting will be used to
                    determine when to write and not to write to certain
                    files. This is only used when using the
                    Logger.multiple method, which will write to all
                    files specified, except those bound to the types
                    of this bypasser.

    "all":
                    The types bound to this setting will not be written
                    as when writing to the file defined through the
                    'logall' bypasser, if available.

    """

    def __init__(self, *, write=None, display=None, logfiles=None,
                 bypassers=None, **kwargs):
        """Create a new Logger instance."""

        super().__init__(**kwargs)

        self.display = pick(display, True)
        self.write = pick(write, True)

        files = {"normal": "logger.log"}

        if logfiles is not None:
            self.logfiles = logfiles
            for type, file in files.items():
                # if the type is already defined, don't overwrite it
                # only add to it if it doesn't exist
                self.logfiles[type] = self.logfiles.get(type, file)
        else:
            self.logfiles = files

        # this needs to be list/tuple of (setting, types, pairs,
        # module, attr) tuples; the setting is the setting to bypass;
        # types is a list of types to check for to determine if
        # bypassing should occur, same about the pairs, except for
        # module/attr matches; module and attr are used with getattr()
        # to bypass the value of setting with the one found in the
        # given module, for the given attribute; module of None means
        # to use the attr as the direct value; making the type None
        # will also indicate that any type can be triggered. To
        # indicate a lack of value for any parameter, pass NoValue, as
        # None has a special meaning
        if bypassers is None:
            bypassers = ()

        self.bypassers = Bypassers(*bypassers)

        self.bypassers.add("timestamp", "splitter", "display", "write",
                           "logall", "files", "all")

    @check_bypass
    def logger(self, *output, file=None, type=None, display=None, write=None,
               sep=None, split=None, use_utc=None, ts_format=None,
               print_ts=None):
        """Log everything to screen and/or file. Always use this."""

        sep = pick(sep, self.separator)
        split = self.bypassed.get("splitter", pick(split, self.split))
        display = self.bypassed.get("display", pick(display, self.display))
        write = self.bypassed.get("write", pick(write, self.write))

        timestamp = self.bypassed.get("timestamp",
                    self._get_timestamp(use_utc, ts_format))
        # this is the file to write everything to
        logall = self.bypassed.get("logall")

        if display:
            self._print(*output, sep=sep, use_utc=use_utc, split=split,
                         ts_format=ts_format, print_ts=print_ts)
        if write:
            output = self._get_output(output, sep).splitlines()
            alines = [x for x in self.logfiles if x in
                                 self.bypassers["all"][0]]
            getter = [file]
            if logall:
                getter.append(logall)
            for log in getter:
                if (log == logall and type not in alines) or log is None:
                    continue
                atypes = "type.%s - " % type if log == logall else ""
                with open(log, "a", encoding="utf-8", errors="replace") as f:
                    for writer in output:
                        f.write(timestamp + atypes + writer + "\n")

    def multiple(self, *output, types=None, display=None, **rest):
        """Log one or more line to multiple files."""
        types = pick(types, ["normal"])

        if len(types) == 1 and "*" in types: # allows any iterable
            for log in self.logfiles:
                if log not in self.bypassers["files"][0]:
                    if display:
                        self.logger(*output, type=log, display=True, **rest)
                        display = False # display only once
                    else:
                        self.logger(*output, type=log, display=False, **rest)

        elif types:
            for log in types:
                if display:
                    self.logger(*output, type=log, display=True, **rest)
                    display = False
                else:
                    self.logger(*output, type=log, display=False, **rest)

        else:
            self.logger(*output, display=display, **rest)

    def show(self, *output, type="show", display=True, write=False, **rest):
        """Explicit way to only print to screen."""
        self.logger(*output, type=type, display=display, write=write, **rest)

    def docstring(self, *output, tabs=4, display=True, write=False, sep=None,
                        **rest):
        """Print a docstring using proper formatting."""
        newlined = False
        indent = None
        lines = []

        sep = pick(sep, "\n")

        output = self._get_output(output, sep)
        for line in output.expandtabs(tabs).splitlines():
            if not newlined and not line.lstrip(): # first empty line
                newlined = True
            elif newlined and indent is None and line.lstrip():
                indent = len(line) - len(line.lstrip())
                line = line.lstrip()
            elif indent is not None:
                if line and line[indent:] == line.lstrip():
                    line = line.lstrip()
                elif (len(line) - len(line.lstrip())) > indent:
                    line = line[indent:]
                elif (len(line) - len(line.lstrip())) < indent:
                    line = line.lstrip()
            lines.append(line)

        while lines and not lines[-1].strip():
            lines.pop()
        while lines and not lines[0].strip():
            lines.pop(0)

        self.logger(*lines, display=display, write=write, sep=sep, **rest)

class Translater(Logger):
    """Logging class to use to translate lines.

    This is inherited from the Logger class.
    The parameters are the same as for the Logger class, plus these:

    all_languages:
                    Dictionary of {language:short} pairs. The language
                    is used for the standard lookup of the language.
                    The value is the 2-characters abbreviation of the
                    language. The default value is "English" for the
                    key, and "en" for the value. This must contain all
                    languages that this class will be asked to
                    translate to, see below for restrictions.

        Default:    {"English": "en"}

    main:
                    The main language that will be used. This is
                    considered the "default" language, and is the one
                    that will be used to write to the normal files. It
                    will always be written to the files, no matter what
                    language is being used.

        Default:    "English"

    current:
                    The current language, used for translating and
                    printing to screen. When writing to one or more
                    files, the files that this language's lines are
                    written into will be prepended with the
                    two-characters short language abbreviation that was
                    given in the all_languages dict, followed by a
                    single underscore and the file's name. This will
                    not be done if the language is the same as 'main'.

        Default:    "English"

    module:
                    The module or dictionary where the translations
                    will be looked up. This can be any arbitrary
                    object, as long as either the object has an
                    attribute corresponding to the line to translate
                    (see below for information on how those are looked
                    up), or it implements indexing via module[attr] and
                    'attr' is in object 'module'. If both are true,
                    only the first will be used. If neither are true,
                    it will print the string as-is. It will never
                    error. It WILL error, however, if the language used
                    is not in 'all_languages'. If it is None, then the
                    'modules' argument will be checked instead, see
                    below. It will also be checked if the module
                    defined here fails to find the appropriate line.

        Default:    None

    modules:
                    If the above parameter is set to None or otherwise
                    fails, it will use this parameter instead. It is a
                    mapping of {language:module} pairs that will be
                    used to search for each language. The keys must be
                    in the all_languages mapping as well. The value
                    must be a module (or any object) where the
                    attributes or items are equivalent to the strings
                    that will be passed in. If both the above and this
                    parameter are None, no translating will occur.

        Default:    None

    check:
                    Boolean value that will determine if a line should
                    be checked for translation or not. If False, the
                    line will not be checked and will be printed or
                    writen to the file as-is

        Default:    True

    first:
                    Determines which, of the line or the language, must
                    be checked first when looking up the translations.
                    The only valid arguments are "line" and "language".
                    Using 'line', the translater will look into the
                    module or mapping for an attribute or item named
                    'line', and then will look for an attribute or item
                    named like the current language, and will return
                    the matching result. Otherwise, it will look for an
                    item named like the current language, and then for
                    an item named like the line in it. If 'module' is
                    left undefined or fails but 'modules' is, this
                    parameter will be ignored and a single value lookup
                    will be performed.

                    Note about custom objects: The lookup uses getattr
                    followed by item.get if the former fails, falling
                    back to printing the line as-is if it fails.

        Default:    "language"

    pattern:
                    Regex pattern that determines when a line should be
                    given to the translater for replacing. If a line
                    doesn't match, it will not be translated.

        Default:    "[A-Z0-9_]*" - UPPERCASE_UNDERSCORED_NAMES

    Note on ignoring translation for certain lines: To prevent certain
    lines from being translated, use the "translate" setting for the
    bypassers, passing a five-tuple with the first item being
    "translate". The second item is an iterable (a set is the supported
    and recommended type) of types that should not be translated. The
    third item is another iterable (again, the Bypassers are meant to
    support a set), consisting of (module, attr) pairs, where the
    module can be any object or None, and the attribute can be an
    attribute or item of the module or, if the module is None, the
    direct value will be looked up instead. The last two parameters can
    be anything (but must be present), they will be replaced at runtime
    as they are only used internally to decide when not to translate.

    To entirely prevent any line from being checked against the pattern
    and be potentially translated, pass the "check" keyword argument
    with a True value, or use the "check" setting of the bypassers.

    Note on translating: The translated lines can take new-style
    formatting with {0} or similar; it can use list indexes, regular
    indexes or named indexes like {foo}. Assign an ordered iterable for
    the numeric indexes to the 'format' argument of the logger method,
    and a mapping to the 'format_dict' argument of the logger method.
    Old-style formatting using the modulus (%) operand may still be
    used, by passing a sequence or mapping to the 'format_mod' argument
    of the logger method. It is up to the user to make sure that the
    proper type of iterable is given, with the proper arguments in the
    string. Numerical and named arguments cannot be mixed for old-style
    formatting. The new-style formatting is the recommended method.
    Unlike new-style formatting, the modulus method can fail if the
    incorrect amount of parameters are given. Both formatting methods
    can be used at the same time. Also, do note that it IS possible to
    give strings matching the regex pattern to format, and they will be
    properly translated as well. It is not, however, possible to loop
    through these recursively. The formatting rules would become too
    complicated for the small benefit that such a feature would
    provide. If one really needs to do so, they can call the logger
    method recursively on their own.

    Worth of note: The modulus-style formatting is applied after the
    new-style formatting. This makes it easier to go one layer deeper
    into the formatting, and allow for formatting from inside the
    previsouly-formatted lines.

    If translating directly without using the logger method, here are a
    few useful bits of information:

    - It operates through side-effect. This means that it doesn't
      return any value, rather, it directly alters the list given. If
      the object passed in as the first parameter is not mutable, an
      exception will occur. This restriction does not apply to the
      formats.

    - It takes five arguments (besides self). The first argument is
      the mutable object used for the output (and which will be
      altered). The second argument is the language. This will be used
      for looking up which line lines to use. The 3 other arguments are
      used for formatting, post-translation. All 3 arguments must be
      given. The first of the three is to be used as the numerical
      formatting using new-style string formatting (the str.format
      method). The second is a mapping to be used in the new-style
      formatting as well. The third one can be either a (mutable)
      sequence or mapping, and is used for old-style formatting
      (modulus formatting with the % operand). It will be applied after
      the new-style formatting has been applied.

    - It makes sure to retain the original class of the formats
      iterables passed in, if it can. The class of each variable needs
      to define a copy method, if it does, it will be used. If there
      are no copy methods, it will use the default expectation of what
      the iterable should be; a list for 'format' and 'format_mod', and
      a dict for 'format_dict'; this is done to accept any object, not
      just built-in ones.

    - It requires an iterable of strings to be passed in. Passing a single
      string will not work as intended.

    """

    def __init__(self, *, all_languages=None, main=None, current=None,
                 module=None, modules=None, check=None, first=None,
                 pattern=None, **kwargs):
        """Create a new translater object."""

        super().__init__(**kwargs)

        langs = {"English": "en"}

        if all_languages is not None:
            self.all_languages = all_languages
            for long, short in langs.items():
                self.all_languages[long] = self.all_languages.get(long, short)
        else:
            self.all_languages = langs

        self.main = pick(main, "English")
        self.current = pick(current, self.main)

        self.bypassers.update(("translate", set(), set(), None, True))
        self.bypassers.add("check")

        self.module = module
        self.modules = modules

        self.check = pick(check, True)
        self.first = pick(first, "language")
        self.pattern = pick(pattern, "[A-Z0-9_]*")

    def translate(self, output, language, format, format_dict, format_mod):
        """Translate a line into the desired language."""

        def copy(name, new):
            return getattr(name.__class__, "copy", new)(name)

        format = copy(format, list)
        format_dict = copy(format_dict, dict)
        format_mod = copy(format_mod, list)

        def enum(iterable):
            if hasattr(iterable, "items"):
                return list(iterable.items())
            return enumerate(iterable)

        def get_line(module, other, fallback):
            try:
                value = getattr(module, other)
            except AttributeError:
                try:
                    value = module[other]
                except (TypeError, KeyError, IndexError):
                    return fallback
            return value

        # for loops are amazing and incredible
        for iterable in (format, format_dict, format_mod, output):
            for i, line in enum(iterable):
                if re.fullmatch(self.pattern, line) is None:
                    continue
                original = line
                module = None
                lang = None
                if self.module is not None:
                    if self.first == "line":
                        module = get_line(self.module, line, original)
                    else:
                        module = get_line(self.module, language,
                                 get_line(self.module, self.main, original))

                if module is None and self.modules is not None:
                    lang = self.modules.get(language)
                    if lang is not None:
                        module = get_line(lang, line, original)

                if module is not None:
                    if lang is None:
                        if self.first == "line":
                            line = get_line(module, language,
                                   get_line(module, self.main, original))
                        else:
                            line = get_line(module, line, original)

                    else:
                        line = module

                if line != original and iterable == output:
                    line = line.format(*format, **format_dict) % format_mod

                iterable[i] = line

    @check_bypass
    def logger(self, *output, file=None, type=None, sep=None, check=None,
               language=None, format=None, format_dict=None, format_mod=None,
               **kwargs):
        """Log a line after translating it."""

        sep = pick(sep, self.separator)

        language = pick(language, self.current)
        check = self.bypassed.get("check", pick(check, self.check))

        format = pick(format, ())
        format_dict = pick(format_dict, {})
        format_mod = pick(format_mod, ())

        output = self._get_output(output, sep, True)

        if ("translate" not in self.bypassed and check and
                               language != self.main):
            trout = output[:]
            self.translate(trout, language, format, format_dict, format_mod)

            trfile = self.all_languages[language] + "_" + file

            super().logger(*trout, file=trfile, type=type, sep=sep, **kwargs)

            display = False

        if check:
            self.translate(output, self.main, format, format_dict, format_mod)

        super().logger(*output, file=file, type=type, sep=sep, **kwargs)

class LevelLogger(Logger):
    """Implement levelled logging.

    "level":
                    Number specifying the default level at which lines
                    will be logged.

        Default:    0

    Bypassers arguments:

    "level":
                    Bypasser to override the "level" parameter given to
                    the logger method. The resulting value must be a
                    number or None.

    """

    def __init__(self, *, level=None, **kwargs):
        """Create a new levelled logging instance."""

        super().__init__(**kwargs)

        self.bypassers.add("level")

        self.level = pick(level, 0)

    @check_bypass
    def logger(self, *output, level=None, **kwargs):
        """Log a line based on level given."""

        level = self.bypassed.get("level", level)

        if level is not None and level >= self.level:
            super().logger(*output, **kwargs)

class TranslatedLevelLogger(LevelLogger, Translater):
    """Implement a way to have levelled logging with translating."""

class LoggingLevels(sys.__class__):
    """Module class for logging levels."""

    def __init__(self, **items):
        """Create a new items mapping."""
        for level, value in items.items():
            setattr(self, level, value)
        super().__init__(self.__class__.__name__, self.__class__.__doc__)

    def __iter__(self):
        """Iterate over the items of self."""
        return (x for x in self.__dict__ if x[0] != "_")

    def __len__(self):
        """Return the number of items in self."""
        num = 0
        for x in self:
            num += 1
        return num

class NamedLevelsLogger(LevelLogger):
    """Implement named levels logging.

    "levels":
                    Mapping of {name:level} pairs, which are used to
                    implement named logging. This supports mutation of
                    the mapping to update the internal mapping.

        Default:    {}

    To add, change or remove a level after instantiation, either the
    original mapping can be altered, or direct change can be made via
    `self.levels.level_to_change = new_value` or similar.

    Passing the level value can be done either through a direct lookup
    with the `levels` argument, a number, a name matching a level, or
    None.

    Bypassers arguments:

    "level":
                    Used to override the "level" parameter given to the
                    logger method. The resulting value must be a lookup
                    to a value in the mapping, a number, a name
                    matching a level, or None.

    """

    def __init__(self, *, levels=None, default=None, **kwargs):
        """Create a new instance of the named levels logger."""

        super().__init__(**kwargs)

        self.default = pick(default, "normal")
        self.levels = LoggingLevels(**pick(levels, {}))

        if self.default not in self.levels:
            setattr(self.levels, self.default, 0)

    def logger(self, *output, level=None, **kwargs):
        """Log a line matching a named level."""

        try: # string - direct value lookup (eg "info" is levels.info)
            level = getattr(self.levels, level)
        except TypeError: # got an int, direct value lookup, or None
            pass
        except AttributeError: # unknown value; fall back to normal
            level = getattr(self.levels, self.default)

        super().logger(*output, level=level, **kwargs)

class TranslatedNamedLevelsLogger(NamedLevelsLogger, TranslatedLevelLogger):
    """Implement a way to use named levels with translating."""
