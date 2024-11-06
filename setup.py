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
      version='0.1.1',
      packages=find_packages(),
      package_data={
          '': ['certs/*'],
      },
      install_requires=[
          'async_upnp_client',
          'beautifulsoup4',
          'construct>=2.10.70',
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
