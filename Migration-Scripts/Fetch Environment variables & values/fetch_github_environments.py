import csv
import os
import time
import requests
from dotenv import load_dotenv

# Load .env
load_dotenv()
GITHUB_TOKEN = os.getenv("GH_PAT")
ORG_NAME = os.getenv("GH_ORG")

# Constants
BASE_URL = "https://api.github.com"
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}
CSV_FILE = "github_environments_variables.csv"

# Handle API rate limit
def handle_rate_limit(response):
    if response.status_code == 403 and 'X-RateLimit-Remaining' in response.headers:
        remaining = int(response.headers["X-RateLimit-Remaining"])
        if remaining == 0:
            reset = int(response.headers["X-RateLimit-Reset"])
            wait = max(reset - int(time.time()), 0)
            print(f"⏳ Rate limit reached. Waiting for {wait} seconds...")
            time.sleep(wait)
            return True
    return False

# Get all org repos
def fetch_org_repositories(org):
    repos = []
    page = 1
    while True:
        url = f"{BASE_URL}/orgs/{org}/repos?per_page=100&page={page}"
        response = requests.get(url, headers=HEADERS)
        if handle_rate_limit(response):
            continue
        if response.status_code != 200:
            print(f"❌ Failed to fetch repos (HTTP {response.status_code})")
            break
        data = response.json()
        if not data:
            break
        repos.extend(data)
        page += 1
    return repos

# Get environments for a repo
def fetch_repo_environments(owner, repo):
    envs = []
    page = 1
    while True:
        url = f"{BASE_URL}/repos/{owner}/{repo}/environments?per_page=100&page={page}"
        response = requests.get(url, headers=HEADERS)
        if handle_rate_limit(response):
            continue
        if response.status_code == 404:
            break  # No environments
        if response.status_code != 200:
            print(f"❌ Failed to fetch environments for {repo} (HTTP {response.status_code})")
            break
        data = response.json().get("environments", [])
        if not data:
            break
        envs.extend(data)
        page += 1
    return envs

# Get variables for an environment
def fetch_environment_variables(owner, repo, env_name):
    url = f"{BASE_URL}/repos/{owner}/{repo}/environments/{env_name}/variables"
    response = requests.get(url, headers=HEADERS)
    if handle_rate_limit(response):
        return fetch_environment_variables(owner, repo, env_name)
    if response.status_code == 404:
        return []  # No variables
    if response.status_code != 200:
        print(f"❌ Failed to fetch variables for {repo}/{env_name} (HTTP {response.status_code})")
        return []
    return response.json().get("variables", [])

# Main script
def main():
    if not GITHUB_TOKEN or not ORG_NAME:
        print("❌ Missing GH_PAT or GH_ORG in .env")
        return

    print(f"🔍 Fetching repositories for organization: {ORG_NAME}")
    repos = fetch_org_repositories(ORG_NAME)
    print(f"✅ Found {len(repos)} repositories")

    with open(CSV_FILE, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Repository", "Environment", "Variable Name", "Value"])

        for repo in repos:
            repo_name = repo["name"]
            owner = repo["owner"]["login"]
            print(f"\n📦 Processing repo: {repo_name}")
            environments = fetch_repo_environments(owner, repo_name)

            for env in environments:
                env_name = env["name"]
                print(f"  🌍 Environment: {env_name}")
                variables = fetch_environment_variables(owner, repo_name, env_name)

                if variables:
                    for var in variables:
                        writer.writerow([repo_name, env_name, var["name"], var["value"]])
                else:
                    # Record env with no variables
                    writer.writerow([repo_name, env_name, "", ""])

    print(f"\n✅ CSV export complete: {CSV_FILE}")

if __name__ == "__main__":
    main()
