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

"""An interface to Docker

Interface with Docker via its commandline executable. Provide access
to container and image metadata and allow deletion of containers and images.

Attributes:
    DOCKER (str): The docker executable to invoke. Set this to force usage
                  of a different docker binary.
"""

import sys
import re
import json
import subprocess
import collections

from . import error
from .dates import parse_date


DOCKER = 'docker'
DOCKER_IMAGES_HDR_REPO = 'REPOSITORY'
DOCKER_IMAGES_HDR_TAG = 'TAG'
DOCKER_IMAGES_HDR_ID = 'IMAGE ID'
DOCKER_NULL_VALUE = '<none>'


class AttrDict(dict):
    """A dict-like object for accessing keys via attributes

    Usage: d.key instead of d['key'].
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self

    def __repr__(self):
        return "%s(%s)" % (type(self).__name__,
                           super().__repr__())

    @classmethod
    def _convert_children(cls, obj):
        """Recursively convert children to AttrDict's"""
        def make_iter(dict_or_list):
            if isinstance(dict_or_list, dict):
                return dict_or_list.items()
            if isinstance(dict_or_list, list):
                return enumerate(dict_or_list)
            raise NotImplementedError(  # pragma: no cover
                    'Can only AttrDict-ify lists and dicts', dict_or_list)

        for key, value in make_iter(obj):
            if isinstance(value, (dict, list)):
                obj[key] = cls.from_json(value)

    @classmethod
    def from_json(cls, obj):
        """Create a new AttrDict from a JSON object (dict or list)

        This operation is recursive, i.e. sub-dicts will be transformed
        to AttrDict's as well.
        """

        if isinstance(obj, dict) and not isinstance(obj, cls):
            obj = cls(obj)

        cls._convert_children(obj)

        return obj


class DockerObj(AttrDict):
    """A base class for Docker images and containers"""

    def __init__(self, json):
        super().__init__(json)

        # Turn all sub-dicts into AttrDict instances.
        AttrDict._convert_children(self)

        # Convert date strings to dates.DateTime objects.
        self._fixup_date(self, 'Created')
        if 'State' in self:
            self._fixup_date(self['State'], 'StartedAt')
            self._fixup_date(self['State'], 'FinishedAt')

    @staticmethod
    def _fixup_date(item, name):
        """Replace item[name] with it's DateTime equivalent

        Set item[name] to parse_date(item[name]).
        """

        if name not in item:
            return
        if not isinstance(item[name], str):
            return

        item[name] = parse_date(item[name])

    def __hash__(self):
        return hash(self.Id)

    def __str__(self):
        objtype = type(self).__name__.lower()
        name = self.Name
        return "%s %s (%s)" % (objtype, name, self.Id[:12])

    def __eq__(self, other):
        # The super call returns NotImplemented for unsupported comparisons.
        # This is required for not breaking tests using AttributeComparator.
        return ((type(self) == type(other) and self.Id == other.Id) or
                (isinstance(other, str) and self.Id == other) or
                super().__eq__(other))

    def __neq__(self, other):
        return not self == other


class Container(DockerObj):
    """Encapsulate data about a Docker container"""
    def __init__(self, json):
        super().__init__(json)
        self.setdefault('Image', None)

        # Container names from `docker inspect` start with a /.
        # This isn't what users would expect, as Docker doesn't show the slash.
        if hasattr(self, 'Name') and self.Name.startswith('/'):
            self.Name = self.Name[1:]


class Image(DockerObj):
    """Encapsulate data about a Docker image"""
    def __init__(self, json):
        super().__init__(json)
        self.ContainerObjects = set()

    @property
    def Dangling(self):
        """True if the image is not referenced by a container and does not
           have a repository name.
        """

        return not self.ContainerObjects and not self.Repository

    @property
    def Name(self):
        """The full friendly name of the image: repository:tag"""
        repo = self.Repository if self.Repository else DOCKER_NULL_VALUE
        tag = self.Tag if self.Tag else DOCKER_NULL_VALUE
        return ''.join([repo, ':', tag])


