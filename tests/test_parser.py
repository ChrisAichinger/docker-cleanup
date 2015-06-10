# Copyright 2015 Christian Aichinger <Greek0@gmx.net>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import io
import re
import tokenize

import pytest

from docker_cleanup import error, parser


class AttributeComparator:
    """Generic comparator compatible with arbitrary objects

    AttributeComparator objects are constructed with a *cls* argument and
    arbitrary keyword arguments and compare equal to all objects that are
    subclasses of *cls* and where the keyword arguments match the object's
    attributes::

        class A:
            pass

        a = A()
        a.x = 7
        a.y = 8

        assert a == AttributeComparator(A, x=7, y=8)
        assert a != AttributeComparator(A, x=7, y=9)
        assert a != AttributeComparator(dict, x=7, y=8)

        # None can be passed as *cls* if the class doesn't matter.
        assert a == AttributeComparator(None, x=7, y=8)

    Constructor arguments:
        cls: A class that other objects have to be subclasses of to compare
             True. If no subclass check is desired, None can be passed.
        **kwargs: Keyword arguments to be compared against other
                  object's dictionary.
    """

    _sentinel = object()

    def __init__(self, cls, **kwargs):
        self.cls = cls
        self.kwargs = kwargs

    def __eq__(self, other):
        if self.cls is not None and not isinstance(other, self.cls):
            return False

        for key in self.kwargs:
            other_value = getattr(other, key, self._sentinel)

            if other_value is self._sentinel:
                return False

            if other_value != self.kwargs[key]:
                return False

        return True

    def __neq__(self, other):
        return not self == other


def tok(s):
    bio = io.BytesIO(s.encode('utf-8'))
    tokens = list(tokenize.tokenize(bio.readline))

    # Strip ENCODING token.
    return tokens[1:]


#################################################
# Tests for ImportStatement
#################################################

no_imports = [
    "outport sys;",
    "DELETE IF True;",
    "7;",
    "'abc';",
]

@pytest.mark.parametrize("input", no_imports)
def test_ImportStatement_try_parse_None(input):
    assert parser.ImportStatement.try_parse(tok(input)) is None


valid_imports = [
    ('IMPORT sys;', ['sys']),
    ('IMPORT os.path;', ['os.path']),
    ('IMPORT sys, os.path;', ['sys', 'os.path']),
]

@pytest.mark.parametrize("input,expected", valid_imports)
def test_ImportStatement_valid(input, expected):
    smt = parser.ImportStatement.try_parse(tok(input))
    assert smt.imports == expected


invalid_imports = [
    "IMPORT",
    "IMPORT sys",
    "IMPORT \n;",
    "IMPORT sys\n;",
    "IMPORT ;",
    "IMPORT .;",
    "IMPORT ..;",
    "IMPORT sys os;",
    "IMPORT 7;",
    "IMPORT 'abc';",
]

@pytest.mark.parametrize("input", invalid_imports)
def test_ImportStatement_invalid(input):
    tokens = tok(input)
    with pytest.raises(error.RuleParseError):
        parser.ImportStatement.try_parse(tokens)


#################################################
# Tests for ImportStatement
#################################################

no_deletes = [
    "IMPORT sys;",
    "FORCE nothing;",
    "FORCE IMAGE IF True;",
    "FORCE CONTAINER IF True;",
    "IMAGE IF True;",
    "CONTAINER IF True;",
    "7;",
    "'abc';",
]

@pytest.mark.parametrize("input", no_deletes)
def test_DeleteStatement_try_parse_None(input):
    assert parser.ExpressionStatement.try_parse(tok(input)) is None


# Should de-duplicate if more entries are added.
valid_deletes = [
    ('DELETE IMAGE IF True;',              'image', 'True'),
    ('DELETE IMAGE IF image.Attr;',        'image', 'image.Attr'),
    ('DELETE IMAGE IF image.Name == "A";', 'image', 'image.Name == "A"'),

    ('DELETE IMAGE IF image.Name == "A" and image.Attr;', 'image',
                     'image.Name == "A" and image.Attr'),
    ('DELETE IMAGE IF image.Name == "A" and\n        image.Attr;', 'image',
                     'image.Name == "A" and\n        image.Attr'),
]
valid_deletes += [(smt.replace('DELETE', 'KEEP'), etype, eexpr)
                  for smt, etype, eexpr in valid_deletes]
