import json
import os
import shutil
import stat
import subprocess
import tempfile
import time
from collections import defaultdict
from datetime import datetime
from getpass import getpass

import click
import emoji
import regex
import semver
from d3b_release_maker import config
from d3b_utils.requests_retry import Session
from github import Github
from github.GithubException import GithubException, UnknownObjectException

GH_API = config.GITHUB_API
GH_RAW = config.GITHUB_RAW

CHANGEFILE = "CHANGELOG.md"
CONFIGFILE = "release_maker_cfg.json"

MAJOR = "major"
MINOR = "minor"
PATCH = "patch"
RELEASE_OPTIONS = [MAJOR, MINOR, PATCH]

release_pattern = r"\s*[" + config.PAST_RELEASE_EMOJIS + r"]\s*[Rr]elease"
emoji_categories = {
    e: category
    for category, emoji_set in config.EMOJI_CATEGORIES.items()
    for e in emoji_set
}

if not os.getenv(config.GH_TOKEN_VAR):
    gh_token = getpass(
        prompt=f"Required GitHub API token not found at {config.GH_TOKEN_VAR} in your environment. Please enter one here: "
    )
    os.environ[config.GH_TOKEN_VAR] = gh_token


def split_at_pattern(text, pattern):
    """
    Split a string where a pattern begins
    """
    obj = regex.search(pattern, text)
    if obj:
        start = obj.start()
        return text[0:start], text[start:]
    else:
        return text, ""


def delay_until(datetime_of_reset):
    wait_time = int((datetime_of_reset - datetime.now()).total_seconds() + 5.5)
    timestr = (
        lambda wait_time: f"{(wait_time//60)} minutes, {wait_time%60} seconds"
    )
    print(f"Backing off for {timestr(wait_time)}.")
    print(
        "If you don't want to wait that long right now, feel free to kill this process."
    )
    while wait_time > 0:
        time.sleep(5)
        wait_time -= 5
        print(f"{timestr(wait_time)} remaining...")


class GitHubSession(Session):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.headers.update({"Accept": "application/vnd.github.v3.raw+json"})
        gh_token = os.getenv(config.GH_TOKEN_VAR)
        if gh_token:
            self.headers.update({"Authorization": "token " + gh_token})

    def get(self, url, **request_kwargs):
        """
        If response.status_code is not 200 then exit program
        Otherwise return original response
        """
        while True:
            response = super().get(url, **request_kwargs)
            if response.status_code != 200:
                if response.status_code == 404:
                    raise UnknownObjectException(
                        response.status_code, response.url
                    )
                elif response.headers.get("X-Ratelimit-Remaining") == "0":
                    print(
                        response.json().get("message"),
                        "<--- https://developer.github.com/v3/#rate-limiting",
                    )
                    datetime_of_reset = datetime.fromtimestamp(
                        int(response.headers["X-Ratelimit-Reset"])
                    )
                    delay_until(datetime_of_reset)
                else:
                    raise GithubException(
                        response.status_code,
                        f"Could not fetch {response.url}! Caused by: {response.text}",
                    )
            else:
                break

        return response

    def yield_paginated(self, endpoint, query_params):
        """
        Yield from paginated endpoint
        """
        query_params.update({"page": 1, "per_page": 100})
        items = True
        while items:
            items = self.get(endpoint, params=query_params).json()
            yield from items
            query_params["page"] += 1


