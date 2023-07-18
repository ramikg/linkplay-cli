import os
from setuptools import setup, find_packages

readme_path = os.path.join(os.path.dirname(__file__), 'README.md')
with open(readme_path) as readme:
    long_description = readme.read()

setup(name='linkplay-cli',
      description='Control Linkplay devices from the comfort of your shell',
      long_description=long_description,
      long_description_content_type='text/markdown',
      url='https://github.com/ramikg/linkplay-cli',
      version='0.0.5',
      packages=find_packages(),
      install_requires=[
          'async_upnp_client',
          'beautifulsoup4',
          'lxml',
          'prettytable',
          'pycryptodome',
          'requests',
          'urllib3'
      ],
      entry_points={
          'console_scripts': [
              'linkplay-cli = linkplay_cli.cli:main',
          ]
      },
      classifiers=[
        'Programming Language :: Python :: 3'
      ])
