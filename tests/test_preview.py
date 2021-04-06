#!/usr/bin/env python
from d3b_release_maker.release_maker import GitHubReleaseNotes

import pytest


@pytest.mark.parametrize(
    "type,mapping",
    [
        ("major", {"1.2.3": "2.0.0", "": "1.0.0"}),
        ("minor", {"1.2.3": "1.3.0", "": "0.1.0"}),
        ("patch", {"1.2.3": "1.2.4", "": "0.0.1"}),
    ],
)
def test_version(type, mapping):
    grn = GitHubReleaseNotes()
    for start, end in mapping.items():
        assert grn._next_release_version(start, type) == end
