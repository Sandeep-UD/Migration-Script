import os
import csv
import time
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
GITHUB_TOKEN = os.getenv('GH_PAT')
GITHUB_ORG = os.getenv('GH_ORG')
BASE_URL = 'https://api.github.com'

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('github_fetch.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class GitHubOrgFetcher:
    def __init__(self, token: str, org: str):
        self.token = token
        self.org = org
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'GitHub-Org-Fetcher/1.0'
        })
        self.rate_limit_remaining = 5000
        self.rate_limit_reset = 0
        
    def check_rate_limit(self, response: requests.Response) -> None:
        self.rate_limit_remaining = int(response.headers.get('X-RateLimit-Remaining', 0))
        self.rate_limit_reset = int(response.headers.get('X-RateLimit-Reset', 0))
        
        if self.rate_limit_remaining < 100:
            reset_time = datetime.fromtimestamp(self.rate_limit_reset)
            wait_time = (reset_time - datetime.now()).total_seconds() + 10
            if wait_time > 0:
                logger.warning(f"Rate limit low ({self.rate_limit_remaining}). Waiting {wait_time:.0f} seconds...")
                time.sleep(wait_time)
    
    def make_request(self, url: str, params: Optional[Dict] = None) -> requests.Response:
        try:
            response = self.session.get(url, params=params, timeout=30)
            self.check_rate_limit(response)
            
            if response.status_code == 403 and 'rate limit' in response.text.lower():
                logger.warning("Rate limit exceeded. Waiting...")
                time.sleep(60)
                response = self.session.get(url, params=params, timeout=30)
            
            response.raise_for_status()
            return response
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {url}: {e}")
            raise
    
    def fetch_paginated_data(self, endpoint: str, params: Optional[Dict] = None) -> List[Dict[Any, Any]]:
        all_data = []
        page = 1
        per_page = 100
        
        if params is None:
            params = {}
        
        while True:
            params.update({'page': page, 'per_page': per_page})
            url = f"{BASE_URL}/{endpoint}"
            
            logger.info(f"Fetching page {page} from {endpoint}")
            response = self.make_request(url, params)
            data = response.json()
            
            if not data or (isinstance(data, dict) and not data.get('total_count', 1)):
                break
                
            if isinstance(data, dict) and 'runners' in data:
                items = data['runners']
                all_data.extend(items)
                if len(items) < per_page:
                    break
            elif isinstance(data, dict) and 'secrets' in data:
                items = data['secrets']
                all_data.extend(items)
                if len(items) < per_page:
                    break
            elif isinstance(data, dict) and 'variables' in data:
                items = data['variables']
                all_data.extend(items)
                if len(items) < per_page:
                    break
            elif isinstance(data, list):
                all_data.extend(data)
                if len(data) < per_page:
                    break
            else:
                break
                
            page += 1
            time.sleep(0.1)
            
        logger.info(f"Fetched {len(all_data)} items from {endpoint}")
        return all_data
    
    def fetch_runners(self) -> List[Dict[Any, Any]]:
        logger.info("Fetching organization runners...")
        try:
            return self.fetch_paginated_data(f"orgs/{self.org}/actions/runners")
        except Exception as e:
            logger.error(f"Error fetching runners: {e}")
            return []
    
    def fetch_secrets(self) -> List[Dict[Any, Any]]:
        logger.info("Fetching organization secrets...")
        try:
            return self.fetch_paginated_data(f"orgs/{self.org}/actions/secrets")
        except Exception as e:
            logger.error(f"Error fetching secrets: {e}")
            return []
    
    def fetch_variables(self) -> List[Dict[Any, Any]]:
        logger.info("Fetching organization variables...")
        try:
            return self.fetch_paginated_data(f"orgs/{self.org}/actions/variables")
        except Exception as e:
            logger.error(f"Error fetching variables: {e}")
            return []
    
    def fetch_all_data(self) -> Dict[str, List[Dict[Any, Any]]]:
        logger.info(f"Starting data fetch for organization: {self.org}")
        data = {
            'runners': self.fetch_runners(),
            'secrets': self.fetch_secrets(),
            'variables': self.fetch_variables()
        }
        logger.info("Data fetch completed")
        return data

def write_to_csv(data: List[Dict[Any, Any]], filename: str, fieldnames: List[str]) -> None:
    if not data:
        logger.warning(f"No data to write to {filename}")
        return
        
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for item in data:
            filtered_item = {k: item.get(k, '') for k in fieldnames}
            writer.writerow(filtered_item)
    
    logger.info(f"Written {len(data)} rows to {filename}")

def export_data_to_csv(data: Dict[str, List[Dict[Any, Any]]]) -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if data['runners']:
        runner_fields = ['id', 'name', 'os', 'status', 'busy', 'labels']
        filename = f"github_runners_{timestamp}.csv"
        processed_runners = []
        for runner in data['runners']:
            runner_copy = runner.copy()
            if 'labels' in runner_copy and isinstance(runner_copy['labels'], list):
                runner_copy['labels'] = ', '.join([label.get('name', '') for label in runner_copy['labels']])
            processed_runners.append(runner_copy)
        write_to_csv(processed_runners, filename, runner_fields)
    
    if data['secrets']:
        secret_fields = ['name', 'value', 'visibility']
        filename = f"github_secrets_{timestamp}.csv"
        processed_secrets = []
        for secret in data['secrets']:
            secret_copy = secret.copy()
            secret_copy['value'] = ''
            processed_secrets.append(secret_copy)
        write_to_csv(processed_secrets, filename, secret_fields)
    
    if data['variables']:
        variable_fields = ['name', 'value', 'visibility']
        filename = f"github_variables_{timestamp}.csv"
        write_to_csv(data['variables'], filename, variable_fields)

def create_env_template() -> None:
    if not os.path.exists('.env'):
        with open('.env', 'w') as f:
            f.write("# GitHub API Configuration\n")
            f.write("GITHUB_TOKEN=your_github_personal_access_token\n")
            f.write("GITHUB_ORG=your_organization_name\n")
        logger.info("Created .env template file. Please update with your credentials.")

def main():
    create_env_template()
    
    if not GITHUB_TOKEN or not GITHUB_ORG:
        logger.error("Please set GITHUB_TOKEN and GITHUB_ORG in your .env file")
        return
    
    if GITHUB_TOKEN == 'your_github_personal_access_token':
        logger.error("Please update GITHUB_TOKEN in your .env file with your actual token")
        return
    
    try:
        fetcher = GitHubOrgFetcher(GITHUB_TOKEN, GITHUB_ORG)
        data = fetcher.fetch_all_data()
        export_data_to_csv(data)
        
        print(f"\nData fetch completed for organization: {GITHUB_ORG}")
        print(f"Runners found: {len(data['runners'])}")
        print(f"Secrets found: {len(data['secrets'])}")
        print(f"Variables found: {len(data['variables'])}")
        print(f"\nCSV files generated with timestamp: {datetime.now().strftime('%Y%m%d_%H%M%S')}")
        
    except Exception as e:
        logger.error(f"Script execution failed: {e}")
        raise

if __name__ == "__main__":
    main()
