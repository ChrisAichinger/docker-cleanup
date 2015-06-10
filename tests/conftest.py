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
import errno
import logging

import pytest

from docker_cleanup import docker


def pytest_addoption(parser):
    parser.addoption("--no-e2e", action="store_true",
                     help="disable end-to-end tests")
    parser.addoption("--debuglog", action="store_true",
                     help="enable logging output")


def pytest_runtest_setup(item):
    if 'end2end' in item.keywords and item.config.getoption("--no-e2e"):
        pytest.skip("disabled with the --no-e2e option")


def pytest_configure(config):
    if config.getoption('--debuglog'):
        logging.basicConfig(level=logging.DEBUG)


@pytest.fixture
def images():
    return [docker.Image({'Id': 'i1', 'Repository': None, 'Tag': None}),
            docker.Image({'Id': 'i2', 'Repository': None, 'Tag': None}),
            docker.Image({'Id': 'i3', 'Repository': None, 'Tag': None}),
            ]


@pytest.fixture
def containers():
    return [docker.Container({'Id': 'c1',  'Image': 'i1', 'Name': 'wild'}),
            docker.Container({'Id': 'c2',  'Image': 'i2', 'Name': 'freaking'}),
            docker.Container({'Id': 'c22', 'Image': 'i2', 'Name': 'boar'}),
            ]


@pytest.fixture()
def mock_call_docker(mocker):
    return mocker.patch('docker_cleanup.docker.call_docker')


@pytest.fixture()
def mock_open_config(mocker):
    orig_open = io.open
    mock_open = mocker.patch('io.open')
    mocker.patch('builtins.open', mock_open)

    def side_effect(file, mode='r', *args, **kwargs):
        if file in mock_open.stubbed_files:
            assert mode == 'r'
            if mock_open.stubbed_files[file] is None:
                raise FileNotFoundError(
                        errno.ENOENT, 'No such file or directory', file)
            return mock_open.stubbed_files[file]

        return orig_open(file, mode, *args, **kwargs)

    mock_open.stubbed_files = {}
    mock_open.side_effect = side_effect
    return mock_open