valid_deletes += [('FORCE ' + smt, etype, eexpr)
                  for smt, etype, eexpr in valid_deletes]
valid_deletes += [
    (smt.replace('IMAGE', 'CONTAINER').replace('image', 'container'),
     'container',
     eexpr.replace('image', 'container'))
    for smt, etype, eexpr in valid_deletes]

@pytest.mark.parametrize("input,expected_type,expected_expr", valid_deletes)
def test_DeleteStatement_valid(input, expected_type, expected_expr):
    smt = parser.ExpressionStatement.try_parse(tok(input))

    str_expr = tokenize.untokenize(smt.expr).strip()

    assert smt.type == expected_type
    assert str_expr == expected_expr


invalid_deletes = [
    "DELETE;",
    "DELETE IMAGE;",
    "DELETE IMAGE IF;",
    "DELETE IMAGE IF True",
    "DELETE ME IF True;",
    "DELETE IMAGE IF image.x == 7\nDELETE;",
    "DELETE IMAGE IF image.x == 7\nFORCE DELETE;",
    "DELETE IMAGE IF image.x == 7\nIMPORT sys;",
    "DELETE IMAGE IF image.x == 'ab\ncd';",
    'DELETE IMAGE IF image.x == "ab\ncd";',
    "DELETE IMAGE IF image.x == §;",
]
invalid_deletes += [smt.replace('DELETE', 'KEEP') for smt in invalid_deletes]
invalid_deletes += ['FORCE ' + smt for smt in invalid_deletes]
invalid_deletes += [
    smt.replace('IMAGE', 'CONTAINER').replace('image', 'container')
    for smt in invalid_deletes]

@pytest.mark.parametrize("input", invalid_deletes)
def test_DELETEStatement_invalid(input):
    tokens = tok(input)
    with pytest.raises(error.RuleParseError):
        # These test inputs must be valid enough for try_parse to succeed, so
        # ExpressionStatement(...) is called.
        # Test cases for try_parse are above.
        assert parser.ExpressionStatement.try_parse(tokens) is not None


#################################################
# Tests for Parser
#################################################

valid_parser_inputs = [
    ("""""", []),
    ("""  \n  """, []),
    ("""# Comment""", []),
    ("""# Comment\n\n\n  # Another comment""", []),
    ("""
     IMPORT sys;
     FORCE DELETE IMAGE IF image.Dangling;
     FORCE DELETE CONTAINER IF not container.Running;
     """,
     [AttributeComparator(parser.ImportStatement),
      AttributeComparator(parser.ExpressionStatement, force=True),
      AttributeComparator(parser.ExpressionStatement, force=True),
      ]),
    ("""
     DELETE IMAGE IF (None);
     """,
     [AttributeComparator(parser.ExpressionStatement, force=False)]),
]
@pytest.mark.parametrize("input,statements", valid_parser_inputs)
def test_Parser_valid(input, statements):
    p = parser.Parser(input)
    assert p.statements == statements


invalid_parser_inputs = [
    "§",
    "'ab\ncd'",
    '"ab\ncd"',
]
@pytest.mark.parametrize("input", invalid_parser_inputs)
def test_Parser_invalid(input):
    with pytest.raises(error.RuleParseError):
        parser.Parser(input)

parser_input_exceptions = [
    ("DELETE IMAGE IF (;", '(', (1, 16)),
    ("DELETE IMAGE IF );", ')', (1, 16)),
    ("DELETE IMAGE IF [;", '[', (1, 16)),
    ("DELETE IMAGE IF ];", ']', (1, 16)),
    ("DELETE IMAGE IF {;", '{', (1, 16)),
    ("DELETE IMAGE IF };", '}', (1, 16)),
    ("DELETE IMAGE IF ''';", "'", (1, 16)),
    ('DELETE IMAGE IF """;', '"', (1, 16)),

    ("DELETE IMAGE IF (();", '(', (1, 16)),
    ("DELETE IMAGE IF )();", ')', (1, 16)),
    ("DELETE IMAGE IF ()(;", '(', (1, 18)),
    ("DELETE IMAGE IF ());", ')', (1, 18)),

    ("DELETE IMAGE;", ';', (1, 12)),
]

@pytest.mark.parametrize("input,char,pos", parser_input_exceptions)
def test_Parser_exceptions(input, char, pos):
    with pytest.raises(error.RuleParseError) as excinfo:
        parser.Parser(input)

    assert excinfo.value.token.string == char
    assert excinfo.value.token.start == pos

