import os
import time
import csv
import requests
from dotenv import load_dotenv

load_dotenv()
GITHUB_TOKEN = os.getenv("GH_PAT")
ORG_NAME = os.getenv("GH_ORG")

BASE_URL = "https://api.github.com"
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}
CSV_FILE = "github_action_runners.csv"

def handle_rate_limit(response):
    if response.status_code == 403 and 'X-RateLimit-Remaining' in response.headers:
        remaining = int(response.headers['X-RateLimit-Remaining'])
        if remaining == 0:
            reset = int(response.headers["X-RateLimit-Reset"])
            wait = max(reset - int(time.time()), 0)
            print(f"⏳ Rate limit hit. Waiting {wait} seconds...")
            time.sleep(wait)
            return True
    return False

def fetch_org_repositories(org):
    repos = []
    page = 1
    while True:
        url = f"{BASE_URL}/orgs/{org}/repos?per_page=100&page={page}"
        response = requests.get(url, headers=HEADERS)
        if handle_rate_limit(response):
            continue
        if response.status_code != 200:
            print(f"❌ Error fetching repos (HTTP {response.status_code}): {response.text}")
            break
        data = response.json()
        if not data:
            break
        repos.extend(data)
        page += 1
    return repos

def fetch_repo_runners(owner, repo):
    runners = []
    page = 1
    while True:
        url = f"{BASE_URL}/repos/{owner}/{repo}/actions/runners?per_page=100&page={page}"
        response = requests.get(url, headers=HEADERS)
        if handle_rate_limit(response):
            continue
        if response.status_code != 200:
            print(f"❌ Failed to fetch runners for {owner}/{repo} (HTTP {response.status_code}): {response.text}")
            break
        data = response.json()
        runners.extend(data.get("runners", []))
        if "next" not in response.links:
            break
        page += 1
    return runners

def main():
    if not GITHUB_TOKEN or not ORG_NAME:
        print("❌ Missing GH_PAT or GH_ORG in .env")
        return

    print(f"🔍 Fetching repositories for org: {ORG_NAME}")
    repos = fetch_org_repositories(ORG_NAME)
    print(f"✅ Found {len(repos)} repositories")

    with open(CSV_FILE, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([
            "Repository",
            "Runner ID",
            "Runner Name",
            "OS",
            "Status",
            "Busy",
            "Labels"
        ])

        for repo in repos:
            repo_name = repo["name"]
            owner = repo["owner"]["login"]
            print(f"\n📦 Repo: {repo_name}")
            runners = fetch_repo_runners(owner, repo_name)
            if not runners:
                print("  No runners found.")
                continue

            for runner in runners:
                labels = ", ".join(label.get("name") for label in runner.get("labels", []))
                writer.writerow([
                    repo_name,
                    runner.get("id"),
                    runner.get("name"),
                    runner.get("os"),
                    runner.get("status"),
                    runner.get("busy"),
                    labels
                ])

    print(f"\n✅ CSV export complete: {CSV_FILE}")

if __name__ == "__main__":
    main()