class GitHubReleaseNotes:
    def __init__(self):
        self.session = GitHubSession()

    def _starting_emojis(self, title):
        """
        Detect emojis at the start of a PR title (and fix malformed titles)
        """
        emojis = set()
        graphemes = regex.findall(r"\X", title)
        emoji_rex = emoji.get_emoji_regexp()
        for i, g in enumerate(graphemes):
            if emoji_rex.match(g):
                emojis.add(g)
            else:  # stop after first non-hit
                if g != " ":
                    # fix missing space in malformed titles
                    title = (
                        "".join(graphemes[:i]) + " " + "".join(graphemes[i:])
                    )
                break

        return (emojis, title)

    def _get_merged_prs(self, branch, after, prs_to_ignore=None):
        """
        Get all non-release PRs merged into the given branch after the given time
        """
        print("Fetching PRs ...")
        endpoint = f"{self.base_url}/pulls"
        query_params = {
            "sort": "updated",
            "direction": "desc",
            "base": branch,
            "state": "closed",
        }
        prs = []
        prs_to_ignore = prs_to_ignore or {}
        for p in self.session.yield_paginated(endpoint, query_params):
            if p["merged_at"]:  # only the merged PRs
                if p["updated_at"] < after:
                    # stop looking if last update was before the last release
                    break
                elif (
                    (p["merged_at"] > after)  # ignore old PRs with updates
                    and (p["number"] not in prs_to_ignore)
                    and (regex.search(release_pattern, p["title"]) is None)
                ):
                    prs.append(p)
        return sorted(prs, key=lambda x: x["merged_at"], reverse=True)

    def _get_commit_date(self, commit_url):
        """
        Get date of commit at commit_url
        """
        commit = self.session.get(commit_url).json()
        return commit["commit"]["committer"]["date"]

    def _get_last_tag(self):
        """
        Get latest tag and when it was committed
        """
        tags = self.session.get(f"{self.base_url}/tags").json()

        # Get latest commit of last tagged release
        if len(tags) > 0:
            for t in tags:
                try:
                    prefix, version = split_at_pattern(t["name"], r"\d")
                    # Raise on non-semver tags so we can skip them
                    semver.VersionInfo.parse(version)
                    return {
                        "name": t["name"],
                        "date": self._get_commit_date(t["commit"]["url"]),
                        "commit_sha": t["commit"]["sha"],
                    }
                except ValueError:
                    pass
        else:
            return None

    def _next_release_version(self, prev_version, release_type):
        """
        Get next release version based on prev version using semver format
        """
        prev_version = semver.VersionInfo.parse(prev_version).finalize_version()
        if release_type == MAJOR:
            new_version = prev_version.bump_major()
        elif release_type == MINOR:
            new_version = prev_version.bump_minor()
        elif release_type == PATCH:
            new_version = prev_version.bump_patch()
        else:
            raise ValueError(
                f"Invalid release type: {release_type}! Release type "
                f"must be one of {RELEASE_OPTIONS}!"
            )

        return str(new_version)

    def _to_markdown(self, repo, counts, prs):
        """
        Converts accumulated information about the project into markdown
        """
        messages = []

        if (len(counts["emojis"]) + len(counts["categories"])) > 0:
            messages.extend(["### Summary", ""])
            if len(counts["emojis"]) > 0:
                emoji_sum = sum(counts["emojis"].values())
                if len(prs) > emoji_sum:
                    counts["emojis"]["?"] += len(prs) - emoji_sum
                messages.append(
                    "- Emojis: "
                    + ", ".join(
                        f"{k} x{v}" for k, v in counts["emojis"].items()
                    )
                )
            if len(counts["categories"]) > 0:
                category_order = list(config.EMOJI_CATEGORIES.keys()) + [
                    config.OTHER_CATEGORY
                ]
                category_sum = sum(counts["categories"].values())
                if len(prs) > category_sum:
                    counts["categories"][config.OTHER_CATEGORY] += (
                        len(prs) - category_sum
                    )
                messages.append(
                    "- Categories: "
                    + ", ".join(
                        f"{k} x{counts['categories'][k]}"
                        for k in category_order
                        if k in counts["categories"]
                    )
                )
            messages.append("")

        messages.extend(["### New features and changes", ""])

        for p in prs:
            if p["merge_commit_sha"] is None:
                continue
            userlink = f"[{p['user']['login']}]({p['user']['html_url']})"
            sha_link = f"[{p['merge_commit_sha'][:8]}](https://github.com/{repo}/commit/{p['merge_commit_sha']})"
            pr_link = f"[#{p['number']}]({p['html_url']})"
            messages.append(
                f"- {pr_link} - {p['title']} - {sha_link} by {userlink}"
            )

        return "\n".join(messages)

    def build_release_notes(self, repo, blurb=None, prs_to_ignore=None):
        """
        Make release notes
        """
        print("\nBegin making release notes ...")

        # Set up session
        self.base_url = f"{GH_API}/repos/{repo}"
        default_branch = self.session.get(self.base_url).json()[
            "default_branch"
        ]

        # Get tag of last release
        print("Fetching latest tag ...")
        latest_tag = self._get_last_tag()

        if latest_tag:
            print(f"Latest tag: {latest_tag}")
        else:
            print("No tags found")
            latest_tag = {"name": "0.0.0", "date": ""}

        # Get all non-release PRs that were merged into the main branch after
        # the last release
        prs = self._get_merged_prs(
            default_branch, latest_tag["date"], prs_to_ignore
        )

        # Count the emojis and fix missing spaces in titles
        counts = {"emojis": defaultdict(int), "categories": defaultdict(int)}
        for p in prs:
            emojis, p["title"] = self._starting_emojis(p["title"].strip())
            for e in emojis:
                counts["emojis"][e] += 1
                counts["categories"][
                    emoji_categories.get(e, config.OTHER_CATEGORY)
                ] += 1

        # Compose markdown
        markdown = self._to_markdown(repo, counts, prs)
        if blurb:
            markdown = f"{blurb}\n\n" + markdown

        print("=" * 32 + "BEGIN DELTA" + "=" * 32)
        print(markdown)
        print("=" * 33 + "END DELTA" + "=" * 33)

        release_type = click.prompt(
            "What type of semantic versioning release is this?",
            type=click.Choice(RELEASE_OPTIONS),
        )

        # Update release version
        prefix, prev_version = split_at_pattern(latest_tag["name"], r"\d")
        version = prefix + self._next_release_version(
            prev_version, release_type
        )
        markdown = f"## Release {version}\n\n" + markdown

        print(f"Previous version: {prev_version}")
        print(f"New version: {version}")

        return default_branch, version, markdown


