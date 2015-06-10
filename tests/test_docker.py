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

import subprocess
from datetime import datetime, timedelta, timezone

from dateutil.tz import tzutc

import pytest
from unittest.mock import call

from docker_cleanup import dates, docker, error
import test_dates


def test_AttrDict():
    json = [{'dct': dict(b=7),
             'lst': [dict()],
            }
           ]

    json_ad = docker.AttrDict.from_json(json)

    assert json == json_ad

    assert isinstance(json_ad[0], docker.AttrDict)
    assert isinstance(json_ad[0].dct, docker.AttrDict)
    assert isinstance(json_ad[0].lst[0], docker.AttrDict)

    assert 'AttrDict' in repr(json_ad)



@pytest.mark.parametrize("cls", [docker.DockerObj,
                                 docker.Container,
                                 docker.Image])
@pytest.mark.parametrize("input,expected", test_dates.date_time_pairs)
def test_DockerObj(input, expected, cls):
    obj = cls({'Id': '2468',
               'Name': 'roger',
               'Repository': 'jack',
               'Tag': 'jill',
               'Unrelated': '\o/',
               'Created': input,
               'State': {'Unrelated': '...',
                         'StartedAt': input,
                         'FinishedAt': input,
                         },
               })

    assert obj.Id == '2468'
    assert obj.Name == 'roger' or obj.Name == 'jack:jill'
    assert obj.Unrelated == '\o/'
    assert obj.State.Unrelated == '...'
    assert obj.Created == expected
    assert obj.State.StartedAt == expected
    assert obj.State.FinishedAt == expected

    if obj.Created is not None:
        assert isinstance(obj.Created, dates.DateTime)
    if obj.State.StartedAt is not None:
        assert isinstance(obj.State.StartedAt, dates.DateTime)
    if obj.State.FinishedAt is not None:
        assert isinstance(obj.State.FinishedAt, dates.DateTime)

    assert '2468' in str(obj)
    assert 'roger' in str(obj) or 'jack:jill' in str(obj)


dockerobj_equals = [
    (docker.DockerObj({'Id': '123'}), docker.DockerObj({'Id': '123'}), True),
    (docker.DockerObj({'Id': '123'}), docker.DockerObj({'Id': '000'}), False),
    (docker.DockerObj({'Id': '123'}), docker.Container({'Id': '123'}), False),
    (docker.DockerObj({'Id': '123'}), docker.Image({'Id': '123'}),     False),
    (docker.Container({'Id': '123'}), docker.Image({'Id': '123'}),     False),
    (docker.Container({'Id': '123'}), docker.Image({'Id': '123'}),     False),

    (docker.DockerObj({'Id': '123'}), '123',                           True),
    (docker.Container({'Id': '123'}), '123',                           True),
    (docker.Image({'Id': '123'}),     '123',                           True),

    (docker.DockerObj({'Id': '123'}), '000',                           False),
    (docker.Container({'Id': '123'}), '000',                           False),
    (docker.Image({'Id': '123'}),     '000',                           False),
]

@pytest.mark.parametrize("input1,input2,expected", dockerobj_equals)
def test_DockerObj_eq(input1, input2, expected):
    assert (input1 == input2) == expected

@pytest.mark.parametrize("input,expected", test_dates.date_time_pairs)
def test_DockerObj_fixup_date(input, expected):
    d_input = {'value1': 'abc',
               'value2': '18',
               'value3': '2001-01-31T13:05:20.123456Z',
               'value4': input,
               }
    d_expected = dict(d_input)
    d_expected['value4'] = expected

    docker.DockerObj._fixup_date(d_input, 'value4')
    assert d_input == d_expected


def test_DockerObj_fixup_date_cornercases():
    d_input = {'an-int': 18,
               'none': None,
               }
    d_expected = dict(d_input)

    # Should not raise any exceptions
    docker.DockerObj._fixup_date(d_input, 'not-present')
    docker.DockerObj._fixup_date(d_input, 'an-int')
    docker.DockerObj._fixup_date(d_input, 'none')

    assert d_input == d_expected


def test_Container():
    c = docker.Container(
            {'Id': 'deadbeef',
             'Name': '/the_slash',
             })

    # Names coming out from `docker inspect` start with a '/'.
    # Test successful slash removal.
    assert c.Name == 'the_slash'


def test_Image():
    dangling_img = docker.Image(
            {'Id': 'deadbeef',
             'Repository': None,
             'Tag': None,
             })
    normal_img = docker.Image(
            {'Repository': 'some/thing',
             'Tag': 'latest',
             })

    assert dangling_img.Id == 'deadbeef'
    assert dangling_img.Repository is None
    assert dangling_img.Tag is None
    assert dangling_img.Dangling
    assert dangling_img.Name == '<none>:<none>'

    assert normal_img.Repository == 'some/thing'
    assert normal_img.Tag == 'latest'
    assert normal_img.Name == 'some/thing:latest'


