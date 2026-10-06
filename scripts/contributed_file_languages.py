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
# File extensions that we count as source-code languages
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

    # Perl
    ".pl": "Perl",
    ".pm": "Perl",

    # Swift
    ".swift": "Swift",

    # Kotlin
    ".kt": "Kotlin",
    ".kts": "Kotlin",

    # TeX
    ".tex": "TeX",

    # Jupyter notebooks
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
    "Perl": "#0298c3",
    "Swift": "#F05138",
    "Kotlin": "#A97BFF",
    "TeX": "#3D6117",
    "Jupyter Notebook": "#DA5B0B",
}


# ============================================================
# Directories we do NOT want to count
# ============================================================

EXCLUDED_DIRS = {
    ".git",
    ".github",

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
            "User-Agent": "github-contributed-file-language-card",
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

def github_rest(path):

    request = urllib.request.Request(
        REST_API + path,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "github-contributed-file-language-card",
        },
    )

    with urllib.request.urlopen(request) as response:
        return json.load(response)


# ============================================================
# Find years in which the user contributed
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
# Repository information
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

      pullRequestContributionsByRepository(
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


# ============================================================
# Collect contributed repositories
# ============================================================

repos = {}


def add_repo(item, contribution_type, year):

    repo = item["repository"]

    if repo["isPrivate"]:
        return

    branch = repo.get("defaultBranchRef")

    if branch is None:
        return

    target = branch.get("target")

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
            "branch": branch["name"],
            "tree_oid": tree["oid"],

            "commit_count": 0,
            "pr_count": 0,

            "years": set(),
        }

    count = item[
        "contributions"
    ][
        "totalCount"
    ]

    if contribution_type == "commit":
        repos[name]["commit_count"] += count

    elif contribution_type == "pr":
        repos[name]["pr_count"] += count

    repos[name]["years"].add(year)


for year in years:

    print(f"Reading contribution history for {year}...")

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
            "commit",
            year,
        )

    for item in collection[
        "pullRequestContributionsByRepository"
    ]:
        add_repo(
            item,
            "pr",
            year,
        )


# ============================================================
# Decide whether a file should be excluded
# ============================================================

def excluded_file(path):

    path_obj = Path(path)

    parts = set(path_obj.parts)

    if parts & EXCLUDED_DIRS:
        return True

    name = path_obj.name.lower()

    # Common bundled/minified files
    if ".min." in name:
        return True

    return False


# ============================================================
# Count source files in one repository
# ============================================================

def count_repo_files(repo_name, tree_oid):

    encoded_repo = "/".join(
        urllib.parse.quote(part, safe="")
        for part in repo_name.split("/")
    )

    data = github_rest(
        f"/repos/{encoded_repo}/git/trees/"
        f"{tree_oid}?recursive=1"
    )

    if data.get("truncated"):
        print(
            f"WARNING: GitHub truncated the tree "
            f"for {repo_name}"
        )

    counts = Counter()

    for item in data.get("tree", []):

        if item.get("type") != "blob":
            continue

        path = item["path"]

        if excluded_file(path):
            continue

        extension = Path(path).suffix.lower()

        language = LANGUAGE_EXTENSIONS.get(
            extension
        )

        if language is not None:
            counts[language] += 1

    return counts


# ============================================================
# Count source files across all contributed repositories
# ============================================================

file_language_counts = Counter()

result_repos = []


for repo in repos.values():

    print(
        f"Counting source files in "
        f"{repo['name']}..."
    )

    counts = count_repo_files(
        repo["name"],
        repo["tree_oid"],
    )

    file_language_counts.update(counts)

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

        "commits":
            repo["commit_count"],

        "pull_requests":
            repo["pr_count"],

        "years":
            sorted(repo["years"]),

        "source_files":
            dict(
                counts.most_common()
            ),

        "total_source_files":
            sum(counts.values()),

    })


result_repos.sort(
    key=lambda x: (
        not x["external"],
        x["repository"].lower(),
    )
)


# ============================================================
# Save audit information
# ============================================================

with open(
    OUT / "contributed-file-repos.json",
    "w",
) as f:

    json.dump(
        {
            "username": USERNAME,

            "repositories":
                result_repos,

            "overall_file_counts":
                dict(
                    file_language_counts.most_common()
                ),
        },
        f,
        indent=2,
    )


# ============================================================
# Prepare SVG data
# ============================================================

MAX_LANGUAGES = 8

top_languages = (
    file_language_counts
    .most_common(MAX_LANGUAGES)
)

total_files = sum(
    file_language_counts.values()
)

repos_with_files = sum(
    repo["total_source_files"] > 0
    for repo in result_repos
)

external_repos = sum(
    repo["external"]
    and repo["total_source_files"] > 0
    for repo in result_repos
)


WIDTH = 495

ROW_HEIGHT = 30

HEIGHT = max(
    210,
    145
    + ROW_HEIGHT
    * len(top_languages)
)


# ============================================================
# SVG helper
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
# Start SVG
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
    "Languages across source files",
    20,
    600,
    "#0969da",
)}

{txt(
    24,
    60,
    (
        f"{total_files} source files "
        f"across {repos_with_files} public repositories "
        f"· {external_repos} owned by others"
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

    for language, count in top_languages:

        fraction = (
            count / total_files
        )

        segment_width = (
            fraction * BAR_WIDTH
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
        "No recognized source files found.",
        13,
    )

else:

    for language, count in top_languages:

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
# Console summary
# ============================================================

print()
print("File-language summary")
print("---------------------")

for language, count in file_language_counts.most_common():

    percentage = (
        100 * count / total_files
        if total_files > 0
        else 0
    )

    print(
        f"{language:20s}"
        f"{count:6d} files "
        f"{percentage:6.2f}%"
    )


print()
print(
    "Generated: "
    "generated/contributed-file-languages.svg"
)

print(
    "Audit file: "
    "generated/contributed-file-repos.json"
)