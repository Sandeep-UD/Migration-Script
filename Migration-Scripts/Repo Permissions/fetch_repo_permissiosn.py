import requests
import csv
import os
import logging
import time
from dotenv import load_dotenv

# === LOAD CONFIGURATION FROM .env ===
load_dotenv()
GITHUB_TOKEN = os.getenv("GH_PAT")
ORG_NAME = os.getenv("GH_ORG")
TARGET_ORG_NAME = os.getenv("TARGET_GH_ORG", ORG_NAME)  # Defaults to source org if not set
CSV_FILE = "user_repo_permission.csv"

# === HEADERS ===
headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

# === LOGGING CONFIGURATION ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("repo-permissions.log"),
        logging.StreamHandler()
    ]
)

def handle_rate_limit(response):
    remaining = int(response.headers.get("X-RateLimit-Remaining", 1))
    reset_time = int(response.headers.get("X-RateLimit-Reset", time.time()))
    if remaining == 0:
        wait_time = reset_time - int(time.time())
        if wait_time > 0:
            logging.warning(f"Rate limit reached. Waiting for {wait_time} seconds...")
            time.sleep(wait_time + 1)

def fetch_repos(org):
    repos = []
    page = 1
    while True:
        url = f"https://api.github.com/orgs/{org}/repos"
        params = {"per_page": 100, "page": page, "type": "all"}
        response = requests.get(url, headers=headers, params=params)
        handle_rate_limit(response)
        if response.status_code != 200:
            logging.error(f"Failed to fetch repos: {response.status_code} - {response.text}")
            break
        data = response.json()
        if not data:
            break
        repos.extend(data)
        page += 1
    logging.info(f"Fetched {len(repos)} repositories for organization '{org}'.")
    return repos

def fetch_collaborators(org, repo):
    collaborators = []
    page = 1
    while True:
        url = f"https://api.github.com/repos/{org}/{repo}/collaborators"
        params = {"affiliation": "direct", "per_page": 100, "page": page}
        response = requests.get(url, headers=headers, params=params)
        handle_rate_limit(response)
        if response.status_code != 200:
            logging.error(f"Failed to fetch collaborators for {repo}: {response.status_code} - {response.text}")
            return []
        data = response.json()
        if not data:
            break
        collaborators.extend(data)
        page += 1
    return collaborators

def get_collaborator_role(org, repo, username):
    url = f"https://api.github.com/repos/{org}/{repo}/collaborators/{username}/permission"
    response = requests.get(url, headers=headers)
    handle_rate_limit(response)
    if response.status_code != 200:
        logging.error(f"Failed to fetch permission for {username} in {repo}: {response.status_code} - {response.text}")
        return "N/A"
    return response.json().get("permission", "N/A")

def normalize_permission(permission):
    permission_mapping = {
        "admin": "admin",
        "write": "push",
        "read": "pull",
        "maintain": "maintain",
        "triage": "triage"
    }
    return permission_mapping.get(permission.lower(), permission)

def main():
    logging.info("Starting to fetch repository permissions.")
    rows = []

    if not GITHUB_TOKEN or not ORG_NAME:
        logging.error("GITHUB_PAT or GITHUB_ORG is not set.")
        return

    repos = fetch_repos(ORG_NAME)

    for repo in repos:
        repo_name = repo.get("name")
        logging.info(f"Processing repository: {repo_name}")
        collaborators = fetch_collaborators(ORG_NAME, repo_name)

        for user in collaborators:
            username = user.get("login")
            user_role = user.get("role_name")
            if not user_role:
                user_role = get_collaborator_role(ORG_NAME, repo_name, username)
            normalized_permission = normalize_permission(user_role)

            rows.append([
                ORG_NAME,
                repo_name,
                username,
                user_role,
                normalized_permission,
                TARGET_ORG_NAME,
                repo_name,
                ""  # EMU User
            ])

    try:
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Source Organization",
                "Source Repository",
                "Username",
                "Original Permission",
                "Normalized Permission",
                "Target Organization",
                "Target Repository",
                "EMU User"
            ])
            writer.writerows(rows)
        logging.info(f"Data written to {CSV_FILE} with {len(rows)} permission entries")
    except Exception as e:
        logging.error(f"Failed to write to CSV: {e}")

    logging.info("Script execution completed.")

if __name__ == "__main__":
    main()
