from unittest import TestCase
from src.config import merge, Empty

class TestConfigMerge(TestCase):
    def test_merge_str_replace(self):
        metadata = {"_type": "str", "_default": "foo", "_merge": "replace"}
        with self.subTest("default fallback"):
            self.assertEqual(merge(metadata, Empty, Empty), "foo")
        with self.subTest("base fallback"):
            self.assertEqual(merge(metadata, "bar", Empty), "bar")
        with self.subTest("empty base"):
            self.assertEqual(merge(metadata, Empty, "baz"), "baz")
        with self.subTest("non-empty base"):
            self.assertEqual(merge(metadata, "bar", "baz"), "baz")

    def test_merge_int_replace(self):
        metadata = {"_type": "int", "_default": 1, "_merge": "replace"}
        with self.subTest("default fallback"):
            self.assertEqual(merge(metadata, Empty, Empty), 1)
        with self.subTest("base fallback"):
            self.assertEqual(merge(metadata, 2, Empty), 2)
        with self.subTest("empty base"):
            self.assertEqual(merge(metadata, Empty, 3), 3)
        with self.subTest("non-empty base"):
            self.assertEqual(merge(metadata, 2, 3), 3)

    def test_merge_int_max(self):
        metadata = {"_type": "int", "_default": 2, "_merge": "max"}
        with self.subTest("default fallback"):
            self.assertEqual(merge(metadata, Empty, Empty), 2)
        with self.subTest("base fallback"):
            self.assertEqual(merge(metadata, 1, Empty), 2)
            self.assertEqual(merge(metadata, 3, Empty), 3)
        with self.subTest("empty base"):
            self.assertEqual(merge(metadata, Empty, 1), 2)
            self.assertEqual(merge(metadata, Empty, 3), 3)
        with self.subTest("non-empty base"):
            self.assertEqual(merge(metadata, 1, 3), 3)
            self.assertEqual(merge(metadata, 3, 1), 3)

    def test_merge_int_min(self):
        metadata = {"_type": "int", "_default": 2, "_merge": "min"}
        with self.subTest("default fallback"):
            self.assertEqual(merge(metadata, Empty, Empty), 2)
        with self.subTest("base fallback"):
            self.assertEqual(merge(metadata, 1, Empty), 1)
            self.assertEqual(merge(metadata, 3, Empty), 2)
        with self.subTest("empty base"):
            self.assertEqual(merge(metadata, Empty, 1), 1)
            self.assertEqual(merge(metadata, Empty, 3), 2)
        with self.subTest("non-empty base"):
            self.assertEqual(merge(metadata, 1, 3), 1)
            self.assertEqual(merge(metadata, 3, 1), 1)

    def test_merge_float_replace(self):
        metadata = {"_type": "float", "_default": 1.0, "_merge": "replace"}
        with self.subTest("default fallback"):
            self.assertEqual(merge(metadata, Empty, Empty), 1.0)
        with self.subTest("base fallback"):
            self.assertEqual(merge(metadata, 2.0, Empty), 2.0)
        with self.subTest("empty base"):
            self.assertEqual(merge(metadata, Empty, 3.0), 3.0)
        with self.subTest("non-empty base"):
            self.assertEqual(merge(metadata, 2.0, 3.0), 3.0)

    def test_merge_float_max(self):
        metadata = {"_type": "float", "_default": 2.0, "_merge": "max"}
        with self.subTest("default fallback"):
            self.assertEqual(merge(metadata, Empty, Empty), 2.0)
        with self.subTest("base fallback"):
            self.assertEqual(merge(metadata, 1.0, Empty), 2.0)
            self.assertEqual(merge(metadata, 3.0, Empty), 3.0)
        with self.subTest("empty base"):
            self.assertEqual(merge(metadata, Empty, 1.0), 2.0)
            self.assertEqual(merge(metadata, Empty, 3.0), 3.0)
        with self.subTest("non-empty base"):
            self.assertEqual(merge(metadata, 1.0, 3.0), 3.0)
            self.assertEqual(merge(metadata, 3.0, 1.0), 3.0)

    def test_merge_float_min(self):
        metadata = {"_type": "float", "_default": 2.0, "_merge": "min"}
        with self.subTest("default fallback"):
            self.assertEqual(merge(metadata, Empty, Empty), 2.0)
        with self.subTest("base fallback"):
            self.assertEqual(merge(metadata, 1.0, Empty), 1.0)
            self.assertEqual(merge(metadata, 3.0, Empty), 2.0)
        with self.subTest("empty base"):
            self.assertEqual(merge(metadata, Empty, 1.0), 1.0)
            self.assertEqual(merge(metadata, Empty, 3.0), 2.0)
        with self.subTest("non-empty base"):
            self.assertEqual(merge(metadata, 1.0, 3.0), 1.0)
            self.assertEqual(merge(metadata, 3.0, 1.0), 1.0)

    def test_merge_bool_replace(self):
        metadata = {"_type": "bool", "_default": False, "_merge": "replace"}
        with self.subTest("default fallback"):
            self.assertIs(merge(metadata, Empty, Empty), False)
        with self.subTest("base fallback"):
            self.assertIs(merge(metadata, True, Empty), True)
        with self.subTest("empty base"):
            self.assertIs(merge(metadata, Empty, True), True)
        with self.subTest("non-empty base"):
            self.assertIs(merge(metadata, True, False), False)
            self.assertIs(merge(metadata, False, True), True)

    def test_merge_bool_and(self):
        metadata_false = {"_type": "bool", "_default": False, "_merge": "and"}
        metadata_true = {"_type": "bool", "_default": True, "_merge": "and"}
        with self.subTest("default fallback"):
            self.assertIs(merge(metadata_false, Empty, Empty), False)
            self.assertIs(merge(metadata_true, Empty, Empty), True)
        with self.subTest("base fallback"):
            self.assertIs(merge(metadata_false, True, Empty), False)
            self.assertIs(merge(metadata_false, False, Empty), False)
            self.assertIs(merge(metadata_true, True, Empty), True)
            self.assertIs(merge(metadata_true, False, Empty), False)
        with self.subTest("empty base"):
            self.assertIs(merge(metadata_false, Empty, True), False)
            self.assertIs(merge(metadata_false, Empty, False), False)
            self.assertIs(merge(metadata_true, Empty, True), True)
            self.assertIs(merge(metadata_true, Empty, False), False)
        with self.subTest("non-empty base"):
            self.assertIs(merge(metadata_false, True, False), False)
            self.assertIs(merge(metadata_false, True, True), False)
            self.assertIs(merge(metadata_false, False, True), False)
            self.assertIs(merge(metadata_false, False, False), False)
            self.assertIs(merge(metadata_true, True, False), False)
            self.assertIs(merge(metadata_true, True, True), True)
            self.assertIs(merge(metadata_true, False, True), False)
            self.assertIs(merge(metadata_true, False, False), False)

    def test_merge_bool_or(self):
        metadata_false = {"_type": "bool", "_default": False, "_merge": "or"}
        metadata_true = {"_type": "bool", "_default": True, "_merge": "or"}
        with self.subTest("default fallback"):
            self.assertIs(merge(metadata_false, Empty, Empty), False)
            self.assertIs(merge(metadata_true, Empty, Empty), True)
        with self.subTest("base fallback"):
            self.assertIs(merge(metadata_false, True, Empty), True)
            self.assertIs(merge(metadata_false, False, Empty), False)
            self.assertIs(merge(metadata_true, True, Empty), True)
            self.assertIs(merge(metadata_true, False, Empty), True)
        with self.subTest("empty base"):
            self.assertIs(merge(metadata_false, Empty, True), True)
            self.assertIs(merge(metadata_false, Empty, False), False)
            self.assertIs(merge(metadata_true, Empty, True), True)
            self.assertIs(merge(metadata_true, Empty, False), True)
        with self.subTest("non-empty base"):
            self.assertIs(merge(metadata_false, True, False), True)
            self.assertIs(merge(metadata_false, True, True), True)
            self.assertIs(merge(metadata_false, False, True), True)
            self.assertIs(merge(metadata_false, False, False), False)
            self.assertIs(merge(metadata_true, True, False), True)
            self.assertIs(merge(metadata_true, True, True), True)
            self.assertIs(merge(metadata_true, False, True), True)
            self.assertIs(merge(metadata_true, False, False), True)

    def test_merge_nullable_replace(self):
        metadata = {"_type": "int", "_nullable": True, "_default": 1, "_merge": "replace"}
        with self.subTest("default fallback"):
            self.assertIs(merge(metadata, Empty, Empty), 1)
        with self.subTest("base fallback"):
            self.assertIs(merge(metadata, None, Empty), None)
        with self.subTest("empty base"):
            self.assertIs(merge(metadata, Empty, None), None)
        with self.subTest("non-empty base"):
            self.assertIs(merge(metadata, 2, None), None)

    def test_merge_enum_replace(self):
        metadata = {"_type": "enum", "_default": "foo", "_values": ["foo", "bar", "baz"], "_merge": "replace"}
        with self.subTest("default fallback"):
            self.assertEqual(merge(metadata, Empty, Empty), "foo")
        with self.subTest("base fallback"):
            self.assertEqual(merge(metadata, "bar", Empty), "bar")
        with self.subTest("empty base"):
            self.assertEqual(merge(metadata, Empty, "baz"), "baz")
        with self.subTest("non-empty base"):
            self.assertEqual(merge(metadata, "bar", "baz"), "baz")

    def test_merge_list_append(self):
        metadata = {"_type": "list", "_default": [1], "_items": {"_type": "int"}, "_merge": "append"}
        with self.subTest("default fallback"):
            self.assertEqual(merge(metadata, Empty, Empty), [1])
        with self.subTest("base fallback"):
            # note: we assume that base already merged in the values from default,
            # so we don't re-merge them inside of the call
            self.assertEqual(merge(metadata, [2], Empty), [2])
        with self.subTest("empty base"):
            self.assertEqual(merge(metadata, Empty, [3]), [1, 3])
        with self.subTest("non-empty base"):
            self.assertEqual(merge(metadata, [2], [3]), [2, 3])

    def test_merge_list_replace(self):
        metadata = {"_type": "list", "_default": [1], "_items": {"_type": "int"}, "_merge": "replace"}
        with self.subTest("default fallback"):
            self.assertEqual(merge(metadata, Empty, Empty), [1])
        with self.subTest("base fallback"):
            self.assertEqual(merge(metadata, [2], Empty), [2])
        with self.subTest("empty base"):
            self.assertEqual(merge(metadata, Empty, [3]), [3])
        with self.subTest("non-empty base"):
            self.assertEqual(merge(metadata, [2], [3]), [3])

    def test_merge_dict_merge(self):
        metadata = {
            "_type": "dict",
            "_merge": "merge",
            "_default": {
                "foo": {
                    "_type": "int",
                    "_default": 0
                },
                "bar": {
                    "_type": "str",
                    "_default": ""
                },
                "baz": {
                    "_type": "list",
                    "_default": [],
                    "_items": {
                        "_type": "float"
                    }
                }
            }}

        with self.subTest("default fallback"):
            self.assertEqual(merge(metadata, Empty, Empty), {"foo": 0, "bar": "", "baz": []})
        with self.subTest("base fallback"):
            self.assertEqual(merge(metadata, {"baz": [2.0]}, Empty), {"foo": 0, "bar": "", "baz": [2.0]})
            self.assertEqual(merge(metadata, {"foo": 1, "bar": "a", "baz": [2.0]}, Empty),
                             {"foo": 1, "bar": "a", "baz": [2.0]})
        with self.subTest("empty base"):
            self.assertEqual(merge(metadata, Empty, {"foo": 1, "bar": "a", "baz": [2.0]}),
                             {"foo": 1, "bar": "a", "baz": [2.0]})
            self.assertEqual(merge(metadata, Empty, {"bar": "a"}), {"foo": 0, "bar": "a", "baz": []})
        with self.subTest("non-empty base"):
            self.assertEqual(merge(metadata, {"foo": 1}, {"bar": "a"}), {"foo": 1, "bar": "a", "baz": []})

    def test_merge_dict_replace(self):
        metadata = {
            "_type": "dict",
            "_merge": "replace",
            "_default": {
                "foo": {
                    "_type": "int",
                    "_default": 0
                },
                "bar": {
                    "_type": "str",
                    "_default": ""
                },
                "baz": {
                    "_type": "list",
                    "_default": [],
                    "_items": {
                        "_type": "float"
                    }
                }
            }}

        with self.subTest("default fallback"):
            self.assertEqual(merge(metadata, Empty, Empty), {"foo": 0, "bar": "", "baz": []})
        with self.subTest("base fallback"):
            self.assertEqual(merge(metadata, {"baz": [2.0]}, Empty), {"foo": 0, "bar": "", "baz": [2.0]})
            self.assertEqual(merge(metadata, {"foo": 1, "bar": "a", "baz": [2.0]}, Empty),
                             {"foo": 1, "bar": "a", "baz": [2.0]})
        with self.subTest("empty base"):
            self.assertEqual(merge(metadata, Empty, {"foo": 1, "bar": "a", "baz": [2.0]}),
                             {"foo": 1, "bar": "a", "baz": [2.0]})
            self.assertEqual(merge(metadata, Empty, {"bar": "a"}), {"foo": 0, "bar": "a", "baz": []})
        with self.subTest("non-empty base"):
            # foo: 1 is replaced with the 3rd parameter so it falls back to default (0)
            self.assertEqual(merge(metadata, {"foo": 1}, {"bar": "a"}), {"foo": 0, "bar": "a", "baz": []})

    def test_merge_tagged_replace(self):
        metadata = {
            "_type": "tagged",
            "_merge": "replace",
            "_tags": {
                "int": {
                    "_type": "dict",
                    "_default": {
                        "intval": {
                            "_type": "int"
                        }
                    }
                },
                "str": {
                    "_type": "dict",
                    "_default": {
                        "strval": {
                            "_type": "str"
                        }
                    }
                }
            }
        }
        # no default fallback sub-test because base and settings both being Empty is an error for tagged types
        with self.subTest("base fallback"):
            self.assertEqual(merge(metadata, {"type": "int", "intval": 1}, Empty), {"type": "int", "intval": 1})
            self.assertEqual(merge(metadata, {"type": "str", "strval": "a"}, Empty), {"type": "str", "strval": "a"})
        with self.subTest("empty base"):
            self.assertEqual(merge(metadata, Empty, {"type": "int", "intval": 1}), {"type": "int", "intval": 1})
            self.assertEqual(merge(metadata, Empty, {"type": "str", "strval": "a"}), {"type": "str", "strval": "a"})
        with self.subTest("non-empty base"):
            self.assertEqual(merge(metadata, {"type": "int", "intval": 1}, {"type": "str", "strval": "a"}),
                             {"type": "str", "strval": "a"})
            self.assertEqual(merge(metadata, {"type": "str", "strval": "a"}, {"type": "int", "intval": 1}),
                             {"type": "int", "intval": 1})

    def test_merge_complex(self):
        metadata = {"_type": {"_type": "int", "_default": 1, "_merge": "replace"}}
        with self.subTest("default fallback"):
            self.assertEqual(merge(metadata, Empty, Empty), 1)
        with self.subTest("base fallback"):
            self.assertEqual(merge(metadata, 2, Empty), 2)
        with self.subTest("empty base"):
            self.assertEqual(merge(metadata, Empty, 3), 3)
        with self.subTest("non-empty base"):
            self.assertEqual(merge(metadata, 2, 3), 3)

    def test_merge_union(self):
        metadata = {"_type": ["int", "str"], "_nullable": True, "_default": None, "_merge": "replace"}
        with self.subTest("default fallback"):
            self.assertIs(merge(metadata, Empty, Empty), None)
        with self.subTest("base fallback"):
            self.assertEqual(merge(metadata, 2, Empty), 2)
            self.assertEqual(merge(metadata, "2", Empty), "2")
            self.assertIs(merge(metadata, None, Empty), None)
        with self.subTest("empty base"):
            self.assertEqual(merge(metadata, Empty, 3), 3)
            self.assertEqual(merge(metadata, Empty, "3"), "3")
            self.assertIs(merge(metadata, Empty, None), None)
        with self.subTest("non-empty base"):
            self.assertEqual(merge(metadata, 2, 3), 3)
            self.assertEqual(merge(metadata, "2", 3), 3)
            self.assertEqual(merge(metadata, None, 3), 3)
            self.assertIs(merge(metadata, 2, None), None)
            self.assertIs(merge(metadata, "2", None), None)
            self.assertIs(merge(metadata, None, None), None)

    def test_invalid_str(self):
        metadata = {"_type": "str"}
        with self.subTest("value required"):
            self.assertRaises(TypeError, merge, metadata, Empty, Empty)
        with self.subTest("invalid type"):
            self.assertRaises(TypeError, merge, metadata, Empty, 2)
            self.assertRaises(TypeError, merge, metadata, Empty, 2.0)
            self.assertRaises(TypeError, merge, metadata, Empty, [])
            self.assertRaises(TypeError, merge, metadata, Empty, {})
            self.assertRaises(TypeError, merge, metadata, Empty, True)
            self.assertRaises(TypeError, merge, metadata, Empty, None)

    def test_invalid_int(self):
        metadata = {"_type": "int"}
        with self.subTest("value required"):
            self.assertRaises(TypeError, merge, metadata, Empty, Empty)
        with self.subTest("invalid type"):
            self.assertRaises(TypeError, merge, metadata, Empty, "2")
            self.assertRaises(TypeError, merge, metadata, Empty, 2.0)
            self.assertRaises(TypeError, merge, metadata, Empty, [])
            self.assertRaises(TypeError, merge, metadata, Empty, {})
            self.assertRaises(TypeError, merge, metadata, Empty, True)
            self.assertRaises(TypeError, merge, metadata, Empty, None)

    def test_invalid_float(self):
        metadata = {"_type": "float"}
        with self.subTest("value required"):
            self.assertRaises(TypeError, merge, metadata, Empty, Empty)
        with self.subTest("invalid type"):
            # ints are also valid floats, so do not test for that here
            self.assertRaises(TypeError, merge, metadata, Empty, "2.0")
            self.assertRaises(TypeError, merge, metadata, Empty, [])
            self.assertRaises(TypeError, merge, metadata, Empty, {})
            self.assertRaises(TypeError, merge, metadata, Empty, True)
            self.assertRaises(TypeError, merge, metadata, Empty, None)

    def test_invalid_bool(self):
        metadata = {"_type": "bool"}
        with self.subTest("value required"):
            self.assertRaises(TypeError, merge, metadata, Empty, Empty)
        with self.subTest("invalid type"):
            self.assertRaises(TypeError, merge, metadata, Empty, 2)
            self.assertRaises(TypeError, merge, metadata, Empty, 2.0)
            self.assertRaises(TypeError, merge, metadata, Empty, [])
            self.assertRaises(TypeError, merge, metadata, Empty, {})
            self.assertRaises(TypeError, merge, metadata, Empty, "True")
            self.assertRaises(TypeError, merge, metadata, Empty, None)

    def test_invalid_nullable(self):
        metadata = {"_type": "int", "_nullable": True}
        with self.subTest("value required"):
            self.assertRaises(TypeError, merge, metadata, Empty, Empty)
        with self.subTest("invalid type"):
            self.assertRaises(TypeError, merge, metadata, Empty, "2")
            self.assertRaises(TypeError, merge, metadata, Empty, 2.0)
            self.assertRaises(TypeError, merge, metadata, Empty, [])
            self.assertRaises(TypeError, merge, metadata, Empty, {})
            self.assertRaises(TypeError, merge, metadata, Empty, True)
            self.assertRaises(TypeError, merge, metadata, Empty, "None")

    def test_invalid_enum(self):
        metadata = {"_type": "enum", "_values": ["foo", "bar", "baz"]}
        with self.subTest("value required"):
            self.assertRaises(TypeError, merge, metadata, Empty, Empty)
        with self.subTest("invalid value"):
            self.assertRaises(TypeError, merge, metadata, Empty, "qux")
        with self.subTest("invalid type"):
            self.assertRaises(TypeError, merge, metadata, Empty, 2)
            self.assertRaises(TypeError, merge, metadata, Empty, 2.0)
            self.assertRaises(TypeError, merge, metadata, Empty, [])
            self.assertRaises(TypeError, merge, metadata, Empty, {})
            self.assertRaises(TypeError, merge, metadata, Empty, True)
            self.assertRaises(TypeError, merge, metadata, Empty, None)

    def test_invalid_list(self):
        metadata = {"_type": "list", "_items": {"_type": "str"}}
        with self.subTest("value required"):
            self.assertRaises(TypeError, merge, metadata, Empty, Empty)
        with self.subTest("invalid item type"):
            self.assertRaises(TypeError, merge, metadata, Empty, [1])
            self.assertRaises(TypeError, merge, metadata, Empty, ["a", []])
        with self.subTest("invalid type"):
            self.assertRaises(TypeError, merge, metadata, Empty, 2)
            self.assertRaises(TypeError, merge, metadata, Empty, 2.0)
            self.assertRaises(TypeError, merge, metadata, Empty, "[]")
            self.assertRaises(TypeError, merge, metadata, Empty, {})
            self.assertRaises(TypeError, merge, metadata, Empty, True)
            self.assertRaises(TypeError, merge, metadata, Empty, None)

    def test_invalid_dict(self):
        metadata = {"_type": "dict", "_default": {"foo": {"_type": "int"}, "bar": {"_type": "str"}}}
        with self.subTest("value required"):
            self.assertRaises(TypeError, merge, metadata, Empty, Empty)
            self.assertRaises(TypeError, merge, metadata, Empty, {})
            self.assertRaises(TypeError, merge, metadata, Empty, {"foo": 1})
            self.assertRaises(TypeError, merge, metadata, Empty, {"bar": "a"})
        with self.subTest("invalid item type"):
            self.assertRaises(TypeError, merge, metadata, Empty, {"foo": "1", "bar": "2"})
            self.assertRaises(TypeError, merge, metadata, Empty, {"foo": 1, "bar": 2})
        with self.subTest("extraneous keys"):
            self.assertRaises(TypeError, merge, metadata, Empty, {"foo": 1, "bar": "2", "baz": 3.0})
        with self.subTest("invalid type"):
            self.assertRaises(TypeError, merge, metadata, Empty, 2)
            self.assertRaises(TypeError, merge, metadata, Empty, 2.0)
            self.assertRaises(TypeError, merge, metadata, Empty, [])
            self.assertRaises(TypeError, merge, metadata, Empty, "{}")
            self.assertRaises(TypeError, merge, metadata, Empty, True)
            self.assertRaises(TypeError, merge, metadata, Empty, None)

    def test_invalid_tagged(self):
        metadata = {
            "_type": "tagged",
            "_tags": {
                "int": {
                    "_type": "dict",
                    "_default": {"intval": {"_type": "int"}}
                },
                "str": {
                    "_type": "dict",
                    "_default": {"strval": {"_type": "str"}}
                }
            }
        }
        with self.subTest("value required"):
            self.assertRaises(TypeError, merge, metadata, Empty, Empty)
        with self.subTest("type required"):
            self.assertRaises(TypeError, merge, metadata, Empty, {})
            self.assertRaises(TypeError, merge, metadata, Empty, {"intval": 1})
        with self.subTest("invalid type"):
            self.assertRaises(TypeError, merge, metadata, Empty, {"type": "float"})
        with self.subTest("invalid typed value"):
            self.assertRaises(TypeError, merge, metadata, Empty, {"type": "int", "strval": "a"})
        with self.subTest("extraneous keys"):
            self.assertRaises(TypeError, merge, metadata, Empty, {"type": "int", "intval": 1, "strval": "a"})
        with self.subTest("invalid type"):
            self.assertRaises(TypeError, merge, metadata, Empty, 2)
            self.assertRaises(TypeError, merge, metadata, Empty, 2.0)
            self.assertRaises(TypeError, merge, metadata, Empty, [])
            self.assertRaises(TypeError, merge, metadata, Empty, "{}")
            self.assertRaises(TypeError, merge, metadata, Empty, True)
            self.assertRaises(TypeError, merge, metadata, Empty, None)

    def test_invalid_complex(self):
        metadata = {"_type": {"_type": "str"}}
        with self.subTest("value required"):
            self.assertRaises(TypeError, merge, metadata, Empty, Empty)
        with self.subTest("invalid type"):
            self.assertRaises(TypeError, merge, metadata, Empty, 2)
            self.assertRaises(TypeError, merge, metadata, Empty, 2.0)
            self.assertRaises(TypeError, merge, metadata, Empty, [])
            self.assertRaises(TypeError, merge, metadata, Empty, {})
            self.assertRaises(TypeError, merge, metadata, Empty, True)
            self.assertRaises(TypeError, merge, metadata, Empty, None)

    def test_invalid_union(self):
        metadata = {"_type": ["int", "str"]}
        with self.subTest("value required"):
            self.assertRaises(TypeError, merge, metadata, Empty, Empty)
        with self.subTest("invalid type"):
            self.assertRaises(TypeError, merge, metadata, Empty, 2.0)
            self.assertRaises(TypeError, merge, metadata, Empty, [])
            self.assertRaises(TypeError, merge, metadata, Empty, {})
            self.assertRaises(TypeError, merge, metadata, Empty, True)

    def test_constructors(self):
        metadata = {
            "_type": "dict",
            "_ctors": [
                {
                    "_type": "str",
                    "_set": "a"
                },
                {
                    "_type": "int",
                    "_set": "b"
                }
            ],
            "_default": {
                "a": {
                    "_type": "str"
                },
                "b": {
                    "_type": "int",
                    "_default": 3
                }
            }
        }
        with self.subTest("fully-specified"):
            self.assertEqual(merge(metadata, Empty, {"a": "foo", "b": 4}), {"a": "foo", "b": 4})
            self.assertEqual(merge(metadata, Empty, {"a": "foo"}), {"a": "foo", "b": 3})
        with self.subTest("using constructor"):
            self.assertEqual(merge(metadata, Empty, "foo"), {"a": "foo", "b": 3})
        with self.subTest("no matching constructor"):
            self.assertRaises(TypeError, merge, metadata, Empty, None)
        with self.subTest("poorly-specified constructor (metadata issue)"):
            self.assertRaises(TypeError, merge, metadata, Empty, 4)

    def test_default_multitype(self):
        metadata = {"_type": ["int", "float"], "_default": None}
        with self.subTest("first"):
            metadata["_default"] = 3
            test = merge(metadata, Empty, Empty)
            self.assertEqual(test, 3)
            self.assertIsInstance(test, int)
        with self.subTest("second"):
            metadata["_default"] = 2.7
            self.assertEqual(merge(metadata, Empty, Empty), 2.7)

    def test_coerce_int_to_float(self):
        metadata = {"_type": "float", "_default": None}
        with self.subTest("as default"):
            metadata["_default"] = 1
            test = merge(metadata, Empty, Empty)
            self.assertEqual(test, 1.0)
            self.assertIsInstance(test, float)
        with self.subTest("as base"):
            metadata["_default"] = 1.0
            test = merge(metadata, 2, Empty)
            self.assertEqual(test, 2.0)
            self.assertIsInstance(test, float)
        with self.subTest("as settings"):
            test = merge(metadata, Empty, 3)
            self.assertEqual(test, 3.0)
            self.assertIsInstance(test, float)
