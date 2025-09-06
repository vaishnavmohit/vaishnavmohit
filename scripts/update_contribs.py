#!/usr/bin/env python3
"""
Update lifetime contribution statistics in the README.

Counts (GitHub definitions):
- totalCommitContributions: Commits authored on the default branch or gh-pages of repositories you own.
- restrictedContributions: Commits in private repos (shown only if token has access and privacy allows).
- totalPullRequestContributions
- totalIssueContributions
- totalPullRequestReviewContributions
- repositoryContributions
We sum these into lifetime_total (simple additive aggregate).

Limitations:
- Does NOT include commits outside default/gh-pages branches.
- "Restricted" merges into total for transparency (optional).
- Yearly slicing required because contributionsCollection cannot exceed 1 year.

Environment:
- Requires GH_LIFETIME_TOKEN or GH_TOKEN (fallback).
"""

import os
import sys
import datetime
import textwrap
import requests
from dataclasses import dataclass

GITHUB_API = "https://api.github.com/graphql"
USER_LOGIN = "vaishnavmohit"
README_PATH = "README.md"
START_MARK = "<!-- LIFETIME_CONTRIBS_START -->"
END_MARK = "<!-- LIFETIME_CONTRIBS_END -->"

token = os.getenv("GH_LIFETIME_TOKEN") or os.getenv("GH_TOKEN")
if not token:
    print("ERROR: GH_LIFETIME_TOKEN (or GH_TOKEN) not set.", file=sys.stderr)
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

def gh_query(query: str, variables: dict):
    r = requests.post(GITHUB_API, json={"query": query, "variables": variables}, headers=headers)
    if r.status_code != 200:
        raise RuntimeError(f"GitHub API HTTP {r.status_code}: {r.text}")
    j = r.json()
    if "errors" in j:
        raise RuntimeError(f"GraphQL errors: {j['errors']}")
    return j["data"]

QUERY_USER_CREATED = """
query($login:String!) {
  user(login:$login) {
    createdAt
  }
}
"""

QUERY_CONTRIBS = """
query($login:String!, $from:DateTime!, $to:DateTime!) {
  user(login:$login) {
    contributionsCollection(from:$from, to:$to) {
      totalCommitContributions
      restrictedContributions
      totalPullRequestContributions
      totalIssueContributions
      totalPullRequestReviewContributions
      repositoryContributions
    }
  }
}
"""

from dataclasses import dataclass
@dataclass
class YearAggregate:
    year: int
    totalCommitContributions: int = 0
    restrictedContributions: int = 0
    totalPullRequestContributions: int = 0
    totalIssueContributions: int = 0
    totalPullRequestReviewContributions: int = 0
    repositoryContributions: int = 0

def daterange_years(start: datetime.date, end: datetime.date):
    cursor = datetime.date(start.year, start.month, start.day)
    while cursor < end:
        # Use same month/day; if creation date was Feb 29 it gets tricky—simple fallback:
        try:
            next_year = datetime.date(cursor.year + 1, cursor.month, cursor.day)
        except ValueError:
            # Handle Feb 29 → Feb 28 next year
            next_year = datetime.date(cursor.year + 1, cursor.month, 28)
        to = min(next_year, end)
        yield datetime.datetime.combine(cursor, datetime.time.min), datetime.datetime.combine(to, datetime.time.min), cursor.year
        cursor = to

def main():
    data = gh_query(QUERY_USER_CREATED, {"login": USER_LOGIN})
    created_at = datetime.datetime.fromisoformat(data["user"]["createdAt"].replace("Z","+00:00")).date()
    today = datetime.date.today()

    totals = YearAggregate(year=0)
    per_year = []

    for start_dt, end_dt, year in daterange_years(created_at, today):
        contrib_data = gh_query(QUERY_CONTRIBS, {
            "login": USER_LOGIN,
            "from": start_dt.isoformat(),
            "to": end_dt.isoformat()
        })["user"]["contributionsCollection"]
        ya = YearAggregate(
            year=year,
            totalCommitContributions=contrib_data["totalCommitContributions"],
            restrictedContributions=contrib_data["restrictedContributions"],
            totalPullRequestContributions=contrib_data["totalPullRequestContributions"],
            totalIssueContributions=contrib_data["totalIssueContributions"],
            totalPullRequestReviewContributions=contrib_data["totalPullRequestReviewContributions"],
            repositoryContributions=contrib_data["repositoryContributions"]
        )
        per_year.append(ya)
        totals.totalCommitContributions += ya.totalCommitContributions
        totals.restrictedContributions += ya.restrictedContributions
        totals.totalPullRequestContributions += ya.totalPullRequestContributions
        totals.totalIssueContributions += ya.totalIssueContributions
        totals.totalPullRequestReviewContributions += ya.totalPullRequestReviewContributions
        totals.repositoryContributions += ya.repositoryContributions

    lifetime_total = (
        totals.totalCommitContributions
        + totals.restrictedContributions
        + totals.totalPullRequestContributions
        + totals.totalIssueContributions
        + totals.totalPullRequestReviewContributions
        + totals.repositoryContributions
    )

    years_summary_lines = []
    for ya in per_year:
        years_summary_lines.append(
            f"- {ya.year}: commits {ya.totalCommitContributions}+restricted {ya.restrictedContributions}, PRs {ya.totalPullRequestContributions}, Issues {ya.totalIssueContributions}, Reviews {ya.totalPullRequestReviewContributions}, Repos {ya.repositoryContributions}"
        )

    block = f"""
**Lifetime Contributions (All Time)**  
Total (aggregated): **{lifetime_total}**

Breakdown (cumulative components):
- Commits (default/gh-pages): {totals.totalCommitContributions}
- Restricted (private) commits: {totals.restrictedContributions}
- Pull Requests: {totals.totalPullRequestContributions}
- Issues: {totals.totalIssueContributions}
- PR Reviews: {totals.totalPullRequestReviewContributions}
- Repositories Created: {totals.repositoryContributions}

<details>
<summary>Per-Year Raw Totals</summary>

{os.linesep.join(years_summary_lines)}

</details>

_Automated update: {datetime.datetime.utcnow().isoformat(timespec='seconds')}Z_
""".strip()

    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    if START_MARK not in content or END_MARK not in content:
        print("ERROR: Placeholder markers missing in README.", file=sys.stderr)
        sys.exit(1)

    pre, rest = content.split(START_MARK, 1)
    _, post = rest.split(END_MARK, 1)

    new_content = f"{pre}{START_MARK}\n{block}\n{END_MARK}{post}"

    if new_content != content:
        with open(README_PATH, "w", encoding="utf-8") as f:
            f.write(new_content)
        print("README updated with lifetime contributions.")
    else:
        print("No changes to README.")

if __name__ == "__main__":
    main()
