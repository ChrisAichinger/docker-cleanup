#!/usr/bin/python3
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
import logging
import argparse
import contextlib

from docker_cleanup import docker, rulefile, error

RULES_FILE = 'cleanup-rules.conf'

logger = logging.getLogger(__name__)


def parse_args(argv):
    """Parse commandline arguments"""
    parser = argparse.ArgumentParser(
        description='Remove undesired Docker images and containers.')
    parser.add_argument('-c', '--config', default=RULES_FILE,
                        help='Path of the rules file to read. '
                             '(default: %(default)s)')
    parser.add_argument('-s', '--statements', metavar='RULES',
                        help='Do not read the rules file, '
                             'execute RULES instead.')
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help='Display more information. '
                             'Repeat for even more verbose output.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Do not actually delete images/containers, '
                             'just print what would happen.')
    parser.add_argument('--dockerpath', default=docker.DOCKER,
                        help='Set docker executable to use '
                             '(default: %(default)s)')
    args = parser.parse_args(argv)

    try:
        args.loglevel = [logging.WARN, logging.INFO][args.verbose]
    except IndexError:
        args.loglevel = logging.DEBUG

    return args


def process(rules, ci, delete_function):
    """Apply rules to container/image ``ci``"""
    action_messages = {
        rulefile.RuleAction.keep: "Keeping %s.",
        rulefile.RuleAction.delete: "Deleting %s.",
        rulefile.RuleAction.force_delete: "Force deleting %s.",
        }
    delete_actions = {rulefile.RuleAction.delete,
                      rulefile.RuleAction.force_delete}

    try:
        action = rules.can_delete(ci)
    except error.RulesError as e:
        e.print_error(ci, rules.filename, file=sys.stderr)
        sys.exit(1)

    print(action_messages[action] % str(ci))
    if action in delete_actions:
        force = (action == rulefile.RuleAction.force_delete)
        delete_function(ci, force)


@contextlib.contextmanager
def open_rules(args):
    """A context manager giving a file to read rules from"""
    if args.statements is not None:
        f = io.StringIO(args.statements)
        f.name = '<argument %x>' % id(f)
        yield f

    elif hasattr(args.config, 'read'):
        if not hasattr(args.config, 'name'):
            args.config.name = '<internal stream %x>' % id(args.config)
        yield args.config

    else:
        try:
            f = open(args.config, 'r')
        except FileNotFoundError as e:
            print("Could not open rules file '%s':" % e.filename,
                  file=sys.stderr)
            print(e.strerror, file=sys.stderr)
            sys.exit(1)

        try:
            yield f
        finally:
            f.close()


def do_cleanup(rules, containers, images, dry_run=False):
    """Delete containers and images based on rules"""
    def dummy_delete(*args):
        pass

    delete_function = dummy_delete if dry_run else docker.delete_container
    for c in containers:
        process(rules, c, delete_function)

    delete_function = dummy_delete if dry_run else docker.delete_image
    for i in images:
        process(rules, i, delete_function)


def cleanup(args, containers, images):
    """Delete containers and images based on rules"""
    with open_rules(args) as f:
        try:
            rules = rulefile.RuleFile(f)
        except error.RulesError as e:
            e.print_error(None, f.name, sys.stderr)
            sys.exit(1)

        do_cleanup(rules, containers, images, args.dry_run)


def real_main(argv):
    args = parse_args(argv)
    logging.basicConfig(level=args.loglevel)

    docker.DOCKER = args.dockerpath

    try:
        containers = docker.load_containers()
        images = docker.load_images()
        docker.cross_reference(containers, images)

        cleanup(args, containers, images)
    except error.DockerError as e:
        print(e.message, file=sys.stderr)
        print("Make sure you have the permissions to execute `%s' "
              "as the current user." % docker.DOCKER, file=sys.stderr)
        sys.exit(1)


def main():
    sys.exit(real_main(sys.argv[1:]))


if __name__ == '__main__':
    main()
