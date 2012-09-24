#!/usr/bin/python

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(name="cloudman",
      version=0.1,
      description="Cloud Manager for deploying and organizing compute clusters in cloud environments.",
      author="Enis Afgan and Dannon Baker",
      url="http://userwww.service.emory.edu/~eafgan/projects.html",
      packages=['cm'],
      license = 'MIT',
      platforms = 'Posix; MacOS X',
      classifiers = [ 'Development Status :: 3 - Alpha',
                      'Intended Audience :: Science/Research',
                      'License :: OSI Approved :: MIT License',
                      'Operating System :: OS Independent',
                      'Topic :: Scientific/Engineering',
                    ],
      install_requires = [ 'mako', 
                           'simplejson',
                           'paste',
                           'routes',
                           'webob',
                           'webhelpers',
                           'amqplib',
                           'boto',
                           'pastescript'
                         ],
      )