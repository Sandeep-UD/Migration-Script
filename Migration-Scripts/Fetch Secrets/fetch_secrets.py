import os
import csv
import time
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = os.getenv("GH_PAT")
ORG = os.getenv("GH_ORG")

HEADERS = {"Authorization": f"token {TOKEN}"}

def log_error(message):
    with open("error.log", "a") as f:
        f.write(f"{message}\n")

def github_get(url, params=None):
    while True:
        try:
            response = requests.get(url, headers=HEADERS, params=params)
            if response.status_code == 403 and "rate limit" in response.text.lower():
                reset_time = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
                wait = max(reset_time - int(time.time()), 1)
                print(f"Rate limit reached. Waiting {wait} seconds...")
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response
        except Exception as e:
            log_error(f"Error fetching {url}: {e}")
            return None

def fetch_all_repos():
    repos = []
    page = 1
    per_page = 100
    while True:
        url = f"https://api.github.com/orgs/{ORG}/repos"
        params = {"per_page": per_page, "page": page}
        response = github_get(url, params)
        if not response:
            break
        data = response.json()
        if not data:
            break
        repos.extend(data)
        if len(data) < per_page:
            break
        page += 1
    return repos

def fetch_repo_secrets(owner, repo):
    secrets = []
    page = 1
    per_page = 100
    while True:
        url = f"https://api.github.com/repos/{owner}/{repo}/actions/secrets"
        params = {"per_page": per_page, "page": page}
        response = github_get(url, params)
        if not response:
            break
        data = response.json()
        secrets.extend(data.get("secrets", []))
        if len(data.get("secrets", [])) < per_page:
            break
        page += 1
    return secrets

def write_csv(secrets):
    with open("secrets_result.csv", "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["repo", "name", "value"]  # Only repo, name, value (empty)
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for secret in secrets:
            writer.writerow({
                "repo": secret["repo"],
                "name": secret["name"],
                "value": ""  # Leave value empty
            })

if __name__ == "__main__":
    if not TOKEN or not ORG:
        print("Missing environment variables. Check your .env file.")
    else:
        all_secrets = []
        repos = fetch_all_repos()
        print(f"Found {len(repos)} repositories in org '{ORG}'.")
        for repo in repos:
            repo_name = repo["name"]
            print(f"Fetching secrets for repo: {repo_name}")
            secrets = fetch_repo_secrets(ORG, repo_name)
            for secret in secrets:
                all_secrets.append({
                    "repo": repo_name,
                    "name": secret.get("name", "")
                })
        write_csv(all_secrets)
        print(f"Fetched secrets for {len(repos)} repos. Output written to secrets_result.csv.")