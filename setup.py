#!/usr/bin/env python

import sys
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

if sys.version_info < (3, 6):
    raise NotImplementedError("Sorry, you need at least Python 3.6 to use sayo.")

import sayo

REQUIRED = [
    'websockets'
]

setup(name='sayo',
      version=sayo.__version__,
      description='An incomplete socket.io client written using asyncio.',
      long_description=sayo.__doc__,
      author=sayo.__author__,
      author_email='samuel.charron@gmail.com',
      url='https://github.com/scharron/sayo/',
      py_modules=['sayo'],
      scripts=['sayo.py'],
      license='MIT',
      platforms='any',
      classifiers=['Development Status :: 3 - Alpha',
                   'Intended Audience :: Developers',
                   'License :: OSI Approved :: MIT License',
                   'Framework :: AsyncIO',
                   'Topic :: System :: Networking',
                   'Topic :: Software Development :: Libraries :: Application Frameworks',
                   'Programming Language :: Python :: 3.6',
                   ],
      install_requires=REQUIRED
      )