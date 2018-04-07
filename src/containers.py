from src.users import User

__all__ = ["UserList", "UserSet", "UserDict"]

""" * Important *

The containers present here should always follow these rules:

- Once a global variable has been set to one of the containers, it *must not* be overwritten;

- The proper way to empty a container is with the 'container.clear()' method. The 'UserDict.clear' method
  also takes care of calling the '.clear()' method of nested containers (if any), so you needn't do that;

- If any local variable points to a container, the 'container.clear()' method
  *must* be called before the variable goes out of scope;

- Copying a container for mutation purpose in a local context should make use of context managers,
  e.g. 'with copy.deepcopy(var.ROLES) as rolelist:' instead of 'rolelist = copy.deepcopy(var.ROLES)',
  with all operations on 'rolelist' being done inside the block. Once the 'with' block is exited (be it
  through exceptions or normal execution), the copied contained ('rolelist' in this case) is automatically cleared.

- If fetching a container from a 'UserDict' with the intent to keep it around separate from the dictionary,
  a copy is advised, as `UserDict.clear` is recursive and will clear all nested containers, even if they
  are being used outside (as the function has no way to know).

Role files should use User containers as their global variables without ever overwriting them. It is advised to
pay close attention to where the variables get touched, to keep the above rules enforced. Refer to existing role
files to get an idea of how those containers should be used.

"""

class UserList(list):
    def __init__(self, iterable=()):
        super().__init__()
        for item in iterable:
            if not isinstance(item, User):
                raise TypeError("UserList may only contain User instances")

            if self not in item.lists:
                item.lists.append(self)
            self.append(item)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.clear()

    def __add__(self, other):
        if not isinstance(other, list):
            return NotImplemented

        self.extend(other)

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
            item.lists.remove(self)

        super().clear()

    def copy(self):
        return type(self)(self)

    def extend(self, iterable):
        for item in iterable:
            if not isinstance(item, User):
                raise TypeError("UserList may only contain User instances")

            if self not in item.lists:
                item.lists.append(self)
            super().append(item)

    def insert(self, index, item):
        super().insert(index, item)

        # If it didn't work, we don't get here

        if not isinstance(item, User):
            raise TypeError("UserList may only contain User instances")

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

class UserSet(set):
    def __init__(self, iterable=()):
        super().__init__()
        for item in iterable:
            if not isinstance(item, User):
                raise TypeError("UserSet may only contain User instances")

            if self not in item.sets:
                item.sets.append(self)
            self.add(item)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.clear()

    # Augmented assignment method overrides

    def __iand__(self, other):
        res = super().__iand__(other)
        if not isinstance(other, set):
            return NotImplemented

        self.intersection_update(other)
        return self

    def __ior__(self, other):
        if not isinstance(other, set):
            return NotImplemented

        self.update(other)
        return self

    def __isub__(self, other):
        if not isinstance(other, set):
            return NotImplemented

        self.difference_update(other)
        return

    def __ixor__(self, other):
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

    def copy(self):
        return type(self)(self)

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

class UserDict(dict):
    def __init__(_self, _it=(), **kwargs):
        super().__init__()
        for key, value in _it:
            self[key] = value
        for key, value in kwargs.items():
            self[key] = value

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.clear()

    def __setitem__(self, item, value):
        in_self = item in self
        if in_self:
            old = self[item]
        super().__setitem__(item, value)
        if in_self:
            if isinstance(old, User):
                if old not in self.values():
                    old.dict_values.remove(self)

        if isinstance(item, User):
            if self not in item.dict_keys:
                item.dict_keys.append(self)

        if isinstance(value, User):
            if self not in item.dict_values:
                item.dict_values.append(self)

    def __delitem__(self, item):
        value = self[item]
        super().__delitem__(item)
        if isinstance(item, User):
            item.dict_keys.remove(self)

        if isinstance(value, User):
            if value not in self.values():
                item.dict_values.remove(self)

    def clear(self):
        for key, value in self.items():
            if isinstance(key, User):
                key.dict_keys.remove(self)
            if isinstance(value, User):
                if self in value.dict_values:
                    value.dict_values.remove(self)

            if isinstance(key, (UserList, UserSet, UserDict)):
                key.clear()
            if isinstance(value, (UserList, UserSet, UserDict)):
                value.clear()

        super().clear()

    def copy(self):
        return type(self)(self.items())

    @classmethod
    def fromkeys(cls, iterable, value=None):
        return cls(dict.fromkeys(iterable, value))

    def pop(self, key, *default):
        value = super().pop(key, *default)
        if isinstance(key, User):
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
