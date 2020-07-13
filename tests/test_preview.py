#!/usr/bin/env python
from click.testing import CliRunner

import pytest
from d3b_release_maker.cli import preview_changelog_cmd


@pytest.mark.parametrize(
    "type,index", [("foo\nmajor", 0), ("foo\nminor", 1), ("foo\npatch", 2)]
)
def test_version(type, index):
    runner = CliRunner()
    result = runner.invoke(
        preview_changelog_cmd,
        args='--repo d3b-center/d3b-release-maker --blurb_file "" --prs_to_ignore ""',
        input=f"{type}",
    )
    assert result.exit_code == 0
    lastlines = result.output.splitlines()[-2:]
    versions = [line.split(": ")[1] for line in lastlines]
    version_parts = [int(v.split(".")[index]) for v in versions]
    assert version_parts[1] == version_parts[0] + 1
