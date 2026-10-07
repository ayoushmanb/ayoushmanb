import os
import json
import html
import urllib.request
import urllib.parse
import urllib.error

from collections import Counter
from pathlib import Path


# ============================================================
# Configuration
# ============================================================

USERNAME = os.getenv("GITHUB_USERNAME", "ayoushmanb")
TOKEN = os.environ["GITHUB_TOKEN"]

GRAPHQL_API = "https://api.github.com/graphql"
REST_API = "https://api.github.com"

OUT = Path("generated")
OUT.mkdir(exist_ok=True)


# ============================================================
# Programming-language extensions
# ============================================================

LANGUAGE_EXTENSIONS = {
    # Python
    ".py": "Python",
    ".pyx": "Python",

    # R
    ".r": "R",
    ".rmd": "R",

    # MATLAB
    ".m": "MATLAB",

    # C / C++
    ".c": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".hh": "C++",
    ".hxx": "C++",

    # Java
    ".java": "Java",

    # Julia
    ".jl": "Julia",

    # JavaScript / TypeScript
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",

    # Shell
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",

    # SQL
    ".sql": "SQL",

    # Rust
    ".rs": "Rust",

    # Go
    ".go": "Go",

    # C#
    ".cs": "C#",

    # Scala
    ".scala": "Scala",

    # Ruby
    ".rb": "Ruby",

    # Swift
    ".swift": "Swift",

    # Kotlin
    ".kt": "Kotlin",
    ".kts": "Kotlin",

    # TeX
    ".tex": "TeX",

    # Jupyter
    ".ipynb": "Jupyter Notebook",
}


LANGUAGE_COLORS = {
    "Python": "#3572A5",
    "R": "#198CE7",
    "MATLAB": "#e16737",
    "C": "#555555",
    "C++": "#f34b7d",
    "Java": "#b07219",
    "Julia": "#a270ba",
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "Shell": "#89e051",
    "SQL": "#e38c00",
    "Rust": "#dea584",
    "Go": "#00ADD8",
    "C#": "#178600",
    "Scala": "#c22d40",
    "Ruby": "#701516",
    "Swift": "#F05138",
    "Kotlin": "#A97BFF",
    "TeX": "#3D6117",
    "Jupyter Notebook": "#DA5B0B",
}


# ============================================================
# Directories/files we do not want to count
# ============================================================

EXCLUDED_DIRS = {
    ".git",
    ".github",
    "generated",

    "node_modules",

    ".venv",
    "venv",
    "env",

    "__pycache__",

    "dist",
    "build",

    "vendor",

    ".tox",
    ".pytest_cache",
    ".mypy_cache",

    "site-packages",
    "target",
}


# ============================================================
# GitHub GraphQL helper
# ============================================================

def graphql(query, variables):

    payload = json.dumps({
        "query": query,
        "variables": variables,
    }).encode("utf-8")

    request = urllib.request.Request(
        GRAPHQL_API,
        data=payload,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "github-personal-language-card",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=60,
    ) as response:
        result = json.load(response)

    if result.get("errors"):
        raise RuntimeError(
            json.dumps(
                result["errors"],
                indent=2,
            )
        )

    return result["data"]


# ============================================================
# GitHub REST helper
# ============================================================

def github_rest(path, params=None):

    url = REST_API + path

    if params:
        url += "?" + urllib.parse.urlencode(params)

    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "github-personal-language-card",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=60,
    ) as response:
        return json.load(response)


# ============================================================
# Encode owner/repository safely for GitHub REST URLs
# ============================================================

def encoded_repo_name(repo_name):

    return "/".join(
        urllib.parse.quote(
            part,
            safe="",
        )
        for part in repo_name.split("/")
    )


# ============================================================
# Source-file helpers
# ============================================================

def excluded_file(path):

    path_obj = Path(path)

    if set(path_obj.parts) & EXCLUDED_DIRS:
        return True

    # Ignore bundled/minified JavaScript-like files
    if ".min." in path_obj.name.lower():
        return True

    return False