class DockerImagesRepoInfo:
    """Associate repository and tag information with Docker image ids

    Attributes:
        id (str): The image id.
        repo (Optional[str]): The image repository name, or ``None`` if no
                              repository name was set in Docker.
        tag (Optional[str]): The image tag name, or ``None`` if no tag was set
                             in Docker.
    """

    def __init__(self, data_dict):
        self.id =   data_dict[DOCKER_IMAGES_HDR_ID]
        self.repo = data_dict[DOCKER_IMAGES_HDR_REPO]
        self.tag =  data_dict[DOCKER_IMAGES_HDR_TAG]

        if self.repo == DOCKER_NULL_VALUE:
            self.repo = None
        if self.tag == DOCKER_NULL_VALUE:
            self.tag = None


def _parse_docker_images_output(docker_images_output):
    """Obtain repository/tag information from ``docker images`` output"""
    header, *lines = docker_images_output.split('\n')

    # Word at the start of string or word preceded by two spaces.
    col_matches = re.finditer(r'^\w+|(?<=\s\s)\w+', header)
    col_starts = [c.start() for c in col_matches]
    col_ends = col_starts[1:] + [None]
    cols = [slice(start, end) for start, end in zip(col_starts, col_ends)]

    keys = [header[sl].strip() for sl in cols]

    for line in lines:
        line = line.strip()
        if not line:
            continue

        values = (line[sl].strip() for sl in cols)
        yield DockerImagesRepoInfo(dict(zip(keys, values)))


def call_docker(*args):
    """Run Docker with the supplied arguments and return its output"""
    cmd = [DOCKER] + list(args)
    try:
        return subprocess.check_output(cmd, universal_newlines=True)
    except subprocess.CalledProcessError as e:
        raise error.DockerError("Docker command %r failed with exit code %d." %
                                (' '.join(cmd), e.returncode)) from e


def _load_docker_inspect_json(ids):
    """Obtain data from ``docker inspect``

    Run ``docker inspect`` on the supplied ``ids`` and parse JSON output and
    return it.

    Arguments:
        ids (List[str]): A list of Docker container or image id's.
    """

    metadata = call_docker('inspect', *ids)
    return json.loads(metadata)

def load_containers():
    """Load ``Container`` objects from Docker"""
    ids = call_docker('ps', '-aq').split()
    return [Container(c) for c in _load_docker_inspect_json(ids)]

def load_images():
    """Load ``Image`` objects from Docker"""
    images_output = call_docker('images', '--no-trunc')
    image_repo_info = list(_parse_docker_images_output(images_output))
    ids = [ri.id for ri in image_repo_info]
    id_repo_map = dict(zip(ids, image_repo_info))

    json = _load_docker_inspect_json(ids)

    for entry in json:
        repo_entry = id_repo_map[entry['Id']]
        entry['Repository'] = repo_entry.repo
        entry['Tag'] = repo_entry.tag

    return [Image(i) for i in json]


def delete_container(container, force=False):
    """Delete a Docker container"""
    if force:
        call_docker('rm', '-f', container.Id)
    else:
        call_docker('rm', container.Id)

    # Remove backlink from the image to the deleted container.
    # May make the image dangling and eligible for removal.
    if container.Image and isinstance(container.Image, Image):
        container.Image.ContainerObjects.remove(container)


def delete_image(image, force=False):
    """Delete a Docker image"""
    if force:
        call_docker('rmi', '-f', image.Id)
    else:
        call_docker('rmi', image.Id)


def cross_reference(containers, images):
    """Cross-reference containers and images

    Add an ``Image`` attribute to containers.
    Add a ``ContainerObjects`` list to images.
    """

    image_map = {i.Id: i for i in images}
    for c in containers:
        image = image_map[c.Image]
        image.ContainerObjects.add(c)

        # Return c's Image Id string with the image object.
        # DockerObj's __eq__ supports comparison to str, so this should be OK.
        c.Image = image