def test_crossreference(containers, images):
    docker.cross_reference(containers, images)

    c1, c2, c22 = containers
    i1, i2, i3 = images

    assert c1.Image == i1
    assert c2.Image == i2
    assert c22.Image == i2

    assert i1.ContainerObjects == {c1}
    assert i2.ContainerObjects == {c2, c22}
    assert i3.ContainerObjects == set()

    assert not i1.Dangling
    assert not i2.Dangling
    assert i3.Dangling


def test_call_docker_errors(mocker):
    err = subprocess.CalledProcessError(1, ['cmdline', 'args'])
    mocker.patch('subprocess.check_output', side_effect=err)

    with pytest.raises(error.DockerError):
        docker.call_docker('images')


images_output_test_pairs = [
    ('REPOSITORY   TAG      IMAGE ID       CREATED       VIRTUAL SIZE\n'
     'some/th      latest   0123456789AB   2 hours ago   385.8 MB',

     [docker.DockerImagesRepoInfo(
         {'REPOSITORY': 'some/th',
          'TAG': 'latest',
          'IMAGE ID': '0123456789AB',
          })
      ]
    ),
    ('REPOSITORY   TAG      IMAGE ID       CREATED       VIRTUAL SIZE\n'
     '<none>       <none>   0987654321AB   2 hours ago   385.8 MB\n'
     'some/other   lt       0123456789AB   2 hours ago   385.8 MB',

     [docker.DockerImagesRepoInfo(
         {'REPOSITORY': '<none>',
          'TAG': '<none>',
          'IMAGE ID': '0987654321AB',
          }),
      docker.DockerImagesRepoInfo(
          {'REPOSITORY': 'some/other',
           'TAG': 'lt',
           'IMAGE ID': '0123456789AB',
           }),
      ]
    ),
]


@pytest.mark.parametrize("input,expected", images_output_test_pairs)
def test_parse_docker_images_output(input, expected):
    imagesdata = list(docker._parse_docker_images_output(input))

    assert len(imagesdata) == len(expected)
    for entry, entry_expected in zip(imagesdata, expected):
        assert entry.id == entry_expected.id
        assert entry.repo == entry_expected.repo
        assert entry.tag == entry_expected.tag


def test_load_inspect_json(mock_call_docker):
    id = '81834'
    mock_call_docker.return_value = '{"Id": "%s", "Name": "bingo"}' % id

    json = docker._load_docker_inspect_json([id])

    assert json['Id'] == id
    assert json['Name'] == 'bingo'


def test_load_containers(mock_call_docker):
    id = '81835'
    mock_call_docker.side_effect = [
        id,
        '[{ "Id": "%s",  "Name": "bingo" }]' % id
    ]

    containers = docker.load_containers()

    assert len(containers) == 1

    container = containers[0]
    assert container.Id == id
    assert container.Name == 'bingo'

    mock_call_docker.assert_has_calls([
        call('ps', '-aq'),
        call('inspect', id),
    ])


def test_load_images(mock_call_docker):
    mock_call_docker.side_effect = [
        images_output_test_pairs[0][0],
        '[{ "Id": "0123456789AB",  "Comment": "testcomment" }]'
    ]

    images = docker.load_images()

    assert len(images) == 1

    image = images[0]
    assert image.Repository == 'some/th'
    assert image.Tag == 'latest'
    assert image.Name == 'some/th:latest'
    assert image.Id == '0123456789AB'
    assert image.Comment == 'testcomment'

    mock_call_docker.assert_has_calls([
        call('images', '--no-trunc'),
        call('inspect', '0123456789AB'),
    ])


def test_delete_container(mock_call_docker):
    container = docker.Container(dict(Id='c0'))

    docker.delete_container(container)
    mock_call_docker.assert_called_once_with('rm', 'c0')

    mock_call_docker.reset_mock()
    docker.delete_container(container, force=True)
    mock_call_docker.assert_called_once_with('rm', '-f', 'c0')


def test_delete_container_del_ImageRef(mock_call_docker, images, containers):
    docker.cross_reference(containers, images)

    container = containers[0]
    assert container in container.Image.ContainerObjects

    docker.delete_container(container)

    assert container not in container.Image.ContainerObjects


def test_delete_image(mock_call_docker):
    image = docker.Image(dict(Id='i0'))

    docker.delete_image(image)
    mock_call_docker.assert_called_once_with('rmi', 'i0')

    mock_call_docker.reset_mock()
    docker.delete_image(image, force=True)
    mock_call_docker.assert_called_once_with('rmi', '-f', 'i0')
