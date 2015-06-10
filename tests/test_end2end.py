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
import json
import builtins
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from docker_cleanup import main


def past_time_isoformat(**kwargs):
    # Do not supply tzinfo here, otherwise isoformat() appends '+00:00'.
    now = datetime.utcnow()
    if now.microsecond == 0:
        now += timedelta(microseconds=1)
    return (now - timedelta(**kwargs)).isoformat()

# Deliberately include different numbers of digits in fractional seconds.
past_1h = past_time_isoformat(hours=1) + 'Z'
past_7d = past_time_isoformat(days=7) + '000Z'
past_9y = past_time_isoformat(days=9*365)[:-2] + 'Z'


e2e_call_docker_match_exact = {
    ('ps', '-aq'):
        'c1\nc2\nc22\n',
    ('images', '--no-trunc'):
        'REPOSITORY    TAG      IMAGE ID   CREATED       VIRTUAL SIZE\n'
        '<none>        <none>   i1         XY days ago   XYZ MB\n'
        'some/second   lt       i2         XY days ago   XYZ MB\n'
        '<none>        <none>   i3         XY days ago   XYZ MB',
    ('inspect', 'c1', 'c2', 'c22'): json.dumps([
        dict(Id='c1', Image='i1', Created=past_1h, Name='einstein'),
        dict(Id='c2', Image='i2', Created=past_9y, Name='podolsky'),
        dict(Id='c22', Image='i2', Created=past_7d, Name='rosen'),
        ]),
    ('inspect', 'i1', 'i2', 'i3'): json.dumps([
        dict(Id='i1', Created=past_1h),
        dict(Id='i2', Created=past_9y),
        dict(Id='i3', Created=past_7d),
        ]),
}
e2e_call_docker_match_command = {
    'rm': '',
    'rmi': '',
}

def make_fake_call_docker(match_exact, match_command):
    def fake_call_docker(*args):
        assert args in match_exact or args[0] in match_command
        if args in match_exact:
            return match_exact[args]
        return match_command[args[0]]
    return fake_call_docker


e2e_inputs = [
    ("DELETE CONTAINER IF Container.Id == 'c2';",                     ['c2'], []),
    ("DELETE IMAGE IF Image.Id == 'i2';",                             [],     ['i2']),
    ("DELETE IMAGE IF Image.Dangling;",                               [],     ['i3']),
    ("DELETE IMAGE IF Image.Created.before('1 year ago');",           [],     ['i2']),
    ("DELETE IMAGE IF Image.Created.before('2 years ago');",          [],     ['i2']),
]

@pytest.mark.end2end
@pytest.mark.parametrize("input,rm_expected,rmi_expected", e2e_inputs)
def test_do_cleanup_print_dry(input, rm_expected, rmi_expected,
                              mock_open_config, mock_call_docker):

    mock_open_config.stubbed_files['testconf.conf'] = io.StringIO(input)
    mock_call_docker.side_effect = make_fake_call_docker(
            e2e_call_docker_match_exact, e2e_call_docker_match_command)

    main.real_main(['--config', 'testconf.conf'])

    rm_seen = [args[1] for args, kwargs in mock_call_docker.call_args_list
                       if args[0] == 'rm']
    rmi_seen = [args[1] for args, kwargs in mock_call_docker.call_args_list
                        if args[0] == 'rmi']

    assert rm_seen == rm_expected
    assert rmi_seen == rmi_expected


def test_call_real_main_errors(mocker, capsys):
    err = subprocess.CalledProcessError(1, ['test-docker', 'args'])
    mocker.patch('subprocess.check_output', side_effect=err)

    with pytest.raises(SystemExit):
        main.real_main(['--dockerpath', 'test-docker', '-s', ''])

    out, err = capsys.readouterr()
    assert 'test-docker' in err