def file_language(path):

    if excluded_file(path):
        return None

    suffix = Path(path).suffix.lower()

    return LANGUAGE_EXTENSIONS.get(suffix)


# ============================================================
# Candidate repositories
#
# We discover repositories using several mechanisms:
#
# 1. ALL public repositories owned by the user
# 2. Public repositoriesContributedTo repositories
# 3. Historical commit-contribution repositories
# 4. Historical pull-request contribution repositories
#
# PRIVATE REPOSITORIES ARE ALWAYS EXCLUDED.
# ============================================================

repos = {}


def add_candidate_repo(
    name,
    owner,
    branch,
    source,
    year=None,
):

    if not name:
        return

    if not branch:
        return

    if name not in repos:

        repos[name] = {
            "name": name,
            "owner": owner,
            "branch": branch,
            "discovery_sources": set(),
            "years": set(),
        }

    repos[name]["discovery_sources"].add(source)

    if year is not None:
        repos[name]["years"].add(year)


# ============================================================
# 1. Discover ALL PUBLIC repositories owned by me
#
# IMPORTANT:
# ayoushmanb/ayoushmanb IS INCLUDED.
# ============================================================

def discover_owned_public_repositories():

    print()
    print("Discovering public repositories owned by me...")

    page = 1

    while True:

        data = github_rest(
            f"/users/{USERNAME}/repos",
            {
                "type": "owner",
                "sort": "updated",
                "direction": "desc",
                "per_page": 100,
                "page": page,
            },
        )

        if not data:
            break

        for repo in data:

            # ------------------------------------------------
            # PRIVATE repositories remain excluded
            # ------------------------------------------------

            if repo.get("private"):
                continue

            name = repo["full_name"]

            add_candidate_repo(
                name=name,
                owner=repo["owner"]["login"],
                branch=repo.get("default_branch"),
                source="owned_public_repo",
            )

        if len(data) < 100:
            break

        page += 1


# ============================================================
# 2. Discover PUBLIC external repositories through
#    repositoriesContributedTo
# ============================================================

def discover_repositories_contributed_to():

    print()
    print("Discovering repositoriesContributedTo...")

    query = """
    query(
        $login: String!,
        $cursor: String
    ) {

      user(login: $login) {

        repositoriesContributedTo(
          first: 100,
          after: $cursor,
          includeUserRepositories: false,
          contributionTypes: [
            COMMIT,
            PULL_REQUEST
          ]
        ) {

          pageInfo {
            hasNextPage
            endCursor
          }

          nodes {

            nameWithOwner
            isPrivate

            owner {
              login
            }

            defaultBranchRef {
              name
            }

          }

        }

      }

    }
    """

    cursor = None

    while True:

        data = graphql(
            query,
            {
                "login": USERNAME,
                "cursor": cursor,
            },
        )

        connection = data[
            "user"
        ][
            "repositoriesContributedTo"
        ]

        for repo in connection["nodes"]:

            # ------------------------------------------------
            # PRIVATE third-party repositories remain excluded
            # ------------------------------------------------

            if repo["isPrivate"]:
                continue

            branch_ref = repo.get(
                "defaultBranchRef"
            )

            if not branch_ref:
                continue

            add_candidate_repo(
                name=repo["nameWithOwner"],
                owner=repo["owner"]["login"],
                branch=branch_ref["name"],
                source="repositoriesContributedTo",
            )

        page_info = connection["pageInfo"]

        if not page_info["hasNextPage"]:
            break

        cursor = page_info["endCursor"]


# ============================================================
# Contribution years
# ============================================================

def get_contribution_years():

    query = """
    query($login: String!) {

      user(login: $login) {

        contributionsCollection {
          contributionYears
        }

      }

    }
    """

    data = graphql(
        query,
        {
            "login": USERNAME,
        },
    )

    return data[
        "user"
    ][
        "contributionsCollection"
    ][
        "contributionYears"
    ]