def new_notes(repo, blurb_file, prs_to_ignore):
    """
    Build notes for new changes
    """
    blurb = None
    if blurb_file:
        with open(blurb_file, "r") as bf:
            blurb = bf.read().strip()

    if prs_to_ignore != "":
        prs_to_ignore = {int(k.strip()) for k in prs_to_ignore.split(",")}

    return GitHubReleaseNotes().build_release_notes(
        repo=repo, blurb=blurb, prs_to_ignore=prs_to_ignore
    )


def new_changelog(repo, blurb_file, prs_to_ignore):
    """
    Creates release notes markdown containing:
    - The next release version number
    - A changelog of Pull Requests merged into the main branch since the last
      release
    - Emoji and category summaries for Pull Requests in the release

    Then merges that into the existing changelog.
    """

    # Build notes for new changes

    branch, new_version, new_markdown = new_notes(
        repo, blurb_file, prs_to_ignore
    )

    if new_version not in new_markdown.partition("\n")[0]:
        print(
            f"New version '{new_version}' not in release title of new markdown."
        )
        return None, None, None, None

    # Load previous changelog file

    session = GitHubSession()
    try:
        prev_markdown = session.get(
            f"{GH_RAW}/{repo}/{branch}/{CHANGEFILE}"
        ).text
    except UnknownObjectException:
        prev_markdown = ""

    # Remove previous title line if not specific to a particular release

    if "\n" in prev_markdown:
        prev_title, prev_markdown = prev_markdown.split("\n", 1)
        if regex.search(r"[Rr]elease .*\d+\.\d+\.\d+", prev_title):
            prev_markdown = "\n".join([prev_title, prev_markdown])

    # Update changelog with new release notes

    if new_version in prev_markdown.partition("\n")[0]:
        print(f"\nNew version '{new_version}' already in {CHANGEFILE}.")
        return None, None, None, None
    else:
        changelog = "\n\n".join([new_markdown, prev_markdown]).rstrip()
        return branch, new_version, new_markdown, changelog


