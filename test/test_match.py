from unittest import TestCase
from src.match import Match, match_all, match_one
from src.functions import match_role, match_mode, match_totem
from src.cats import Wolf

class TestMatch(TestCase):
    def __init__(self, methodName="runTest"):
        super().__init__(methodName)
        self.addTypeEqualityFunc(Match, self.assertMatchEqual)

    def assertMatchEqual(self, match1: Match, match2: Match, msg):
        self.assertSetEqual(set(match1), set(match2), msg)

    def test_match_obj(self):
        corpus = ("foo", "bar", "baz")
        single = match_all("foo", corpus)
        multiple = match_all("ba", corpus)
        with self.subTest("__bool__"):
            self.assertTrue(single)
            self.assertFalse(multiple)
        with self.subTest("get"):
            self.assertEqual(single.get(), "foo")
            self.assertRaises(ValueError, multiple.get)
        with self.subTest("__len__"):
            self.assertEqual(len(single), 1)
            self.assertEqual(len(multiple), 2)
        with self.subTest("__iter__"):
            self.assertEqual(set(single), {"foo"})
            self.assertEqual(set(multiple), {"bar", "baz"})

    def test_match_all(self):
        corpus = ("foo", "bar", "baz", "over", "overlapped", "AWOO")
        with self.subTest("single match, exact"):
            self.assertEqual(match_all("foo", corpus), Match({"foo"}))
            self.assertEqual(match_all("bar", corpus), Match({"bar"}))
            self.assertEqual(match_all("over", corpus), Match({"over"}))
        with self.subTest("single match, prefix"):
            self.assertEqual(match_all("f", corpus), Match({"foo"}))
            self.assertEqual(match_all("overl", corpus), Match({"overlapped"}))
        with self.subTest("multiple matches"):
            self.assertEqual(match_all("ba", corpus), Match({"bar", "baz"}))
        with self.subTest("case insensitivity"):
            self.assertEqual(match_all("a", corpus), Match({"AWOO"}))
            self.assertEqual(match_all("aWoO", corpus), Match({"AWOO"}))
            self.assertEqual(match_all("FOO", corpus), Match({"foo"}))

    def test_match_one(self):
        corpus = ("foo", "bar", "baz", "overlapped", "ovation", "AWOO")
        with self.subTest("single match, exact"):
            self.assertEqual(match_one("foo", corpus), "foo")
            self.assertEqual(match_one("bar", corpus), "bar")
        with self.subTest("single match, prefix"):
            self.assertEqual(match_one("f", corpus), "foo")
            self.assertEqual(match_one("ove", corpus), "overlapped")
        with self.subTest("multiple matches"):
            self.assertIsNone(match_one("ba", corpus))
        with self.subTest("case insensitivity"):
            self.assertEqual(match_one("a", corpus), "AWOO")
            self.assertEqual(match_one("aWoO", corpus), "AWOO")
            self.assertEqual(match_one("FOO", corpus), "foo")

    def test_match_role(self):
        with self.subTest("regular match"):
            self.assertEqual(match_role("det").get().key, "detective")
            self.assertEqual(match_role("lover").get().key, "lover")
            self.assertEqual(match_role("crazed shaman").get().key, "crazed shaman")
            self.assertFalse(match_role("crazedshaman"))
            self.assertFalse(match_role("wolfteam"))
        with self.subTest("removing spaces"):
            self.assertEqual(match_role("crazed shaman", remove_spaces=True).get().key, "crazed shaman")
            self.assertEqual(match_role("crazedshaman", remove_spaces=True).get().key, "crazed shaman")
        with self.subTest("allowing extra"):
            self.assertEqual(match_role("wolfteam", allow_extra=True).get().key, "wolfteam player")
        with self.subTest("disallowing special roles"):
            self.assertFalse(match_role("lover", allow_special=False))
        with self.subTest("limited scope"):
            self.assertFalse(match_role("det", scope=Wolf))
            self.assertEqual(match_role("alpha", scope=Wolf).get().key, "alpha wolf")

    def test_match_totem(self):
        with self.subTest("regular match"):
            self.assertEqual(match_totem("pac").get().key, "pacifism")
            self.assertEqual(match_totem("death").get().key, "death")
            self.assertFalse(match_totem("nonexistent"))
        with self.subTest("limited scope"):
            self.assertEqual(match_totem("pac", {"pacifism", "desperation"}).get().key, "pacifism")
            self.assertFalse(match_totem("death", {"pacifism", "desperation"}))

    def test_match_mode(self):
        with self.subTest("regular match"):
            self.assertEqual(match_mode("def").get().key, "default")
            self.assertFalse(match_mode("villagergame"))
        with self.subTest("allowing extra"):
            self.assertEqual(match_mode("def", allow_extra=True).get().key, "default")
            self.assertEqual(match_mode("villagergame", allow_extra=True).get().key, "villagergame")
