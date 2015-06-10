API Documentation for the docker_cleanup Package
================================================

This document describes the internal structure of docker-cleanup. It is
intended for developers and typically not very interesting for end-users.

docker-cleanup is structured into several different parts:

* A rule file interpreter, is implemented in ``rulefile.py``. It relies on two
  helper modules to get its job done:

  - ``parser.py`` for parsing the rule file
  - ``tokenrunner.py`` for executing KEEP and DELETE expressions
* An interface to Docker, which provides lists of containers and images, as
  well as the ability to remove them. This is implemented in ``docker.py``.
* Error classes in ``error.py``.
* An overall driver, ``main.py``.

.. automodule:: docker_cleanup
    :members:
    :undoc-members:
    :show-inheritance:

Common tasks
------------

To augment the ``Container`` and ``Image`` objects available in rules
statements, look into ``docker.py``.

To extend the rules file syntax, ``docker.py`` and ``rulefile.py`` will need to
be modified.

Modules
-------

.. toctree::
   :maxdepth: 2

   docker_cleanup.main
   docker_cleanup.docker
   docker_cleanup.rulefile
   docker_cleanup.parser
   docker_cleanup.tokenrunner
   docker_cleanup.error