# ============================================================
# 3/4. Historical commit + PR contribution repositories
# ============================================================

def discover_historical_contributions():

    years = get_contribution_years()

    print()
    print(
        "Contribution years:",
        years,
    )

    query = """
    query(
        $login: String!,
        $from: DateTime!,
        $to: DateTime!
    ) {

      user(login: $login) {

        contributionsCollection(
          from: $from,
          to: $to
        ) {

          commitContributionsByRepository(
            maxRepositories: 100
          ) {

            repository {

              nameWithOwner
              isPrivate

              owner {
                login
              }

              defaultBranchRef {
                name
              }

            }

          }

          pullRequestContributionsByRepository(
            maxRepositories: 100
          ) {

            repository {

              nameWithOwner
              isPrivate

              owner {
                login
              }

              defaultBranchRef {
                name
              }

            }

          }

        }

      }

    }
    """

    for year in years:

        print(
            f"Checking historical contributions "
            f"for {year}..."
        )

        data = graphql(
            query,
            {
                "login": USERNAME,
                "from": (
                    f"{year}-01-01T00:00:00Z"
                ),
                "to": (
                    f"{year}-12-31T23:59:59Z"
                ),
            },
        )

        collection = data[
            "user"
        ][
            "contributionsCollection"
        ]

        # ----------------------------------------------------
        # Commit contribution repositories
        # ----------------------------------------------------

        for item in collection[
            "commitContributionsByRepository"
        ]:

            repo = item["repository"]

            if repo["isPrivate"]:
                continue

            branch = repo.get(
                "defaultBranchRef"
            )

            if not branch:
                continue

            add_candidate_repo(
                name=repo["nameWithOwner"],
                owner=repo["owner"]["login"],
                branch=branch["name"],
                source="historical_commit_contribution",
                year=year,
            )

        # ----------------------------------------------------
        # Pull-request contribution repositories
        # ----------------------------------------------------

        for item in collection[
            "pullRequestContributionsByRepository"
        ]:

            repo = item["repository"]

            if repo["isPrivate"]:
                continue

            branch = repo.get(
                "defaultBranchRef"
            )

            if not branch:
                continue

            add_candidate_repo(
                name=repo["nameWithOwner"],
                owner=repo["owner"]["login"],
                branch=branch["name"],
                source="historical_pr_contribution",
                year=year,
            )


# ============================================================
# Run repository discovery
# ============================================================

discover_owned_public_repositories()

discover_repositories_contributed_to()

discover_historical_contributions()


print()
print(
    f"Found {len(repos)} candidate "
    f"public repositories."
)


# ============================================================
# Get ALL current branches in a repository
#
# We search more than just "main".
#
# This allows us to find authored commits on feature branches,
# gh-pages, or other current branches.
# ============================================================

def get_branches(repo_name):

    encoded_repo = encoded_repo_name(
        repo_name
    )

    branches = []

    page = 1

    while True:

        data = github_rest(
            f"/repos/{encoded_repo}/branches",
            {
                "per_page": 100,
                "page": page,
            },
        )

        if not data:
            break

        branches.extend(
            branch["name"]
            for branch in data
        )

        if len(data) < 100:
            break

        page += 1

    return branches


# ============================================================
# Get MY commits on one branch
# ============================================================

def get_my_commits_on_branch(
    repo_name,
    branch,
):

    encoded_repo = encoded_repo_name(
        repo_name
    )

    commits = []

    page = 1

    while True:

        data = github_rest(
            f"/repos/{encoded_repo}/commits",
            {
                "author": USERNAME,
                "sha": branch,
                "per_page": 100,
                "page": page,
            },
        )

        if not data:
            break

        commits.extend(data)

        if len(data) < 100:
            break

        page += 1

    return commits


