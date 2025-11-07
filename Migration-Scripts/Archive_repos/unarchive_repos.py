import csv
import requests
import os
import logging
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# GitHub API token and organization name
GH_TOKEN = os.getenv("GH_TOKEN")
GH_ORG = os.getenv("GH_ORG")
GITHUB_API_URL = "https://api.github.com"

# Setup logging
logging.basicConfig(
    filename="unarchive_repos.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

def check_rate_limit():
    """
    Check GitHub API rate limit status and wait if necessary.
    Returns True if requests can proceed, False if there was an error.
    """
    headers = {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    
    try:
        response = requests.get(f"{GITHUB_API_URL}/rate_limit", headers=headers)
        if response.status_code == 200:
            data = response.json()
            remaining = data['rate']['remaining']
            reset_time = data['rate']['reset']
            
            if remaining < 1:
                wait_time = reset_time - int(time.time()) + 1
                if wait_time > 0:
                    message = f"Rate limit exceeded. Waiting for {wait_time} seconds..."
                    print(message)
                    logging.info(message)
                    time.sleep(wait_time)
            return True
    except Exception as e:
        error_message = f"Error checking rate limit: {str(e)}"
        print(error_message)
        logging.error(error_message)
        return False

def unarchive_repo(org_name, repo_name):
    """
    Unarchives a GitHub repository under the specified organization.

    :param org_name: Name of the organization
    :param repo_name: Name of the repository to be unarchived
    """
    if not check_rate_limit():
        return

    url = f"{GITHUB_API_URL}/repos/{org_name}/{repo_name}"
    headers = {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    data = {"archived": False}

    try:
        response = requests.patch(url, headers=headers, json=data)

        if response.status_code == 200:
            message = f"Repository '{repo_name}' has been unarchived successfully."
            print(message)
            logging.info(message)
        else:
            error_message = (
                f"Failed to unarchive repository '{repo_name}'. "
                f"Status Code: {response.status_code}, Response: {response.json()}"
            )
            print(error_message)
            logging.error(error_message)
    except requests.exceptions.RequestException as e:
        error_message = f"Network error while unarchiving '{repo_name}': {str(e)}"
        print(error_message)
        logging.error(error_message)

def process_csv(file_path):
    """
    Reads repository names from a CSV file and unarchives them.

    :param file_path: Path to the CSV file
    """
    try:
        with open(file_path, mode='r') as file:
            csv_reader = csv.DictReader(file)
            for row in csv_reader:
                repo_name = row['repo_name']
                print(f"Unarchiving repository: {repo_name}")
                logging.info(f"Processing repository: {repo_name}")
                unarchive_repo(GH_ORG, repo_name)
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
