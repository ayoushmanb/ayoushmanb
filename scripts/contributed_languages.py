import os
import json
import html
import urllib.request
from collections import Counter
from pathlib import Path


# ============================================================
# Configuration
# ============================================================

USERNAME = os.getenv("GITHUB_USERNAME", "ayoushmanb")
TOKEN = os.environ["GITHUB_TOKEN"]
API = "https://api.github.com/graphql"

OUT = Path("generated")
OUT.mkdir(exist_ok=True)


# ============================================================
# GraphQL helper
# ============================================================

def graphql(query, variables):

    payload = json.dumps({
        "query": query,
        "variables": variables
    }).encode()

    request = urllib.request.Request(
        API,
        data=payload,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "github-language-card",
        },
    )

    with urllib.request.urlopen(request) as response:
        result = json.load(response)

    if "errors" in result:
        raise RuntimeError(
            json.dumps(
                result["errors"],
                indent=2
            )
        )

    return result["data"]


# ============================================================
# 1. Find every year in which this user contributed
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
    {
        "login": USERNAME
    }
)

years = sorted(
    data[
        "user"
    ][
        "contributionsCollection"
    ][
        "contributionYears"
    ]
)

print(
    "Contribution years:",
    years
)


# ============================================================
# 2. Get repositories for commit + PR contributions
# ============================================================

repo_fragment = """
repository {
  nameWithOwner
  url
  isPrivate

  owner {
    login
  }

  languages(
    first: 20,
    orderBy: {
      field: SIZE,
      direction: DESC
    }
  ) {
    totalSize

    edges {
      size

      node {
        name
        color
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


repos = {}


def add_repo(
    item,
    contribution_type,
    year,
):

    repo = item["repository"]

    # Exclude private repositories
    if repo["isPrivate"]:
        return

    language_edges = (
        repo[
            "languages"
        ][
            "edges"
        ]
    )

    # No recognized programming language
    if not language_edges:
        return

    name = repo[
        "nameWithOwner"
    ]

    if name not in repos:

        repos[name] = {
            "name":
                name,

            "url":
                repo["url"],

            "owner":
                repo[
                    "owner"
                ][
                    "login"
                ],

            "commit_count":
                0,

            "pr_count":
                0,

            "years":
                set(),

            "languages":
                language_edges,
        }

    count = (
        item[
            "contributions"
        ][
            "totalCount"
        ]
    )

    if contribution_type == "commit":

        repos[
            name
        ][
            "commit_count"
        ] += count

    if contribution_type == "pr":

        repos[
            name
        ][
            "pr_count"
        ] += count

    repos[
        name
    ][
        "years"
    ].add(year)


# ============================================================
# Read contributions year by year
# ============================================================

for year in years:

    print(
        f"Reading {year}..."
    )

    data = graphql(
        contribution_query,
        {
            "login":
                USERNAME,

            "from":
                f"{year}-01-01T00:00:00Z",

            "to":
                f"{year}-12-31T23:59:59Z",
        },
    )

    collection = (
        data[
            "user"
        ][
            "contributionsCollection"
        ]
    )

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
# 3. Determine primary language for each contributed repo
#
# ONE REPOSITORY = ONE VOTE
#
# Example:
#
# repo 1 -> Python
# repo 2 -> Python
# repo 3 -> R
#
# result:
#
# Python = 2
# R      = 1
# ============================================================

language_counts = Counter()
language_colors = {}

result_repos = []


# Sort repository names so output is deterministic
for repo_name in sorted(
    repos,
    key=str.lower,
):

    repo = repos[
        repo_name
    ]

    # Sort primarily by language size.
    #
    # If two languages have exactly the same size,
    # use language name as a deterministic tie-breaker.
    languages = sorted(
        repo[
            "languages"
        ],
        key=lambda x: (
            -x["size"],
            x[
                "node"
            ][
                "name"
            ].lower(),
        ),
    )

    primary = (
        languages[
            0
        ][
            "node"
        ][
            "name"
        ]
    )

    color = (
        languages[
            0
        ][
            "node"
        ][
            "color"
        ]
        or "#8c959f"
    )

    language_counts[
        primary
    ] += 1

    language_colors[
        primary
    ] = color

    external = (
        repo[
            "owner"
        ].lower()
        != USERNAME.lower()
    )

    result_repos.append({
        "repository":
            repo["name"],

        "owner":
            repo["owner"],

        "external":
            external,

        "primary_language":
            primary,

        "commits":
            repo[
                "commit_count"
            ],

        "pull_requests":
            repo[
                "pr_count"
            ],

        "years":
            sorted(
                repo[
                    "years"
                ]
            ),
    })


# External repositories first,
# then alphabetical repository name.
result_repos.sort(
    key=lambda x: (
        not x[
            "external"
        ],
        x[
            "repository"
        ].lower(),
    )
)


# ============================================================
# Save audit JSON
# ============================================================

with open(
    OUT / "contributed-repos.json",
    "w",
    encoding="utf-8",
) as f:

    json.dump(
        result_repos,
        f,
        indent=2,
    )


# ============================================================
# 4. Generate SVG
# ============================================================

# Deterministic ranking:
#
# 1. larger repository count first
# 2. alphabetically if tied
top_languages = sorted(
    language_counts.items(),
    key=lambda x: (
        -x[1],
        x[0].lower(),
    ),
)[:8]


total_repos = sum(
    language_counts.values()
)


external_repos = sum(
    1
    for x in result_repos
    if x[
        "external"
    ]
)


WIDTH = 495

HEIGHT = (
    155
    + 30
    * len(
        top_languages
    )
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
# SVG header
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
    "Languages across contributed repositories",
    20,
    600,
    "#0969da",
)}

{txt(
    24,
    60,
    (
        f"{total_repos} public repositories "
        f"· {external_repos} owned by others"
    ),
    12,
)}
"""


