import os
import json
import html
import urllib.request
import urllib.parse

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
# Languages we want to count
# ============================================================

LANGUAGE_EXTENSIONS = {
    ".py": "Python",
    ".pyx": "Python",

    ".r": "R",
    ".rmd": "R",

    ".m": "MATLAB",

    ".c": "C",

    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".hh": "C++",
    ".hxx": "C++",

    ".java": "Java",

    ".jl": "Julia",

    ".js": "JavaScript",
    ".jsx": "JavaScript",

    ".ts": "TypeScript",
    ".tsx": "TypeScript",

    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",

    ".sql": "SQL",

    ".rs": "Rust",
    ".go": "Go",
    ".cs": "C#",

    ".scala": "Scala",

    ".rb": "Ruby",

    ".swift": "Swift",

    ".kt": "Kotlin",
    ".kts": "Kotlin",

    ".tex": "TeX",

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
# Ignore generated / dependency directories
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
    }).encode()

    request = urllib.request.Request(
        GRAPHQL_API,
        data=payload,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "github-my-file-language-card",
        },
    )

    with urllib.request.urlopen(request) as response:
        result = json.load(response)

    if "errors" in result:
        raise RuntimeError(
            json.dumps(result["errors"], indent=2)
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
            "User-Agent": "github-my-file-language-card",
        },
    )

    with urllib.request.urlopen(request) as response:
        return json.load(response)


# ============================================================
# Find contribution years
# ============================================================

