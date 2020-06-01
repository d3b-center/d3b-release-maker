import os

from setuptools import find_packages, setup

root_dir = os.path.dirname(os.path.abspath(__file__))
req_file = os.path.join(root_dir, "requirements.txt")
with open(req_file) as f:
    requirements = f.read().splitlines()

setup(
    name="d3b-release-maker",
    use_scm_version={
        "local_scheme": "dirty-tag",
        "version_scheme": "post-release",
    },
    setup_requires=["setuptools_scm"],
    description="D3b software release authoring tool",
    author=(
        "Center for Data Driven Discovery in Biomedicine at the"
        " Children's Hospital of Philadelphia"
    ),
    packages=find_packages(),
    entry_points={"console_scripts": ["release=d3b_release_maker.cli:cli"]},
    include_package_data=True,
    install_requires=requirements,
)