# ============================================================
# Get ALL unique commits authored by me
#
# Same commit may exist on several branches.
# Deduplicate using commit SHA.
# ============================================================

def get_all_my_commits(
    repo_name,
    default_branch,
):

    branches = get_branches(
        repo_name
    )

    if (
        default_branch
        and default_branch not in branches
    ):
        branches.append(
            default_branch
        )

    commit_map = {}

    print(
        f"  scanning {len(branches)} "
        f"branch(es)"
    )

    for branch in branches:

        try:

            commits = (
                get_my_commits_on_branch(
                    repo_name,
                    branch,
                )
            )

        except urllib.error.HTTPError as exc:

            print(
                f"    WARNING: could not read "
                f"branch {branch}: HTTP {exc.code}"
            )

            continue

        if commits:

            print(
                f"    {branch}: "
                f"{len(commits)} matching commit(s)"
            )

        for commit in commits:

            commit_map[
                commit["sha"]
            ] = commit

    return (
        list(commit_map.values()),
        branches,
    )


# ============================================================
# Get files changed by one commit
# ============================================================

def get_commit_files(
    repo_name,
    sha,
):

    encoded_repo = encoded_repo_name(
        repo_name
    )

    files = []

    page = 1

    while True:

        data = github_rest(
            f"/repos/{encoded_repo}/commits/{sha}",
            {
                "per_page": 100,
                "page": page,
            },
        )

        page_files = data.get(
            "files",
            [],
        )

        files.extend(
            page_files
        )

        if len(page_files) < 100:
            break

        page += 1

    return files


# ============================================================
# Find UNIQUE source-file paths personally touched by me
#
# Examples:
#
# model.R changed in 20 commits -> 1 file
#
# same commit visible on main + feature branch -> 1 commit
#
# same filename in different repositories -> counted separately
# ============================================================

def get_my_source_files(
    repo_name,
    default_branch,
):

    commits, branches = (
        get_all_my_commits(
            repo_name,
            default_branch,
        )
    )

    print(
        f"  unique authored commits: "
        f"{len(commits)}"
    )

    touched_files = set()

    for i, commit in enumerate(
        commits,
        start=1,
    ):

        sha = commit["sha"]

        print(
            f"    commit "
            f"{i}/{len(commits)} "
            f"{sha[:8]}"
        )

        try:

            files = get_commit_files(
                repo_name,
                sha,
            )

        except urllib.error.HTTPError as exc:

            print(
                f"      WARNING: commit "
                f"could not be read: "
                f"HTTP {exc.code}"
            )

            continue

        for file_info in files:

            filename = file_info.get(
                "filename"
            )

            if not filename:
                continue

            language = file_language(
                filename
            )

            if language is None:
                continue

            touched_files.add(
                filename
            )

    return (
        touched_files,
        commits,
        branches,
    )


# ============================================================
# Process candidate repositories
# ============================================================

overall_file_counts = Counter()

all_repo_results = []


