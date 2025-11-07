import csv
import os
import time
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
GH_PAT = os.getenv("GH_PAT")
GH_ORG = os.getenv("GH_ORG")
API_URL = "https://api.github.com"

if not GH_PAT:
    raise ValueError("GH_PAT environment variable is not set")
if not GH_ORG:
    raise ValueError("GH_ORG environment variable is not set")

HEADERS = {
    "Authorization": f"token {GH_PAT}",  # Changed from Bearer to token
    "Accept": "application/vnd.github.v3+json",
    "X-GitHub-Api-Version": "2022-11-28"
}

CSV_INPUT = "users.csv"
CSV_OUTPUT = "output.csv"


def check_rate_limit():
    response = requests.get(f"{API_URL}/rate_limit", headers=HEADERS)
    if response.status_code != 200:
        print("[!] Failed to check rate limit.")
        return

    data = response.json()
    remaining = data['rate']['remaining']
    reset_time = data['rate']['reset']

    if remaining == 0:
        sleep_time = reset_time - int(time.time()) + 5
        print(f"[!] Rate limit exceeded. Sleeping for {sleep_time} seconds...")
        time.sleep(sleep_time)


def get_existing_org_members():
    """Fetch current members of the org using pagination."""
    members = set()
    page = 1
    while True:
        check_rate_limit()
        url = f"{API_URL}/orgs/{GH_ORG}/members?per_page=100&page={page}"
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code != 200:
            print(f"[!] Failed to fetch members (HTTP {resp.status_code})")
            break
        page_data = resp.json()
        if not page_data:
            break
        members.update(user["login"] for user in page_data)
        page += 1
    return members


def add_user_to_org(username, role="member"):
    """
    Add a user to the GitHub org with specified role using direct invitation.
    Args:
        username (str): GitHub username to add
        role (str): Role to assign (member or admin)
    """
    check_rate_limit()
    url = f"{API_URL}/orgs/{GH_ORG}/memberships/{username}"
    # Convert role to lowercase and validate
    role = role.lower()
    if role not in ["member", "admin"]:
        return False, f"Invalid role: {role}. Must be 'member' or 'admin'"
    
    payload = {"role": role}
    response = requests.put(url, headers=HEADERS, json=payload)

    if response.status_code in (200, 201):
        return True, f"Invitation sent to user as {role}"
    elif response.status_code == 404:
        return False, "User not found"
    elif response.status_code == 422:
        return False, "Invalid username or user cannot be added"
    elif response.status_code == 403:
        return False, "Token doesn't have sufficient permissions. Ensure token has 'admin:org' permission"
    else:
        return False, f"Error {response.status_code}: {response.text}"


# Check if token has sufficient permissions
def check_token_permissions():
    url = f"{API_URL}/user"
    response = requests.get(url, headers=HEADERS)
    if response.status_code != 200:
        print("[!] Failed to authenticate with GitHub. Please check your token.")
        return False
    
    # Check organization access
    url = f"{API_URL}/user/memberships/orgs/{GH_ORG}"
    response = requests.get(url, headers=HEADERS)
    if response.status_code != 200:
        print(f"[!] Token does not have access to organization {GH_ORG}")
        print("[!] Make sure the token has 'admin:org' permission and you have admin access to the organization")
        return False
    return True


def main():
    """Main execution function"""
    print(f"[*] Checking token permissions...")
    if not check_token_permissions():
        return

    print(f"[*] Getting existing org members...")
    existing_members = get_existing_org_members()
    
    results = []
    success_count = 0
    failure_count = 0

    try:
        with open(CSV_INPUT, 'r') as infile, open(CSV_OUTPUT, 'w', newline='') as outfile:
            reader = csv.DictReader(infile)
            writer = csv.writer(outfile)
            writer.writerow(['username', 'role', 'status', 'message'])

            for row in reader:
                username = row['username']
                role = row.get('role', 'member')  # Default to member if role not specified
                
                print(f"[*] Processing user: {username}")
                
                if username in existing_members:
                    message = f"Already a member of {GH_ORG}"
                    writer.writerow([username, role, 'skipped', message])
                    print(f"[-] {message}")
                    continue

                success, message = add_user_to_org(username, role)
                status = 'success' if success else 'failed'
                writer.writerow([username, role, status, message])
                
                if success:
                    success_count += 1
                    print(f"[+] {message}")
                else:
                    failure_count += 1
                    print(f"[!] {message}")

                # Add a small delay between requests to be nice to the API
                time.sleep(1)

    except FileNotFoundError:
        print(f"[!] Input file {CSV_INPUT} not found")
        return
    except Exception as e:
        print(f"[!] An error occurred: {str(e)}")
        return

    print(f"\n[*] Summary:")
    print(f"    Successfully added: {success_count}")
    print(f"    Failed: {failure_count}")
    print(f"[*] Results have been written to {CSV_OUTPUT}")


if __name__ == "__main__":
    main()
