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
import builtins
import logging

import pytest

from docker_cleanup import main


def test_parse_args():
    args = main.parse_args(['--dry-run'])
    assert args.dry_run

    args = main.parse_args([])
    assert args.loglevel >= logging.WARN

    args = main.parse_args(['-vvv'])
    assert args.loglevel <= logging.DEBUG


def test_cleanup_config_fname(mocker):
    open = mocker.patch('builtins.open', return_value=io.StringIO(''))
    args = main.parse_args('-c myconf.conf --dry-run'.split())

    main.cleanup(args, [], [])

    open.assert_called_once_with('myconf.conf', 'r')


do_cleanup_inputs = [
    ('DELETE CONTAINER IF Container.Id == "c2";', 'c2', False),
    ('DELETE IMAGE IF Image.Id == "i2";', 'i2', False),
    ('FORCE DELETE CONTAINER IF Container.Id == "c2";', 'c2', True),
    ('FORCE DELETE IMAGE IF Image.Id == "i2";', 'i2', True),
]

@pytest.mark.parametrize("use_statements_arg", [True, False])
@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("input,id,force", do_cleanup_inputs)
def test_do_cleanup_print_dry(input, id, force, dry_run, use_statements_arg,
                              containers, images, mocker, capsys):

    sentinel = object()
    if force:
        regex = r'^Force deleting.*\W%s\W' % id
    else:
        regex = r'^Deleting.*\W%s\W' % id

    delimg = mocker.patch('docker_cleanup.docker.delete_image')
    delcnt = mocker.patch('docker_cleanup.docker.delete_container')

    args = main.parse_args(['--dry-run'] if dry_run else [])
    if use_statements_arg:
        args.statements = input
    else:
        args.config = io.StringIO(input)

    main.cleanup(args, containers, images)

    out, err = capsys.readouterr()
    assert re.search(regex, out, re.MULTILINE)
    assert not err

    if dry_run:
        assert delimg.call_count == 0
        assert delcnt.call_count == 0
    else:
        if id.startswith('i'):
            assert delimg.call_count == 1
            assert delcnt.call_count == 0
            call_args, call_kwargs = delimg.call_args
        else:
            assert delimg.call_count == 0
            assert delcnt.call_count == 1
            call_args, call_kwargs = delcnt.call_args

        assert len(call_args) <= 2
        assert call_args[0].Id == id
        assert (call_args[1:] == (force,) or
                call_kwargs.get('force', sentinel) == force)


def test_open_rules_filenotfound(mock_open_config, capsys):
    mock_open_config.stubbed_files['testconf.conf'] = None
    args = main.parse_args('-c testconf.conf'.split())

    with pytest.raises(SystemExit):
        with main.open_rules(args):
            pass

    out, err = capsys.readouterr()
    assert 'testconf.conf' in err