def load_config():
    """
    Get repo config file
    """
    try:
        with open(CONFIGFILE, "r") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}

    update = False
    if "project_title" not in cfg:
        cfg["project_title"] = click.prompt(
            f"Project title not found in repo {CONFIGFILE}. Please enter one now"
        )
        update = True
    if "pre_release_script" not in cfg:
        cfg["pre_release_script"] = click.prompt(
            f"Pre-release script path not found in repo {CONFIGFILE}."
            " Enter one now if desired or just return to continue:",
            default="",
        )
        update = True

    if update:
        with open(CONFIGFILE, "w") as f:
            json.dump(cfg, f, indent=2)

    return cfg


def make_release(repo, blurb_file, prs_to_ignore):
    """
    Generate a new changelog, run the script, and then make a PR on GitHub
    """
    gh_token = os.getenv(config.GH_TOKEN_VAR)
    default_branch, new_version, new_markdown, changelog = new_changelog(
        repo, blurb_file, prs_to_ignore
    )

    if changelog:
        # Freshly clone repo
        tmp = os.path.join(tempfile.gettempdir(), "release_maker")
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"Cloning https://github.com/{repo}.git to {tmp} ...")
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                f"https://{gh_token}@github.com/{repo}.git",
                tmp,
            ],
            check=True,
            capture_output=True,
        )
        os.chdir(tmp)

        # Get the configuration
        cfg = load_config()

        # Attach project header
        changelog = f"# {cfg['project_title']} Change History\n\n{changelog}"

        print("Writing updated changelog file ...")
        with open(CHANGEFILE, "w") as f:
            f.write(changelog)

        pre_release_script = cfg.get("pre_release_script")
        if pre_release_script:
            print(f"Executing pre-release script {pre_release_script} ...")
            mode = os.stat(pre_release_script).st_mode
            os.chmod(pre_release_script, mode | stat.S_IXUSR)
            subprocess.run(
                [pre_release_script, new_version],
                check=True,
                capture_output=True,
            )

        # Create and push new release branch
        release_branch_name = (
            f"release-{new_version}-{config.NEW_RELEASE_EMOJI}"
        )
        print(f"Submitting release branch {release_branch_name} ...")
        subprocess.run(
            ["git", "checkout", "-b", release_branch_name],
            check=True,
            capture_output=True,
        )
        subprocess.run(["git", "add", "-A"], check=True, capture_output=True)
        commit_emoji = (
            config.NEW_RELEASE_EMOJI_SHORTCODE
            if hasattr(config, "NEW_RELEASE_EMOJI_SHORTCODE")
            else config.NEW_RELEASE_EMOJI
        )
        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                f"{commit_emoji} Release {new_version}\n\n{new_markdown}",
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "push", "--force", "origin", release_branch_name],
            check=True,
            capture_output=True,
        )

        # Create GitHub Pull Request
        print("Submitting PR for release ...")
        gh_repo = Github(gh_token, base_url=GH_API).get_repo(repo)
        pr_title = f"{config.NEW_RELEASE_EMOJI} Release {new_version}"
        pr_url = None
        for p in gh_repo.get_pulls(state="open", base=default_branch):
            if p.title == pr_title:
                pr_url = p.html_url
                break

        if pr_url:
            print(f"Updated release PR: {pr_url}")
        else:
            pr = gh_repo.create_pull(
                title=pr_title,
                body=new_markdown,
                head=release_branch_name,
                base=default_branch,
            )
            pr.add_to_labels("release")
            print(f"Created release PR: {pr.html_url}")
    else:
        print("Doing nothing.")