year_query = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionYears
    }
  }
}
"""

data = graphql(
    year_query,
    {"login": USERNAME},
)

years = data[
    "user"
][
    "contributionsCollection"
][
    "contributionYears"
]

print("Contribution years:", years)


# ============================================================
# Discover public repositories where I have commit
# contributions
# ============================================================

repo_fragment = """
repository {

  nameWithOwner
  isPrivate

  owner {
    login
  }

  defaultBranchRef {

    name

    target {
      ... on Commit {

        tree {
          oid
        }

      }
    }

  }

}
"""


contribution_query = f"""
query(
    $login: String!,
    $from: DateTime!,
    $to: DateTime!
) {{

  user(login: $login) {{

    contributionsCollection(
        from: $from,
        to: $to
    ) {{

      commitContributionsByRepository(
          maxRepositories: 100
      ) {{

        {repo_fragment}

        contributions(first: 1) {{
          totalCount
        }}

      }}

    }}

  }}

}}
"""


repos = {}


def add_repo(item, year):

    repo = item["repository"]

    # --------------------------------------------------------
    # Public repositories only
    # --------------------------------------------------------

    if repo["isPrivate"]:
        return

    # --------------------------------------------------------
    # Do not count the GitHub profile repository itself.
    #
    # Otherwise scripts/contributed_*.py would artificially
    # add Python to the card.
    # --------------------------------------------------------

    if (
        repo["nameWithOwner"].lower()
        == f"{USERNAME}/{USERNAME}".lower()
    ):
        return

    default_branch = repo.get(
        "defaultBranchRef"
    )

    if default_branch is None:
        return

    target = default_branch.get("target")

    if target is None:
        return

    tree = target.get("tree")

    if tree is None:
        return

    name = repo["nameWithOwner"]

    if name not in repos:

        repos[name] = {
            "name": name,
            "owner": repo["owner"]["login"],
            "branch": default_branch["name"],
            "tree_oid": tree["oid"],
            "years": set(),
        }

    repos[name]["years"].add(year)


for year in years:

    print(
        f"Finding contributed repositories "
        f"for {year}..."
    )

    data = graphql(
        contribution_query,
        {
            "login": USERNAME,
            "from": f"{year}-01-01T00:00:00Z",
            "to": f"{year}-12-31T23:59:59Z",
        },
    )

    collection = data[
        "user"
    ][
        "contributionsCollection"
    ]

    for item in collection[
        "commitContributionsByRepository"
    ]:

        add_repo(
            item,
            year,
        )


# ============================================================
# Helpers
# ============================================================

def encoded_repo_name(repo_name):

    return "/".join(
        urllib.parse.quote(
            part,
            safe="",
        )
        for part in repo_name.split("/")
    )


def excluded_file(path):

    path_obj = Path(path)

    if set(path_obj.parts) & EXCLUDED_DIRS:
        return True

    if ".min." in path_obj.name.lower():
        return True

    return False


def file_language(path):

    if excluded_file(path):
        return None

    extension = Path(
        path
    ).suffix.lower()

    return LANGUAGE_EXTENSIONS.get(
        extension
    )


# ============================================================
# Get the files that CURRENTLY exist in the repository
# ============================================================

def get_current_files(
    repo_name,
    tree_oid,
):

    encoded_repo = encoded_repo_name(
        repo_name
    )

    data = github_rest(
        f"/repos/{encoded_repo}/git/trees/"
        f"{tree_oid}",
        {
            "recursive": "1",
        },
    )

    if data.get("truncated"):

        print(
            "WARNING: repository tree "
            f"was truncated for {repo_name}"
        )

    current_files = set()

    for item in data.get(
        "tree",
        [],
    ):

        if item.get("type") != "blob":
            continue

        path = item["path"]

        if file_language(path) is None:
            continue

        current_files.add(path)

    return current_files


# ============================================================
# Find commits authored by ME on the default branch
# ============================================================

def get_my_commits(
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
# Get files changed in one commit
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
# Find UNIQUE current source files touched by my commits
# ============================================================

def get_my_source_files(
    repo_name,
    branch,
    tree_oid,
):

    current_files = get_current_files(
        repo_name,
        tree_oid,
    )

    my_commits = get_my_commits(
        repo_name,
        branch,
    )

    print(
        f"  {len(my_commits)} commits "
        f"authored by {USERNAME}"
    )

    touched_paths = set()

    for i, commit in enumerate(
        my_commits,
        start=1,
    ):

        sha = commit["sha"]

        print(
            f"    commit "
            f"{i}/{len(my_commits)} "
            f"{sha[:8]}"
        )

        files = get_commit_files(
            repo_name,
            sha,
        )

        for file_info in files:

            filename = file_info.get(
                "filename"
            )

            if filename:
                touched_paths.add(
                    filename
                )

            # A renamed file may have both paths.
            previous = file_info.get(
                "previous_filename"
            )

            if previous:
                touched_paths.add(
                    previous
                )

    # --------------------------------------------------------
    # Keep only files that:
    #
    # 1. I touched
    # 2. still exist on the current default branch
    # 3. are recognized source-code files
    #
    # This also removes historical/deleted file paths.
    # --------------------------------------------------------

    my_current_files = (
        touched_paths
        & current_files
    )

    return (
        my_current_files,
        len(my_commits),
    )


# ============================================================
# Build personal file-language statistics
# ============================================================

overall_file_counts = Counter()

result_repos = []


for repo in repos.values():

    print()
    print(
        "Processing "
        f"{repo['name']}..."
    )

    my_files, commit_count = (
        get_my_source_files(
            repo["name"],
            repo["branch"],
            repo["tree_oid"],
        )
    )

    repo_counts = Counter()

    for path in my_files:

        language = file_language(
            path
        )

        if language is not None:

            repo_counts[
                language
            ] += 1

            overall_file_counts[
                language
            ] += 1

    external = (
        repo["owner"].lower()
        != USERNAME.lower()
    )

    result_repos.append({
        "repository":
            repo["name"],

        "owner":
            repo["owner"],

        "external":
            external,

        "branch":
            repo["branch"],

        "years":
            sorted(
                repo["years"]
            ),

        "my_commits_on_default_branch":
            commit_count,

        "my_source_files":
            dict(
                repo_counts.most_common()
            ),

        "total_my_source_files":
            len(my_files),

        # Useful for checking that the script
        # really counted only files you touched.
        "my_source_file_paths":
            sorted(my_files),
    })


result_repos.sort(
    key=lambda x: (
        not x["external"],
        x["repository"].lower(),
    )
)


# ============================================================
# Remove repositories where no qualifying source file was found
# ============================================================

result_repos_with_files = [
    repo
    for repo in result_repos
    if repo[
        "total_my_source_files"
    ] > 0
]


# ============================================================
# Save audit JSON
# ============================================================

with open(
    OUT / "contributed-file-repos.json",
    "w",
) as f:

    json.dump(
        {
            "username":
                USERNAME,

            "definition":
                (
                    "Unique current source files "
                    "on public default branches "
                    "touched by commits authored "
                    "by the user."
                ),

            "repositories":
                result_repos_with_files,

            "overall_file_counts":
                dict(
                    overall_file_counts
                    .most_common()
                ),
        },
        f,
        indent=2,
    )


# ============================================================
# Prepare SVG
# ============================================================

total_files = sum(
    overall_file_counts.values()
)

repo_count = len(
    result_repos_with_files
)

external_repo_count = sum(
    repo["external"]
    for repo in result_repos_with_files
)


MAX_LANGUAGES = 8

ranked = overall_file_counts.most_common(
    MAX_LANGUAGES
)


WIDTH = 495
ROW_HEIGHT = 30

HEIGHT = max(
    210,
    145
    + ROW_HEIGHT
    * len(ranked),
)


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

        color = LANGUAGE_COLORS.get(
            language,
            "#8c959f",
        )

        svg += f"""
        <rect
            x="{position}"
            y="{BAR_Y}"
            width="{segment_width}"
            height="{BAR_HEIGHT}"
            fill="{color}"
        />
        """

        position += segment_width


# ============================================================
# Language list
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

        color = LANGUAGE_COLORS.get(
            language,
            "#8c959f",
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
) as f:

    f.write(svg)


# ============================================================
# Console output
# ============================================================

print()
print("=" * 60)
print("MY CONTRIBUTED SOURCE FILES")
print("=" * 60)

for repo in result_repos_with_files:

    tag = (
        "EXTERNAL"
        if repo["external"]
        else "OWN"
    )

    print()
    print(
        f"{tag}: "
        f"{repo['repository']}"
    )

    print(
        "  My commits: "
        f"{repo['my_commits_on_default_branch']}"
    )

    print(
        "  My source files: "
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
print("Overall:")

for language, count in (
    overall_file_counts
    .most_common()
):

    percent = (
        100
        * count
        / total_files
        if total_files
        else 0
    )

    print(
        f"  {language:20s} "
        f"{count:4d} files "
        f"{percent:6.2f}%"
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