for repo_name in sorted(
    repos.keys(),
    key=str.lower,
):

    repo = repos[
        repo_name
    ]

    print()
    print("=" * 70)
    print(
        f"Processing {repo_name}"
    )
    print("=" * 70)

    external = (
        repo["owner"].lower()
        != USERNAME.lower()
    )

    result = {
        "repository":
            repo_name,

        "owner":
            repo["owner"],

        "external":
            external,

        "default_branch":
            repo["branch"],

        "discovery_sources":
            sorted(
                repo[
                    "discovery_sources"
                ]
            ),

        "contribution_years":
            sorted(
                repo["years"]
            ),

        "branches_scanned":
            [],

        "my_commits_found":
            0,

        "my_source_files":
            {},

        "total_my_source_files":
            0,

        "my_source_file_paths":
            [],

        "status":
            "pending",
    }

    try:

        my_files, my_commits, branches = (
            get_my_source_files(
                repo_name,
                repo["branch"],
            )
        )

        repo_counts = Counter()

        for path in my_files:

            language = file_language(
                path
            )

            if language is None:
                continue

            repo_counts[
                language
            ] += 1

            overall_file_counts[
                language
            ] += 1

        result[
            "branches_scanned"
        ] = sorted(branches)

        result[
            "my_commits_found"
        ] = len(my_commits)

        result[
            "my_source_files"
        ] = dict(
            repo_counts.most_common()
        )

        result[
            "total_my_source_files"
        ] = len(my_files)

        result[
            "my_source_file_paths"
        ] = sorted(my_files)

        if my_files:

            result[
                "status"
            ] = "counted"

        elif my_commits:

            result[
                "status"
            ] = (
                "commits_found_but_no_"
                "recognized_source_files"
            )

        else:

            result[
                "status"
            ] = (
                "no_authored_commits_"
                "found_on_current_branches"
            )

    except urllib.error.HTTPError as exc:

        result[
            "status"
        ] = (
            f"http_error_{exc.code}"
        )

        print(
            f"WARNING: HTTP {exc.code} "
            f"while processing {repo_name}"
        )

    except Exception as exc:

        result[
            "status"
        ] = (
            f"error: {exc}"
        )

        print(
            f"WARNING: {exc}"
        )

    all_repo_results.append(
        result
    )


# ============================================================
# Repositories represented in the card
# ============================================================

counted_repos = [
    repo
    for repo in all_repo_results
    if repo[
        "total_my_source_files"
    ] > 0
]


# ============================================================
# Save detailed JSON audit
#
# ALL candidate public repositories remain in this file,
# even if no files were ultimately counted.
#
# Private repos never enter this structure.
# ============================================================

audit = {
    "username":
        USERNAME,

    "definition":
        (
            "Unique recognized source-file paths touched "
            "by commits authored by the user in public "
            "repositories. Includes public repositories "
            "owned by the user and public repositories "
            "owned by others. Private repositories are "
            "excluded. Commits are searched across all "
            "current repository branches and deduplicated "
            "by commit SHA. File paths are deduplicated "
            "within each repository."
        ),

    "candidate_repository_count":
        len(all_repo_results),

    "counted_repository_count":
        len(counted_repos),

    "repositories":
        all_repo_results,

    "overall_file_counts":
        dict(
            overall_file_counts
            .most_common()
        ),
}


with open(
    OUT / "contributed-file-repos.json",
    "w",
    encoding="utf-8",
) as f:

    json.dump(
        audit,
        f,
        indent=2,
    )


# ============================================================
# Prepare SVG data
# ============================================================

total_files = sum(
    overall_file_counts.values()
)

repo_count = len(
    counted_repos
)

external_repo_count = sum(
    1
    for repo in counted_repos
    if repo["external"]
)


MAX_LANGUAGES = 8

ranked = (
    overall_file_counts
    .most_common(
        MAX_LANGUAGES
    )
)


WIDTH = 495
ROW_HEIGHT = 30

HEIGHT = max(
    210,
    145
    + ROW_HEIGHT
    * len(ranked),
)


# ============================================================
# SVG text helper
# ============================================================

def txt(
    x,
    y,
    value,
    size=13,
    weight=400,
    color="#656d76",
):

    value = html.escape(
        str(value)
    )

    return f"""
    <text
        x="{x}"
        y="{y}"
        font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
        font-size="{size}"
        font-weight="{weight}"
        fill="{color}"
    >{value}</text>
    """


# ============================================================
# Build SVG
# ============================================================

svg = f"""
<svg
    xmlns="http://www.w3.org/2000/svg"
    width="{WIDTH}"
    height="{HEIGHT}"
    viewBox="0 0 {WIDTH} {HEIGHT}"
>

<rect
    x="0.5"
    y="0.5"
    width="{WIDTH - 1}"
    height="{HEIGHT - 1}"
    rx="6"
    fill="#ffffff"
    stroke="#d0d7de"
/>

{txt(
    24,
    35,
    "Languages across my contributed files",
    20,
    600,
    "#0969da",
)}

{txt(
    24,
    60,
    (
        f"{total_files} source files "
        f"across {repo_count} public repositories "
        f"· {external_repo_count} owned by others"
    ),
    11,
)}
"""


