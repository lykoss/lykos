from unittest import TestCase
from src.containers import UserSet, UserDict, UserList, DefaultUserDict
from src.users import FakeUser

class TestUserContainers(TestCase):
    def test_set_init(self):
        user = FakeUser.from_nick("1")
        self.assertEqual(str(UserSet()), "UserSet()")
        self.assertEqual(str(UserSet([user])), "UserSet(1)")
