# D3b Release Maker

Tool to automate GitHub-based software releases for projects with the following
characteristics:

- Feature branching with merge-commits into master
- Gitmoji-style PR messages
- Semantic versioning tags for releases (<https://semver.org>)

## Part 1: CLI that generates release notes and creates a PR on GitHub for review

Install with pip:
`pip install git+https://github.com/d3b-center/d3b-release-maker.git`

Create a temporary auth token on GitHub and add it to your environment as
`GH_TOKEN`.

Then run: `release --help`

## Part 2: GitHub Actions Workflow that automates tagging releases and asset uploading

Copy `gh_releases.yml` from this repository's `.github/workflows/` directory
into `.github/workflows/` in your project repository. (Read more about GitHub
Actions and Workflows at <https://help.github.com/en/actions>)

If you want to attach binary assets to your GitHub releases, add a
`.github/prepare_assets.sh` script that receives one input argument with the
new release version and generates your assets and then creates
`.github/release_assets.txt` containing a list of the files you want to upload,
one per line, in the order that you want them to appear.

## What the parts do

### What the CLI does

When you run the `release build` command:

1. The CLI looks at the most recent git tag that looks like a Semantic Version.
2. Then it looks for all PRs that were merged into master after that tag which
   do not themselves look like a release merge.
3. Emojis at the start of the PR titles are grouped and counted according to
   the gitmoji emoji guide (<https://gitmoji.carloscuesta.me>).
4. Markdown is generated with links to PRs, merge commits, and committers and is
   shown to the user.
5. The user is prompted to provide a type of version update (major, minor,
   patch) based on the shown list of changes, and a new version number is
   generated.
6. A fresh copy of your repository is cloned to a temporary location.
7. The new changes list is added to the CHANGELOG.md file (one is created if
   one doesn't already exist).
8. An optional user-provided script is then run if you need to e.g. add the new
   version number to files in your repository.
9. All newly modified files are commited with a special release commit and
   pushed to a special release branch, and a Pull Request into master is opened
   on GitHub for review.

### What the GitHub Actions Workflow does

When a special release branch is merged into master:

1. Your repository is tagged with the new semantic version, and a GitHub
   release is created with the contents of the just-merged Pull Request body.
2. If a `.github/prepare_assets.sh` script exists, it is run.
3. If a `.github/release_assets.txt` file exists, any files listed in it are
   then uploaded to the GitHub release.
