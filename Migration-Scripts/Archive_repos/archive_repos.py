import csv
import requests
import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# GitHub API token and organization name
GH_TOKEN = os.getenv("GH_TOKEN")
GH_ORG = os.getenv("GH_ORG")
GITHUB_API_URL = "https://api.github.com"

# Setup logging
logging.basicConfig(
    filename="archive_repos.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

def archive_repo(org_name, repo_name):
    """
    Archives a GitHub repository under the specified organization.

    :param org_name: Name of the organization
    :param repo_name: Name of the repository to be archived
    """
    url = f"{GITHUB_API_URL}/repos/{org_name}/{repo_name}"
    headers = {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    data = {"archived": True}

    response = requests.patch(url, headers=headers, json=data)

    if response.status_code == 200:
        message = f"Repository '{repo_name}' has been archived successfully."
        print(message)
        logging.info(message)
    else:
        error_message = (
            f"Failed to archive repository '{repo_name}'. "
            f"Status Code: {response.status_code}, Response: {response.json()}"
        )
        print(error_message)
        logging.error(error_message)

def process_csv(file_path):
    """
    Reads repository names from a CSV file and archives them.

    :param file_path: Path to the CSV file
    """
    try:
        with open(file_path, mode='r') as file:
            csv_reader = csv.DictReader(file)
            for row in csv_reader:
                repo_name = row['repo_name']
                print(f"Archiving repository: {repo_name}")
                logging.info(f"Processing repository: {repo_name}")
                archive_repo(GH_ORG, repo_name)
    except FileNotFoundError:
        error_message = f"CSV file '{file_path}' not found."
        print(error_message)
        logging.error(error_message)
    except KeyError:
        error_message = "CSV file must contain a 'repo_name' column."
        print(error_message)
        logging.error(error_message)

if __name__ == "__main__":
    # Path to the CSV file
    csv_file_path = "repositories.csv"
    
    if not GH_TOKEN or not GH_ORG:
        error_message = "Ensure GH_TOKEN and GH_ORG are set in the .env file."
        print(error_message)
        logging.error(error_message)
    else:
        process_csv(csv_file_path)