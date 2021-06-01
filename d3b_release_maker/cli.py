#!/usr/bin/env python
import click
import re
import subprocess

from d3b_release_maker.release_maker import make_release, new_notes


def get_repository():
    """
    Try to retrieve the github repository by extracting it from the current git
    repository's 'origin' url.
    """
    try:
        result = subprocess.check_output(
            ["git", "remote", "get-url", "origin"], stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        # If the git command fails, bail early
        return None

    result = result.decode().strip()
    match = re.match(r".*[:/]([\w\d0-9-]+\/[\w\d-]+)", result)
    if match:
        return match.group(1)
    return None


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli():
    """
    Container for the cli
    """
    pass


def options(function):
    function = click.option(
        "--blurb_file",
        prompt="Optional markdown file containing a custom message to prepend to the notes for this release",
        default="",
        help="Optional markdown file containing a custom message to prepend to the notes for this release",
    )(function)
    function = click.option(
        "--repo",
        prompt="The github repository (e.g. my-organization/my-project-name)",
        help="The github organization/repository to make a release for",
        default=get_repository,
    )(function)
    return function


@click.command(
    name="preview", short_help="Preview the changes for a new release"
)
@options
def preview_changelog_cmd(repo, blurb_file):
    new_notes(repo, blurb_file)


@click.command(name="build", short_help="Generate a new release on GitHub")
@options
def make_release_cmd(repo, blurb_file):
    make_release(repo, blurb_file)


cli.add_command(preview_changelog_cmd)
cli.add_command(make_release_cmd)
