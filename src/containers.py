from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from typing import Dict, Generic, Iterable, List, Set, TypeVar

from src.users import User

__all__ = ["UserList", "UserSet", "UserDict", "DefaultUserDict"]

KT = TypeVar("KT")
VT = TypeVar("VT")

""" * Important *

The containers present here should always follow these rules:

- Once a global variable has been set to one of the containers, it *must not* be overwritten;

- The proper way to empty a container is with the 'container.clear()' method. The 'UserDict.clear' method
  also takes care of calling the '.clear()' method of nested containers (if any), so you needn't do that;

- If any local variable points to a container, the 'container.clear()' method
  *must* be called before the variable goes out of scope;

- Copying a container for mutation purpose in a local context should make use of context managers,
  e.g. 'with copy.deepcopy(var.roles) as rolelist:' instead of 'rolelist = copy.deepcopy(var.roles)',
  with all operations on 'rolelist' being done inside the block. Once the 'with' block is exited (be it
  through exceptions or normal execution), the copied contained ('rolelist' in this case) is automatically cleared.

- If fetching a container from a 'UserDict' with the intent to keep it around separate from the dictionary,
  a copy is advised, as 'UserDict.clear' is recursive and will clear all nested containers, even if they
  are being used outside (as the function has no way to know).

Role files should use User containers as their global variables without ever overwriting them. It is advised to
pay close attention to where the variables get touched, to keep the above rules enforced. Refer to existing role
files to get an idea of how those containers should be used.

"""

class Container(ABC):
    """Base container class for all containers."""

    __slots__ = ()

    @abstractmethod
    def __init__(self, iterable: Iterable = ()):
        # We require subclasses to accept an iterable but we don't implicitly populate the
        # base class with it since that would lead to potentially forgotten tracking.
        # Instead the subclass should iterate over iterable and add each element to the parent container
        # with its own add/append/etc. method that implements proper user tracking.
        super(Container, self).__init__()

    def __iter__(self):
        # noinspection PyUnresolvedReferences
        return super(Container, self).__iter__()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.clear()

    def __format__(self, format_spec=""):
        args = [format(x, format_spec) for x in self]
        return "{0}({1})".format(self.__class__.__name__, ", ".join(args))

    def __str__(self):
        return self.__format__()

    def __eq__(self, other):
        return self is other

    def __copy__(self):
        return type(self)(self)

    def __deepcopy__(self, memo):
        return type(self)(copy.deepcopy(x, memo) for x in self)

    def copy(self):
        return self.__copy__()

    @abstractmethod
    def clear(self):
        # noinspection PyUnresolvedReferences
        super(Container, self).clear()

class UserList(Container, List[User]):
    def __init__(self, iterable=()):
        super().__init__()
        try:
            for item in iterable:
                self.append(item)
        except:
            self.clear()
            raise

    def __add__(self, other):
        if not isinstance(other, list):
            return NotImplemented

        self.extend(other)

    def __getitem__(self, item):
        new = super().__getitem__(item)
        if isinstance(item, slice):
            new = type(self)(new)
        return new

    def __setitem__(self, index, value):
        if not isinstance(value, User):
            raise TypeError("UserList may only contain User instances")

        item = self[index]
        super().__setitem__(index, value)
        if item not in self:
            item.lists.remove(self)

        if self not in value.lists:
            value.lists.append(self)

    def __delitem__(self, index):
        item = self[index]

        super().__delitem__(index)

        if item not in self: # there may have been multiple instances
            item.lists.remove(self)

    def append(self, item):
        if not isinstance(item, User):
            raise TypeError("UserList may only contain User instances")

        if self not in item.lists:
            item.lists.append(self)

        super().append(item)

    def clear(self):
        for item in self:
            if self in item.lists:
                item.lists.remove(self)

        super().clear()

    def extend(self, iterable):
        for item in iterable:
            self.append(item)

    def insert(self, index, item):
        if not isinstance(item, User):
            raise TypeError("UserList may only contain User instances")

        super().insert(index, item)

        # If it didn't work, we don't get here

        if self not in item.lists:
            item.lists.append(self)

    def pop(self, index=-1):
        item = super().pop(index)

        if item not in self:
            item.lists.remove(self)

        return item

    def remove(self, item):
        super().remove(item)

        if item not in self:
            item.lists.remove(self)

