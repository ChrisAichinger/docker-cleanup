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

import sys
import io

import pytest

from docker_cleanup import docker, rulefile, error
from docker_cleanup.rulefile import RuleAction

from test_parser import AttributeComparator


processor_valid = [
    ('', RuleAction.keep, {
        'Image': AttributeComparator(docker.Image),
    }),
    ('IMPORT sys;', RuleAction.keep, {
        'Image': AttributeComparator(docker.Image),
        'sys': sys,
    }),
    ('DELETE CONTAINER IF True;', RuleAction.keep, {
        'Image': AttributeComparator(docker.Image),
    }),
    ('DELETE IMAGE IF True;', RuleAction.delete, {
        'Image': AttributeComparator(docker.Image),
    }),
    ('DELETE IMAGE IF Image.Id;', RuleAction.delete, None),
    ('KEEP IMAGE IF True; DELETE IMAGE IF True;', RuleAction.keep, None),
    ('FORCE DELETE IMAGE IF True;', RuleAction.force_delete, None),
]


@pytest.mark.parametrize("input,expected_result,expected_ctx", processor_valid)
def test_RuleFile(input, expected_result, expected_ctx):
    f = io.StringIO(input)
    img = docker.Image({'Id': 'i1', 'Repository': None, 'Tag': None})
    ctx = dict()

    result = rulefile.RuleFile(f).can_delete(img, context=ctx)

    assert result == expected_result
    if expected_ctx is not None:
        assert ctx == expected_ctx


processor_invalid = [
    ('DELETE IMAGE;', 1),
    ('DELETE IMAGE IF 1/0;', 1),
    ('\nDELETE IMAGE IF 1/0;', 2),
    ('DELETE IMAGE IF 1 + \n    1/0;', 2),
]

@pytest.mark.parametrize("input,err_lineno", processor_invalid)
def test_RuleFile_invalid(input, err_lineno):
    f = io.StringIO(input)
    img = docker.Image({'Id': 'i1', 'Repository': None, 'Tag': None})
    ctx = dict()

    with pytest.raises(error.RulesError) as excinfo:
        rulefile.RuleFile(f).can_delete(img, context=ctx)

    assert excinfo.value.lineno == err_lineno
