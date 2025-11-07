import requests
import csv
import os
import time
from datetime import datetime
from dotenv import load_dotenv
from requests.exceptions import ConnectionError, ChunkedEncodingError

# Load environment variables
load_dotenv()
GITHUB_PAT = os.getenv("GH_PAT")
GITHUB_ORG = os.getenv("GH_ORG")

HEADERS = {
    "Authorization": f"Bearer {GITHUB_PAT}",
    "Accept": "application/vnd.github+json"
}

# ------------------- Logging -------------------
def log_error(msg):
    with open("error_log.txt", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} - {msg}\n")

# ------------------- API Call Helper -------------------
def github_api_get(url, params=None, max_retries=5):
    retries = 0
    while retries < max_retries:
        try:
            response = requests.get(url, headers=HEADERS, params=params)
            if response.status_code == 403 and "rate limit" in response.text.lower():
                reset_time = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
                sleep_time = max(reset_time - int(time.time()), 1)
                print(f"Rate limit hit. Sleeping for {sleep_time} seconds...")
                time.sleep(sleep_time)
                continue
            if response.status_code not in (200, 201):
                log_error(f"Failed GET {url}: {response.status_code} {response.text}")
                return None
            return response.json()
        except (ConnectionError, ChunkedEncodingError) as e:
            retries += 1
            log_error(f"Connection error on {url}: {e}. Retry {retries}/{max_retries}")
            time.sleep(5 * retries)  # Exponential backoff
        except Exception as e:
            log_error(f"Unexpected error on {url}: {e}")
            return None
    log_error(f"Max retries exceeded for {url}")
    return None

# ------------------- Fetch Repositories -------------------
def get_repos(org):
    repos = []
    page = 1
    per_page = 100
    while True:
        url = f"https://api.github.com/orgs/{org}/repos"
        params = {"per_page": per_page, "page": page, "type": "all"}
        data = github_api_get(url, params)
        if not data:
            break
        repos.extend(data)
        if len(data) < per_page:
            break
        page += 1
    return repos

# ------------------- PR Counts -------------------
def get_pr_counts(org, repo):
    url = f"https://api.github.com/repos/{org}/{repo}/pulls"

    def count_prs(state):
        page = 1
        per_page = 100
        total = 0
        while True:
            prs = github_api_get(url, {"state": state, "per_page": per_page, "page": page})
            if not prs:
                break
            total += len(prs)
            if len(prs) < per_page:
                break
            page += 1
        return total

    open_prs = count_prs("open")
    closed_prs = 0
    merged_prs = 0

    # Count closed and merged separately
    page = 1
    per_page = 100
    while True:
        prs = github_api_get(url, {"state": "closed", "per_page": per_page, "page": page})
        if not prs:
            break
        for pr in prs:
            pr_url = f"https://api.github.com/repos/{org}/{repo}/pulls/{pr['number']}"
            pr_data = github_api_get(pr_url)
            if not pr_data:
                continue
            if pr_data.get("merged_at"):
                merged_prs += 1
            else:
                closed_prs += 1
        if len(prs) < per_page:
            break
        page += 1

    return open_prs, closed_prs, merged_prs

# ------------------- Issue Counts -------------------
def get_issue_counts(org, repo):
    url = f"https://api.github.com/repos/{org}/{repo}/issues"

    def count_issues(state):
        page = 1
        per_page = 100
        count = 0
        while True:
            issues = github_api_get(url, {"state": state, "per_page": per_page, "page": page})
            if not issues:
                break
            count += sum(1 for i in issues if "pull_request" not in i)
            if len(issues) < per_page:
                break
            page += 1
        return count

    return count_issues("open"), count_issues("closed")

# ------------------- Branches -------------------
def get_branches(org, repo):
    url = f"https://api.github.com/repos/{org}/{repo}/branches"
    branches = []
    page = 1
    per_page = 100
    while True:
        data = github_api_get(url, {"per_page": per_page, "page": page})
        if not data:
            break
        branches.extend(data)
        if len(data) < per_page:
            break
        page += 1
    return len(branches)

