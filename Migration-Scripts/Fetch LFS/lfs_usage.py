import requests
import os
import base64
import time
import pandas as pd
from dotenv import load_dotenv

# Load GitHub token and org name from .env file
load_dotenv()
GITHUB_TOKEN = os.getenv("GH_PAT")
ORG_NAME = os.getenv("GH_ORG")  # Now loaded from .env

# GitHub API base URL
BASE_URL = "https://api.github.com"

# Headers for authentication
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

def handle_rate_limit(response):
    """Handles API rate limits by pausing execution."""
    if response.status_code == 403 and "X-RateLimit-Remaining" in response.headers:
        remaining = int(response.headers["X-RateLimit-Remaining"])
        reset_time = int(response.headers["X-RateLimit-Reset"])
        wait_time = reset_time - time.time()
        
        if remaining == 0:
            print(f"Rate limit exceeded. Waiting for {int(wait_time)} seconds...")
            time.sleep(wait_time + 1)
            return True  # Indicate retry is needed
    return False  # No rate limit issues

def get_repositories(org):
    """Fetch all repositories under the organization, handling pagination."""
    repos = []
    page = 1
    while True:
        url = f"{BASE_URL}/orgs/{org}/repos?per_page=100&page={page}"
        response = requests.get(url, headers=HEADERS)

        if handle_rate_limit(response):
            continue  # Retry after waiting

        if response.status_code != 200:
            print(f"Error fetching repositories: {response.json()}")
            return []

        data = response.json()
        if not data:
            break

        repos.extend(data)
        if len(repos) % 100 == 0:  # Delay every 100 records
            print("Processed 100 repositories, waiting for 10 seconds...")
            time.sleep(10)

        page += 1
        time.sleep(1)  # Prevent hitting rate limits

    return repos

def get_branches(repo_name):
    """Fetch all branches of a repository."""
    branches = []
    page = 1
    while True:
        url = f"{BASE_URL}/repos/{ORG_NAME}/{repo_name}/branches?per_page=100&page={page}"
        response = requests.get(url, headers=HEADERS)

        if handle_rate_limit(response):
            continue  # Retry after waiting

        if response.status_code != 200:
            print(f"Error fetching branches for {repo_name}: {response.json()}")
            return []

        data = response.json()
        if not data:
            break

        branches.extend([branch["name"] for branch in data])
        page += 1
        time.sleep(1)

    return branches

def check_lfs_usage(repo_name, branch_name):
    """Check if a repository has LFS enabled by inspecting .gitattributes file."""
    url = f"{BASE_URL}/repos/{ORG_NAME}/{repo_name}/contents/.gitattributes?ref={branch_name}"
    
    while True:
        response = requests.get(url, headers=HEADERS)

        if handle_rate_limit(response):
            continue  # Retry after waiting

        if response.status_code == 200:
            try:
                file_content = response.json().get("content", "")
                decoded_content = base64.b64decode(file_content).decode("utf-8")
                if "filter=lfs" in decoded_content:
                    return True
            except Exception as e:
                print(f"Error decoding .gitattributes for {repo_name}: {e}")
        
        return False  # Return False if LFS is not found

def main():
    """Main function to check LFS usage across all repositories and branches."""
    if not ORG_NAME:
        print("Error: GITHUB_ORG not set in .env file.")
        return
    repositories = get_repositories(ORG_NAME)
    results = []

    print("\nChecking LFS usage for repositories in the organization:", ORG_NAME)
    print("=" * 90)
    print(f"{'Repository':<30} | {'Branches':<40} | {'Using LFS'}")
    print("-" * 90)

    for index, repo in enumerate(repositories, start=1):
        repo_name = repo["name"]
        branches = get_branches(repo_name)

        lfs_used = "No"
        for branch in branches:
            if check_lfs_usage(repo_name, branch):
                lfs_used = "Yes"
                break

        print(f"{repo_name:<30} | {', '.join(branches):<40} | {lfs_used}")
        results.append([repo_name, ", ".join(branches), lfs_used])

        if index % 100 == 0:
            print("Processed 100 repositories, waiting for 10 seconds...")
            time.sleep(10)

    print("=" * 90)
    print("LFS check completed.")

    csv_filename = f"{ORG_NAME}_lfs_usage.csv"
    df = pd.DataFrame(results, columns=["Repository", "Branches", "Using LFS"])
    df.to_csv(csv_filename, index=False)
    print(f"Results saved to {csv_filename}")

if __name__ == "__main__":
    main()