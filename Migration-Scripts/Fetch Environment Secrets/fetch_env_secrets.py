import csv
import os
import time
import requests
from dotenv import load_dotenv

# Load .env
load_dotenv()
GITHUB_TOKEN = os.getenv("GH_PAT")
ORG_NAME = os.getenv("GH_ORG")

# GitHub API setup
BASE_URL = "https://api.github.com"
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}
CSV_FILE = "github_environment_secrets.csv"

# Rate limit handler
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

# Fetch organization repos
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

# Fetch environments in a repo
def fetch_repo_environments(owner, repo):
    environments = []
    page = 1
    while True:
        url = f"{BASE_URL}/repos/{owner}/{repo}/environments?per_page=100&page={page}"
        response = requests.get(url, headers=HEADERS)
        if handle_rate_limit(response):
            continue
        if response.status_code == 404:
            break
        if response.status_code != 200:
            print(f"❌ Failed to fetch environments for {repo} (HTTP {response.status_code})")
            break
        data = response.json().get("environments", [])
        if not data:
            break
        environments.extend(data)
        page += 1
    return environments

# Fetch secrets in an environment
def fetch_environment_secrets(owner, repo, env_name):
    url = f"{BASE_URL}/repos/{owner}/{repo}/environments/{env_name}/secrets"
    response = requests.get(url, headers=HEADERS)
    if handle_rate_limit(response):
        return fetch_environment_secrets(owner, repo, env_name)
    if response.status_code == 404:
        return []
    if response.status_code != 200:
        print(f"❌ Failed to fetch secrets for {repo}/{env_name} (HTTP {response.status_code})")
        return []
    return response.json().get("secrets", [])

# Main function
def main():
    if not GITHUB_TOKEN or not ORG_NAME:
        print("❌ Missing GH_PAT or GH_ORG in .env")
        return

    print(f"🔍 Fetching repositories for organization: {ORG_NAME}")
    repos = fetch_org_repositories(ORG_NAME)
    print(f"✅ Found {len(repos)} repositories")

    with open(CSV_FILE, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Repository", "Environment", "Secret Name"])

        for repo in repos:
            repo_name = repo["name"]
            owner = repo["owner"]["login"]
            print(f"\n📦 Repository: {repo_name}")
            environments = fetch_repo_environments(owner, repo_name)

            for env in environments:
                env_name = env["name"]
                print(f"  🔐 Environment: {env_name}")
                secrets = fetch_environment_secrets(owner, repo_name, env_name)

                if secrets:
                    for secret in secrets:
                        writer.writerow([repo_name, env_name, secret["name"]])
                else:
                    writer.writerow([repo_name, env_name, ""])  # No secrets

    print(f"\n✅ Export completed: {CSV_FILE}")

if __name__ == "__main__":
    main()
