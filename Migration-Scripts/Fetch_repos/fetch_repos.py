import os
from dotenv import load_dotenv
import requests
import csv
import time
import logging

# Create logs directory if it doesn't exist
os.makedirs("logs", exist_ok=True)

# Configure logging
logging.basicConfig(
    filename="logs/fetch_repos.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# Load environment variables from .env file
load_dotenv()

def get_github_repos(org, token, per_page=100):
    url = f"https://api.github.com/orgs/{org}/repos"
    headers = {"Authorization": f"token {token}"}
    params = {"per_page": per_page, "page": 1}
    repos = []
    
    while True:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 403 and "X-RateLimit-Remaining" in response.headers:
            reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
            wait_seconds = max(reset_time - int(time.time()), 1)
            msg = f"Rate limit exceeded. Waiting for {wait_seconds} seconds..."
            print(msg)
            logging.warning(msg)
            time.sleep(wait_seconds)
            continue
        elif response.status_code != 200:
            error_msg = f"Error: {response.status_code} - {response.json().get('message', 'Unknown error')}"
            print(error_msg)
            logging.error(error_msg)
            break
        
        data = response.json()
        if not data:
            break
        
        repos.extend(data)
        params["page"] += 1
    
    return repos

def save_to_csv(repositories, filename="github_repos.csv"):
    with open(filename, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Repository Name", "Visibility"])
        for repo in repositories:
            writer.writerow([
                repo["name"],
                repo.get("visibility", "N/A")
            ])

if __name__ == "__main__":
    ORG_NAME = os.getenv("GH_ORG")
    TOKEN = os.getenv("GH_PAT")
    
    try:
        repositories = get_github_repos(ORG_NAME, TOKEN)
        save_to_csv(repositories)
        print("CSV file saved successfully!")
        logging.info("CSV file saved successfully!")
    except Exception as e:
        logging.exception(f"Unhandled exception: {e}")
        print(f"An error occurred. Check logs/fetch_repos.log for details.")