# ============================================================
# Stacked language bar
# ============================================================

BAR_X = 24
BAR_Y = 80
BAR_WIDTH = 447
BAR_HEIGHT = 10

position = BAR_X


if total_repos > 0:

    for language, count in top_languages:

        fraction = (
            count
            / total_repos
        )

        segment_width = (
            fraction
            * BAR_WIDTH
        )

        color = (
            language_colors.get(
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
# Language list
# ============================================================

y = 125


if total_repos == 0:

    svg += txt(
        24,
        y,
        "No qualifying public repositories found.",
        13,
    )

else:

    for language, count in top_languages:

        color = (
            language_colors.get(
                language,
                "#8c959f",
            )
        )

        percent = (
            100
            * count
            / total_repos
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
                f"repo"
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

        y += 30


svg += "</svg>"


# ============================================================
# Save SVG
# ============================================================

with open(
    OUT
    / "contributed-languages.svg",
    "w",
    encoding="utf-8",
) as f:

    f.write(svg)


# ============================================================
# Console summary
# ============================================================

print()
print(
    "Repositories included:"
)
print(
    "----------------------"
)


for repo in result_repos:

    owner_type = (
        "EXTERNAL"
        if repo[
            "external"
        ]
        else "OWN"
    )

    print(
        f"{owner_type:8s} "
        f"{repo['repository']:50s} "
        f"{repo['primary_language']}"
    )


print()

print(
    f"Total repositories: "
    f"{total_repos}"
)

print(
    f"External repositories: "
    f"{external_repos}"
)

print()

print(
    "Language summary:"
)

for language, count in top_languages:

    percentage = (
        100
        * count
        / total_repos
        if total_repos
        else 0
    )

    print(
        f"  {language:20s} "
        f"{count:3d} repos "
        f"{percentage:6.2f}%"
    )


print()

print(
    "Generated: "
    "generated/"
    "contributed-languages.svg"
)

print(
    "Audit: "
    "generated/"
    "contributed-repos.json"
)