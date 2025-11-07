import csv
import os
import time
import requests
from dotenv import load_dotenv
from datetime import datetime

# Load .env file
load_dotenv()
GITHUB_TOKEN = os.getenv("GH_PAT")
ORG_NAME = os.getenv("GH_ORG")

# GitHub API setup
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}
BASE_URL = "https://api.github.com"
CSV_FILE = "org_actions_variables.csv"
ERROR_LOG_DIR = "error_logs"

# Ensure error log directory exists
os.makedirs(ERROR_LOG_DIR, exist_ok=True)

def log_error(message):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(ERROR_LOG_DIR, f"errors_{timestamp}.log")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(message + "\n")
    print(f"❌ {message}")

def handle_rate_limit(response):
    if response.status_code == 403 and 'X-RateLimit-Remaining' in response.headers:
        remaining = int(response.headers.get("X-RateLimit-Remaining", 1))
        if remaining == 0:
            reset_time = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
            wait = max(reset_time - int(time.time()), 0)
            print(f"Rate limit reached. Waiting for {wait} seconds...")
            time.sleep(wait + 1)
            return True
    return False

def fetch_org_repositories(org):
    repos = []
    page = 1
    while True:
        url = f"{BASE_URL}/orgs/{org}/repos?per_page=100&page={page}"
        while True:
            response = requests.get(url, headers=HEADERS)
            if handle_rate_limit(response):
                continue
            if response.status_code != 200:
                msg = f"Error fetching repos for org {org} (page {page}): {response.status_code} {response.text}"
                log_error(msg)
                return repos
            break
        data = response.json()
        if not data:
            break
        repos.extend(data)
        page += 1
    return repos

def fetch_actions_variables(owner, repo):
    vars_list = []
    page = 1
    while True:
        url = f"{BASE_URL}/repos/{owner}/{repo}/actions/variables?per_page=100&page={page}"
        while True:
            response = requests.get(url, headers=HEADERS)
            if handle_rate_limit(response):
                continue
            if response.status_code == 404:
                # Actions might not be enabled
                return vars_list
            elif response.status_code != 200:
                msg = f"Error fetching variables for {repo} (page {page}): {response.status_code} {response.text}"
                log_error(msg)
                return vars_list
            break
        data = response.json().get("variables", [])
        if not data:
            break
        vars_list.extend(data)
        page += 1
    return vars_list

def main():
    if not ORG_NAME:
        log_error("ORG_NAME is missing in .env")
        return

    print(f"🔍 Fetching repositories for organization: {ORG_NAME}")
    repos = fetch_org_repositories(ORG_NAME)
    print(f"✅ Found {len(repos)} repositories")

    with open(CSV_FILE, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Repository", "Variable Name", "Value"])

        for repo in repos:
            repo_name = repo["name"]
            print(f"📦 Fetching variables for: {repo_name}")
            variables = fetch_actions_variables(ORG_NAME, repo_name)
            for var in variables:
                writer.writerow([repo_name, var["name"], var["value"]])

    print(f"\n✅ Done. Output saved to `{CSV_FILE}`")

if __name__ == "__main__":
    main()