# ------------------- Tags -------------------
def get_tags(org, repo):
    url = f"https://api.github.com/repos/{org}/{repo}/tags"
    tags = []
    page = 1
    per_page = 100
    while True:
        data = github_api_get(url, {"per_page": per_page, "page": page})
        if not data:
            break
        tags.extend(data)
        if len(data) < per_page:
            break
        page += 1
    return len(tags)

# ------------------- Last Commit -------------------
def get_last_commit(org, repo, default_branch):
    url = f"https://api.github.com/repos/{org}/{repo}/commits"
    data = github_api_get(url, {"sha": default_branch, "per_page": 1})
    if data and len(data) > 0:
        commit = data[0]
        date = commit["commit"]["committer"]["date"]

        # Prefer the actual author instead of web-flow
        user = ""
        if commit.get("author") and commit["author"]:
            user = commit["author"].get("login") or commit["author"].get("name", "")
        elif commit.get("committer") and commit["committer"]:
            user = commit["committer"].get("login") or commit["committer"].get("name", "")
        else:
            user = commit["commit"]["committer"].get("name", "")

        return date, user
    return "", ""

# ------------------- Primary Language -------------------
def get_primary_language(repo_data):
    return repo_data.get("language", "")

# ------------------- Main -------------------
def main():
    org = GITHUB_ORG
    if not org:
        print("ORG_NAME not set in .env file.")
        return

    repos = get_repos(org)
    if not repos:
        print("No repositories found or error occurred.")
        return

    filename = f"{org}_repo_details_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with open(filename, "w", newline='', encoding="utf-8") as csvfile:
        fieldnames = [
            "Repo Name", "Visibility", "Created At", "Updated At", "Last Pushed Date", "Repo Size (MB)",
            "Primary Language", "Total Open PRs", "Total Closed PRs", "Total Merged PRs",
            "Total Open Issues", "Total Closed Issues", "Total Branches", "Total Releases",
            "Total Tags", "Last Committed Date", "Last Committed User"
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for repo in repos:
            print(f"Processing {repo['name']}...")
            try:
                open_prs, closed_prs, merged_prs = get_pr_counts(org, repo["name"])
                open_issues, closed_issues = get_issue_counts(org, repo["name"])
                branch_count = get_branches(org, repo["name"])
                tag_count = get_tags(org, repo["name"])
                last_commit_date, last_commit_user = get_last_commit(org, repo["name"], repo["default_branch"])

                releases_url = f"https://api.github.com/repos/{org}/{repo['name']}/releases"
                releases = github_api_get(releases_url, {"per_page": 1})
                total_releases = len(releases) if releases else 0

                row = {
                    "Repo Name": repo["name"],
                    "Visibility": repo["visibility"],
                    "Created At": repo["created_at"],
                    "Updated At": repo["updated_at"],
                    "Last Pushed Date": repo["pushed_at"],
                    "Repo Size (MB)": round(repo["size"] / 1024, 2),
                    "Primary Language": get_primary_language(repo),
                    "Total Open PRs": open_prs,
                    "Total Closed PRs": closed_prs,
                    "Total Merged PRs": merged_prs,
                    "Total Open Issues": open_issues,
                    "Total Closed Issues": closed_issues,
                    "Total Branches": branch_count,
                    "Total Releases": total_releases,
                    "Total Tags": tag_count,
                    "Last Committed Date": last_commit_date,
                    "Last Committed User": last_commit_user
                }

                writer.writerow(row)
            except Exception as e:
                log_error(f"Error processing {repo['name']}: {e}")
                continue

    print(f"✅ Done. Output written to {filename}")

# ------------------- Entry Point -------------------
if __name__ == "__main__":
    main()
 