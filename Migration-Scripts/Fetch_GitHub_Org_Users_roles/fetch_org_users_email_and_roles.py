import os
import requests
import csv
import time
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Read PAT and org names from .env file
GITHUB_PAT = os.getenv("GH_PAT")
ORG_NAMES = os.getenv("GH_ORG").split(',')

# GraphQL API endpoint
GRAPHQL_URL = "https://api.github.com/graphql"

# Setup error log folder and logging
LOG_DIR = "error_logs"
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "error.log"),
    level=logging.ERROR,
    format="%(asctime)s %(levelname)s: %(message)s"
)

# Headers for the request
headers = {
    "Authorization": f"Bearer {GITHUB_PAT}",
    "Content-Type": "application/json",
}

# Query to fetch organization members with full name
def fetch_org_members(org_name, cursor=None):
    query = """
    query($org: String!, $cursor: String) {
      organization(login: $org) {
        membersWithRole(first: 100, after: $cursor) {
          edges {
            node {
              login
              name
              email
            }
            role
          }
          pageInfo {
            endCursor
            hasNextPage
          }
        }
      }
    }
    """

    variables = {
        "org": org_name,
        "cursor": cursor
    }

    response = requests.post(GRAPHQL_URL, json={"query": query, "variables": variables}, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        error_msg = f"Error fetching data for {org_name}: {response.status_code} - {response.text}"
        print(error_msg)
        logging.error(error_msg)
        return None

# Function to fetch user details for multiple organizations
def fetch_user_details():
    all_user_details = []
    for org_name in ORG_NAMES:
        cursor = None
        while True:
            data = fetch_org_members(org_name, cursor)
            if data:
                members = data["data"]["organization"]["membersWithRole"]["edges"]
                for member in members:
                    user_info = member["node"]
                    email = user_info.get("email", "N/A")
                    full_name = user_info.get("name", "N/A")
                    user_details = {
                        "organization_name": org_name,
                        "full_name": full_name,
                        "user_name": user_info["login"],
                        "user_github_handle": user_info["login"],
                        "email": email if email != "" else "N/A",
                        "role": member["role"]
                    }
                    all_user_details.append(user_details)

                page_info = data["data"]["organization"]["membersWithRole"]["pageInfo"]
                if page_info["hasNextPage"]:
                    cursor = page_info["endCursor"]
                else:
                    break
            else:
                break
    return all_user_details

# Save the details to a CSV file
def save_to_csv(user_details):
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    filename = f"user_details_{timestamp}.csv"

    headers = ["organization_name", "full_name", "user_name", "user_github_handle", "email", "role"]

    with open(filename, mode="w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(user_details)

    print(f"Details saved to {filename}")

# Print the results to the console
def print_to_console(user_details):
    for user in user_details:
        print(f"Org: {user['organization_name']}, Full Name: {user['full_name']}, "
              f"Username: {user['user_name']}, Handle: {user['user_github_handle']}, "
              f"Email: {user['email']}, Role: {user['role']}")

# Main function
if __name__ == "__main__":
    user_details = fetch_user_details()
    if user_details:
        save_to_csv(user_details)
        print_to_console(user_details)
    else:
        print("No user details fetched.")