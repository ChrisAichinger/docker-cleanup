
from setuptools import setup

import docker_cleanup

install_requires = ['python-dateutil>=2.2']
tests_require = ['pytest', 'coverage<4.0a1', 'pytest-cov', 'pytest-mock']
docs_require = ['sphinx']

setup(name='docker_cleanup',
      version=docker_cleanup.__version__,
      url='https://github.com/Grk0/docker-cleanup',
      description='Clean up Docker containers and images',
      author='Christian Aichinger',
      author_email='Greek0@gmx.net',
      license='Apache Software License',
      classifiers = [
          'Development Status :: 4 - Beta',
          'Environment :: Console',
          'Intended Audience :: Developers',
          'Intended Audience :: System Administrators',
          'License :: OSI Approved :: Apache Software License',
          'Natural Language :: English',
          'Operating System :: POSIX :: Linux',
          'Programming Language :: Python :: 3 :: Only',
          'Programming Language :: Python :: 3.3',
          'Programming Language :: Python :: 3.4',
          'Topic :: System :: Systems Administration',
          'Topic :: Utilities',
          ],

      packages=['docker_cleanup'],
      entry_points={
          'console_scripts': ['docker-cleanup = docker_cleanup.main:main']},

      install_requires=install_requires,
      tests_require=tests_require,
      extras_require={
          'tests': tests_require,
          'docs': docs_require,
          },
      )

#    cmdclass={'test': PyTest},
#    long_description=long_description,
#    include_package_data=True,
#    platforms='any',
#    test_suite='sandman.test.test_sandman',
#    extras_require={
#        'testing': ['pytest'],
#    }
