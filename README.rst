docker-cleanup: Remove Obsolete Docker Containers and Images
============================================================

docker-cleanup deletes Docker_ containers and images based on rules
from a config file. Here is an example::

    # Keep currently running containers, delete others if they last finished
    # more than a week ago.
    KEEP CONTAINER IF Container.State.Running;
    DELETE CONTAINER IF Container.State.FinishedAt.before('1 week ago');

    # Delete dangling (unnamed and not used by containers) images.
    DELETE IMAGE IF Image.Dangling;

This produces the output::

    Deleting container drunk_shockley (8febebd2ae07).
    Deleting container piwik-mysqld (de2919e7165f).
    Keeping container romantic_sinoussi (d3b01591c160).
    Deleting image <none> (c7fc123775b0).
    Keeping image debootstrap/minbase:latest (f20371f5799a).
    Keeping image greek0/mysql:latest (fccd2180c600).

.. _Docker: https://www.docker.com/

Features
--------

* Sane lifetime management for Docker containers and images (finally!)
* Simple and expressive rule language
* A rich set of filtering criteria

Getting Started
---------------

Good news: it's easy to start using docker-cleanup! Here are the steps:

* Make sure you have Python >= 3.3
* Get docker-cleanup from GitHub::

      git clone https://github.com/Grk0/docker-cleanup
      cd docker-cleanup

* Install the Python dateutil package::

      sudo apt-get install python3-dateutil  # on Debian or
      sudo yum install python-dateutil       # on Fedora >= 22
      sudo yum install python3-dateutil      # on Fedora < 22

* Edit the `cleanup-rules.conf` file
* Run `docker-cleanup`, at first preferably with the `--dry-run` option::

      docker-cleanup --dry-run

You'll see what docker-cleanup would do in your setup. Once you're satisfied
with the results, drop the ``--dry-run`` parameter and add a cronjob for
docker-cleanup.


The Rules Language
------------------

The rule language is super simple. Rules within the ``cleanup-rules.conf`` file
are checked top-to-bottom against every container and image on the system.
If a rule matches, its action is applied and no further rules are checked.
If no rule matches, no action is taken (i.e. the container or image is kept).

Each rule may be one of 4 basic directives::

    KEEP CONTAINER IF ...;
    DELETE CONTAINER IF ...;

    KEEP IMAGE IF ...;
    DELETE IMAGE IF ...;

These do exactly what you'd expect. The ``...`` part is an condition
expression, if it evaluates to *True*, the rule matches and the corresponding
action (keep/delete) is taken.

Container directives can access the ``Container`` variable inside the
expression, while image directives have an ``Image`` variable. Both variables
support a wide range of attributes, such as ``Id``, ``Name``, ``Created`` and
many more::

    DELETE CONTAINER IF Container.Id.startswith('c664a829fe15');
    KEEP IMAGE IF Image.Name == 'debian:jessie';

The attributes are derived from ``docker inspect``, so that is a good starting
point for getting a list of attributes supported by ``Container`` and ``Image``
objects. Containers have one noteworthy field:

* ``Containers.Image`` is the ``Image`` object the container is based on,
  instead of simply an image id string.

``Image`` variables support a few additional attributes not listed by ``docker
inspect``:

* ``Image.Repository``: the repository column in 'docker images'
* ``Image.Tag``: the tag column in 'docker images'
* ``Image.Name``: the combined repository and tag: ``<repository>:<tag>``.
* ``Image.Containers``: a set of ``Container`` objects based off the image
* ``Image.Dangling``: true for images that are not used by any container
  and don't have a proper name (``<none>/<none>``)

Finally, containers and images have proper date/time objects as
their ``Created``, ``State.StartedAt``, and ``State.FinishedAt`` attributes
(the last two only apply to containers). These objects have the methods
``after()`` and ``before()``, which support natural comparison to absolute
and relative times::

    Image.Created.before('2015.05.22')        # True for images created before May 22
    Image.Created.before('2015.05.22 16:18')  # True for images created before May 22, 4:18 pm
    Image.Created.before('1 week ago')        # True for images created more than one week ago

    # True for containers that stopped running more than 3 hours ago.
    Container.State.FinishedAt.before('3 hours ago')

    # True for containers last started after January 31.
    Container.State.StartedAt.after('2015-01-31')

The conditional expression within rules is translated into Python code and can
be arbitrarily complex. The most important syntax elements are:

* ``== != < > <= >=``: the typical comparison operators
* ``not <expression>``: negation of the expression
* ``<a> and <b>``: true if both ``<a>`` and ``<b>`` are true
* ``<a> or <b>``: true if either ``<a>`` or ``<b>`` are true
* ``1 + 2 * 3``: normal operator precedence (``1 + (2 * 3)``)
* ``(1 + 2) * 3``: parentheses will do the expected thing
* ``'abc' == "abc"``: strings use either single or double quotes

In contrast to normal Python code, newlines are allowed everywhere, and each
rule statement must be terminated with a semicolon (``;``). This encourages
writing readable rules::

    DELETE CONTAINER IF not Container.Running and
                        Container.Image.Repository == 'postgres' and
                        Container.State.FinishedAt.before('4 days ago');

Strive to write clear and readable rule files!

Force delete
++++++++++++

If ``FORCE`` is placed before the ``DELETE`` keyword, the ``--force`` option
is passed to ``docker rm`` and ``docker rmi``. For containers, this enables
deletion of currently running containers to succeed. For images, it enables
deletion of images that are still in use by an existing container::

    # Always delete the Ubuntu container, even if it is currently running.
    FORCE DELETE CONTAINER IF Container.Name == 'ubuntu';

    # Delete all node images, even if containers still use them.
    FORCE DELETE IMAGE IF Image.Repository == 'node';



Contributing to docker-cleanup
------------------------------

To start working with the docker-cleanup code, create a virtual environment,
activate it, and install the development requirements::

    python3.4 -m venv venv
    source venv/bin/activate
    pip install -r dev-requirements.txt

And you're good to go! Patches and GitHub pull requests are more than welcome.

Note that docker-cleanup relies heavily on its testsuite, so please make sure
that it still passes after your changes (run ``py.test``). New features also
require test coverage to be accepted upstream::

    py.test --cov docker_cleanup --cov-report html

