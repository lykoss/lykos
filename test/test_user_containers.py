from unittest import TestCase
from src.containers import UserSet, UserDict, UserList, DefaultUserDict
from src.users import FakeUser

class TestUserContainers(TestCase):
    def test_set_init_exist(self):
        user = FakeUser.from_nick("1")
        self.assertEqual(str(UserSet()), "UserSet()")
        value = UserSet([user])
        self.assertEqual(str(value), "UserSet(1)")

    def test_set_init_appear(self):
        user = FakeUser.from_nick("1")
        value = UserSet([user])
        self.assertIn(value, user.sets)

    def test_set_init_exclusive(self):
        with self.assertRaises(TypeError):
            UserSet([1, 2, 3])

    def test_set_init_unique(self):
        user = FakeUser.from_nick("1")
        value = UserSet([user, user])
        self.assertEqual(str(value), "UserSet(1)")

    def test_set_add_exist(self):
        user = FakeUser.from_nick("1")
        value = UserSet()
        value.add(user)
        self.assertEquals(str(value), "UserSet(1)")

    def test_set_add_appear(self):
        user = FakeUser.from_nick("1")
        value = UserSet()
        value.add(user)
        self.assertIn(value, user.sets)

    def test_set_add_exclusive(self):
        user = FakeUser.from_nick("1")
        value = UserSet()
        value.add(user)
        self.assertRaises(TypeError, value.add, "1")

    def test_set_add_unique(self):
        user = FakeUser.from_nick("1")
        value = UserSet()
        value.add(user)
        self.assertEquals(str(value), "UserSet(1)")
        value.add(user)
        self.assertEquals(str(value), "UserSet(1)")

    def test_set_clear(self):
        user = FakeUser.from_nick("1")
        value = UserSet([user])
        self.assertIn(value, user.sets)
        value.clear()
        self.assertNotIn(value, user.sets)
        self.assertEqual(str(value), "UserSet()")

    def test_set_difference(self):
        user1 = FakeUser.from_nick("1")
        user2 = FakeUser.from_nick("2")
        value = UserSet([user1, user2])
        new = value.difference([user2])
        self.assertEqual(str(new), "UserSet(1)")
        self.assertEqual(str(value), "UserSet(1, 2)")
        self.assertIn(value, user1.sets)
        self.assertIn(value, user2.sets)
        self.assertIn(new, user1.sets)
        self.assertNotIn(new, user2.sets)

    def test_set_difference_update(self):
        user1 = FakeUser.from_nick("1")
        user2 = FakeUser.from_nick("2")
        value = UserSet([user1, user2])
        value.difference_update([user2])
        self.assertIn(value, user1.sets)
        self.assertNotIn(value, user2.sets)
        self.assertEqual(str(value), "UserSet(1)")