class UserSet(Container, Set[User]):
    def __init__(self, iterable=()):
        super().__init__()
        try:
            for item in iterable:
                self.add(item)
        except:
            self.clear()
            raise

    def __format__(self, format_spec=""):
        # sort the args so we have a stable result regardless of our hash key for unit testing
        args = sorted([format(x, format_spec) for x in self])
        return "{0}({1})".format(self.__class__.__name__, ", ".join(args))

    # Operators are not overloaded - 'user_set & other_set' will return a regular set
    # This is a deliberate design decision. To get a UserSet out of them, use the named ones

    # Augmented assignment method overrides

    def __iand__(self, other):  # type: ignore
        if not isinstance(other, set):
            return NotImplemented

        self.intersection_update(other)
        return self

    def __ior__(self, other):  # type: ignore
        if not isinstance(other, set):
            return NotImplemented

        self.update(other)
        return self

    def __isub__(self, other):  # type: ignore
        if not isinstance(other, set):
            return NotImplemented

        self.difference_update(other)

    def __ixor__(self, other):  # type: ignore
        if not isinstance(other, set):
            return NotImplemented

        self.symmetric_difference_update(other)
        return self

    def add(self, item):
        if item not in self:
            if not isinstance(item, User):
                raise TypeError("UserSet may only contain User instances")

            item.sets.append(self)
            super().add(item)

    def clear(self):
        for item in self:
            item.sets.remove(self)

        super().clear()

    def difference(self, iterable):
        return type(self)(super().difference(iterable))

    def difference_update(self, iterable):
        for item in iterable:
            if item in self:
                self.remove(item)

    def discard(self, item):
        if item in self:
            item.sets.remove(self)

        super().discard(item)

    def intersection(self, iterable):
        return type(self)(super().intersection(iterable))

    def intersection_update(self, iterable):
        for item in set(self):
            if item not in iterable:
                self.remove(item)

    def pop(self):
        item = super().pop()
        item.sets.remove(self)
        return item

    def remove(self, item):
        super().remove(item)

        item.sets.remove(self)

    def symmetric_difference(self, iterable):
        return type(self)(super().symmetric_difference(iterable))

    def symmetric_difference_update(self, iterable):
        for item in iterable:
            if item in self:
                self.remove(item)
            else:
                self.add(item)

    def union(self, iterable):
        return type(self)(super().union(iterable))

    def update(self, iterable):
        for item in iterable:
            if item not in self:
                self.add(item)

class UserDict(Container, Dict[KT, VT], Generic[KT, VT]):
    def __init__(self, _it=(), **kwargs):
        super().__init__()
        if hasattr(_it, "items"):
            _it = _it.items()
        try:
            for key, value in _it:
                self[key] = value
            for key, value in kwargs.items():
                self[key] = value
        except:
            while self:
                self.popitem() # don't clear, as it's recursive (we might not want that)
            raise

    def __format__(self, format_spec=""):
        if format_spec == "for_tb":
            # we don't know if the keys, the values, or both are Users or other user containers, so try all 3...
            try:
                args = ["{0:for_tb}: {1:for_tb}".format(x, y) for x, y in self.items()]
            except TypeError:
                try:
                    args = ["{0:for_tb}: {1}".format(x, y) for x, y in self.items()]
                except TypeError:
                    args = ["{0}: {1:for_tb}".format(x, y) for x, y in self.items()]
        elif format_spec == "":
            # maintain a stable ordering for unit testing regardless of hash key
            args = sorted(["{0}: {1}".format(x, y) for x, y in self.items()])
        else:
            return super().__format__(format_spec)

        return "{0}({1})".format(self.__class__.__name__, ", ".join(args))

    def __deepcopy__(self, memo):
        new = type(self)()
        for key, value in self.items():
            new[key] = copy.deepcopy(value, memo)
        return new

    def __setitem__(self, item, value):
        old = self.get(item)
        super().__setitem__(item, value)
        if isinstance(old, User):
            if old not in self.values():
                old.dict_values.remove(self)

        if isinstance(item, User):
            if self not in item.dict_keys:
                item.dict_keys.append(self)

        if isinstance(value, User):
            if self not in value.dict_values:
                value.dict_values.append(self)

    def __delitem__(self, item):
        if isinstance(item, slice): # special-case: delete if it exists, otherwise don't
            if item.start is item.step is None: # checks out
                item = item.stop
                if item not in self:
                    return

        value = self[item]
        super().__delitem__(item)
        if isinstance(item, User):
            item.dict_keys.remove(self)

        if isinstance(value, User):
            if value not in self.values():
                value.dict_values.remove(self)

        if isinstance(value, (UserSet, UserList, UserDict)):
            value.clear()

    def clear(self):
        for key, value in self.items():
            if isinstance(key, User):
                key.dict_keys.remove(self)
            if isinstance(value, User):
                if self in value.dict_values:
                    value.dict_values.remove(self)

            if isinstance(value, (UserList, UserSet, UserDict)):
                value.clear()

        super().clear()

    @classmethod
    def fromkeys(cls, iterable, value=None):
        return cls(dict.fromkeys(iterable, value))

    def pop(self, key, *default):
        value = super().pop(key, *default)
        if isinstance(key, User):
            if self in key.dict_keys:
                key.dict_keys.remove(self)
        if isinstance(value, User):
            if value not in self.values():
                value.dict_values.remove(self)
        return value

    def popitem(self):
        key, value = super().popitem()
        if isinstance(key, User):
            key.dict_keys.remove(self)
        if isinstance(value, User):
            if value not in self.values():
                value.dict_values.remove(self)
        return key, value

    def setdefault(self, key, default=None):
        if key not in self:
            self[key] = default
        return self[key]

    def update(self, iterable):
        if hasattr(iterable, "items"):
            iterable = iterable.items()
        for key, value in iterable:
            self[key] = value

class DefaultUserDict(UserDict[KT, VT], Generic[KT, VT]):
    def __init__(self, _factory, _it=(), **kwargs):
        self.factory = _factory
        super().__init__(_it, **kwargs)

    def __missing__(self, key):
        self[key] = self.factory()
        return self[key]
