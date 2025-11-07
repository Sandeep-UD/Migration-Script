import os
import requests
import time
import csv
import json
from dotenv import load_dotenv

# Load .env file
load_dotenv()
GITHUB_TOKEN = os.getenv("GH_PAT")
ORG_NAME = os.getenv("GH_ORG")

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
}

OUTPUT_FILE = "environment_reviewers.csv"

def check_rate_limit():
    url = "https://api.github.com/rate_limit"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        data = response.json()
        remaining = data['rate']['remaining']
        reset_time = data['rate']['reset']
        if remaining == 0:
            sleep_time = int(reset_time - time.time()) + 5
            print(f"[!] Rate limit reached. Sleeping for {sleep_time} seconds...")
            time.sleep(sleep_time)
    else:
        print("[!] Failed to check rate limit")

def fetch_all_repos(org):
    print("[+] Fetching repositories...")
    repos = []
    page = 1
    while True:
        check_rate_limit()
        url = f"https://api.github.com/orgs/{org}/repos?per_page=100&page={page}&type=all"
        response = requests.get(url, headers=HEADERS)
        if response.status_code != 200:
            print(f"[!] Error fetching repos: {response.status_code} - {response.text}")
            break

        page_data = response.json()
        if not page_data:
            break

        repos.extend(page_data)
        page += 1
    print(f"[+] Total repositories fetched: {len(repos)}")
    return repos

def fetch_environments(repo_full_name):
    check_rate_limit()
    url = f"https://api.github.com/repos/{repo_full_name}/environments"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json().get("environments", [])
    else:
        print(f"[!] Error fetching environments for {repo_full_name}: {response.status_code}")
        return []

def fetch_environment_details(repo_full_name, environment_name):
    check_rate_limit()
    url = f"https://api.github.com/repos/{repo_full_name}/environments/{environment_name}"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"[!] Error fetching environment details for {repo_full_name}/{environment_name}: {response.status_code}")
        return {}

def extract_reviewers_from_rules(protection_rules):
    reviewers_list = []
    if not protection_rules:
        return [{
            "type": "required_reviewers",
            "reviewer_id": "None",
            "reviewer_login": "None",
            "reviewer_name": "None",
            "reviewer_type": "None"
        }]
    for rule in protection_rules:
        if rule.get("type") == "required_reviewers":
            for reviewer in rule.get("reviewers", []):
                r = reviewer.get("reviewer", {})
                reviewers_list.append({
                    "type": rule.get("type"),
                    "reviewer_id": r.get("id", "None"),
                    "reviewer_login": r.get("login", "None"),
                    "reviewer_name": r.get("name", "None"),
                    "reviewer_type": r.get("type", "None")
                })
    if not reviewers_list:
        reviewers_list.append({
            "type": "required_reviewers",
            "reviewer_id": "None",
            "reviewer_login": "None",
            "reviewer_name": "None",
            "reviewer_type": "None"
        })
    return reviewers_list

def main():
    repos = fetch_all_repos(ORG_NAME)

    with open(OUTPUT_FILE, mode="w", newline="", encoding="utf-8") as csvfile:
        fieldnames = [
            "repository", "environment", "environment_id", "environment_url",
            "created_at", "updated_at", "can_admins_bypass", "wait_timer",
            "deployment_branch_policy", "type", "reviewer_id", "reviewer_login",
            "reviewer_name", "reviewer_type"
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for repo in repos:
            repo_name = repo["full_name"]
            print(f"[~] Processing: {repo_name}")
            environments = fetch_environments(repo_name)

            for env in environments:
                env_name = env.get("name")
                env_id = env.get("id")
                env_url = env.get("url")
                created_at = env.get("created_at")
                updated_at = env.get("updated_at")
                deployment_branch_policy = env.get("deployment_branch_policy")
                # Convert deployment_branch_policy dict to string for CSV
                if deployment_branch_policy is not None:
                    deployment_branch_policy = json.dumps(deployment_branch_policy)
                else:
                    deployment_branch_policy = ""

                # Fetch full environment details for protection_rules
                env_details = fetch_environment_details(repo_name, env_name)
                protection_rules = env_details.get("protection_rules", [])
                can_admins_bypass = None
                wait_timer = None
                # Try to extract from the first rule if present
                for rule in protection_rules:
                    if rule.get("type") == "required_reviewers":
                        can_admins_bypass = rule.get("can_admins_bypass")
                        wait_timer = rule.get("wait_timer")
                        break

                reviewers = extract_reviewers_from_rules(protection_rules)
                for reviewer in reviewers:
                    writer.writerow({
                        "repository": repo_name,
                        "environment": env_name,
                        "environment_id": env_id,
                        "environment_url": env_url,
                        "created_at": created_at,
                        "updated_at": updated_at,
                        "can_admins_bypass": can_admins_bypass,
                        "wait_timer": wait_timer,
                        "deployment_branch_policy": deployment_branch_policy,
                        "type": reviewer.get("type"),
                        "reviewer_id": reviewer.get("reviewer_id"),
                        "reviewer_login": reviewer.get("reviewer_login"),
                        "reviewer_name": reviewer.get("reviewer_name"),
                        "reviewer_type": reviewer.get("reviewer_type"),
                    })

    print(f"[✓] Done. Output saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()