# ============================================================
# Stacked language bar
# ============================================================

if total_files > 0:

    BAR_X = 24
    BAR_Y = 80
    BAR_WIDTH = 447
    BAR_HEIGHT = 10

    position = BAR_X

    for language, count in ranked:

        fraction = (
            count
            / total_files
        )

        segment_width = (
            fraction
            * BAR_WIDTH
        )

        color = (
            LANGUAGE_COLORS.get(
                language,
                "#8c959f",
            )
        )

        svg += f"""
        <rect
            x="{position:.2f}"
            y="{BAR_Y}"
            width="{segment_width:.2f}"
            height="{BAR_HEIGHT}"
            fill="{color}"
        />
        """

        position += (
            segment_width
        )


# ============================================================
# Language rows
# ============================================================

y = 125


if total_files == 0:

    svg += txt(
        24,
        y,
        "No qualifying source files found.",
        13,
    )

else:

    for language, count in ranked:

        color = (
            LANGUAGE_COLORS.get(
                language,
                "#8c959f",
            )
        )

        percent = (
            100
            * count
            / total_files
        )

        svg += f"""
        <circle
            cx="29"
            cy="{y - 4}"
            r="5"
            fill="{color}"
        />
        """

        svg += txt(
            44,
            y,
            language,
            13,
            600,
            "#24292f",
        )

        svg += txt(
            290,
            y,
            (
                f"{count} "
                f"file"
                f"{'' if count == 1 else 's'}"
            ),
            12,
        )

        svg += txt(
            390,
            y,
            f"{percent:.1f}%",
            12,
        )

        y += ROW_HEIGHT


svg += "</svg>"


# ============================================================
# Save SVG
# ============================================================

with open(
    OUT / "contributed-file-languages.svg",
    "w",
    encoding="utf-8",
) as f:

    f.write(svg)


# ============================================================
# Console summary
# ============================================================

print()
print()
print("=" * 70)
print("PERSONAL SOURCE-FILE CONTRIBUTION SUMMARY")
print("=" * 70)


for repo in all_repo_results:

    print()

    tag = (
        "EXTERNAL"
        if repo["external"]
        else "OWN"
    )

    print(
        f"{tag}: "
        f"{repo['repository']}"
    )

    print(
        "  status: "
        f"{repo['status']}"
    )

    print(
        "  branches scanned: "
        f"{len(repo['branches_scanned'])}"
    )

    print(
        "  my commits found: "
        f"{repo['my_commits_found']}"
    )

    print(
        "  my source files: "
        f"{repo['total_my_source_files']}"
    )

    for language, count in (
        repo[
            "my_source_files"
        ].items()
    ):

        print(
            f"    {language}: "
            f"{count}"
        )


print()
print("-" * 70)
print("OVERALL")
print("-" * 70)


for language, count in (
    overall_file_counts
    .most_common()
):

    percentage = (
        100
        * count
        / total_files
        if total_files
        else 0
    )

    print(
        f"{language:20s} "
        f"{count:5d} files "
        f"{percentage:6.2f}%"
    )


print()
print(
    f"Candidate public repositories: "
    f"{len(all_repo_results)}"
)

print(
    f"Public repositories counted: "
    f"{repo_count}"
)

print(
    f"External public repositories counted: "
    f"{external_repo_count}"
)

print(
    f"Total unique source files: "
    f"{total_files}"
)

print()
print(
    "Generated: "
    "generated/contributed-file-languages.svg"
)

print(
    "Audit: "
    "generated/contributed-file-repos.json"
)