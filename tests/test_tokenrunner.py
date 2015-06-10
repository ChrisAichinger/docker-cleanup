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
import tokenize
import itertools

import pytest

from docker_cleanup import tokenrunner


def tok(s):
    bio = io.BytesIO(s.encode('utf-8'))
    tokens = list(tokenize.tokenize(bio.readline))

    # Strip ENCODING token.
    return tokens[1:]


#################################################
# Tests for Executor
#################################################

valid_executor_inputs = [
    ('', None),
    ('True', True),
    ('42', 42),
    ('"abc"', "abc"),
    ('(1,\n2)', (1, 2)),
    ('1 + 2', 3),
    ('1 +\n 2', 3),
]

@pytest.mark.parametrize("input,expected", valid_executor_inputs)
def test_Executor_valid(input, expected):
    tokens = tok(input)
    ex = tokenrunner.Executor(tokens)
    result = ex.run()

    assert result == expected


def test_Executor_globals():
    ex = tokenrunner.Executor(tok('number + 32'))
    context = dict(number=10)

    result = ex.run(context)

    assert result == 42


def add_offsets(table, offsets):
    return [(input, etype, lineno, offset)
            for (input, etype, lineno), offset
            in itertools.product(table, offsets)]


executor_run_exceptions = [
    ('True) and (True',       None, 1),
    ('(}',                    None, 1),
    ('{)',                    None, 1),
    ('(]',                    None, 1),
    ('[)',                    None, 1),

    ('1 + \nTrue) and (True', None, 2),
    ('1 + \n(}',              None, 2),
    ('1 + \n{)',              None, 2),
    ('1 + \n(]',              None, 2),
    ('1 + \n[)',              None, 2),

    ('1/0',                   ZeroDivisionError, 1),
    ('(1 + \n 1/0)',          ZeroDivisionError, 2),
    ('(1 + \n\n 1/0)',        ZeroDivisionError, 3),
    ('1 + \n 1/0',            ZeroDivisionError, 2),
    ('1 + \n\n 1/0',          ZeroDivisionError, 3),
]

@pytest.mark.parametrize("input,etype,lineno,offset",
                         add_offsets(executor_run_exceptions, [0, 42]))
def test_Executor_exceptions(input, etype, lineno, offset):
    tokens = tok(input)

    with pytest.raises(tokenrunner.RuleExecutionError) as excinfo:
        ex = tokenrunner.Executor(tokens, line_offset=offset)
        ex.run()

    assert excinfo.value.token.start[0] == lineno + offset
    if etype:
        assert isinstance(excinfo.value.__cause__, etype)


@pytest.mark.parametrize("paren", ['(', ')'])
def test_Executor_init_exceptions_manual(paren):
    # The tokenize module can't handle unmatched parens, create them manually.
    with pytest.raises(tokenrunner.RuleExecutionError):
        tokenrunner.Executor([tokenize.TokenInfo(
                tokenize.OP, paren, (1,0), (1,1), paren)])
