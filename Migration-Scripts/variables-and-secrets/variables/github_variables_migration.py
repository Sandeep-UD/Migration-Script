#!/usr/bin/env python3
import os
import csv
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

class GitHubVariablesMigrator:
    """GitHub Actions Variables Migration Tool"""
    
    def __init__(self):
        """Initialize the migrator with configuration from .env file"""
        load_dotenv()
        
        # Load configuration from environment
        self.source_token = os.getenv('SOURCE_GITHUB_TOKEN')
        self.target_token = os.getenv('TARGET_GITHUB_TOKEN')
        self.source_org = os.getenv('SOURCE_ORGANIZATION')
        self.target_org = os.getenv('TARGET_ORGANIZATION')
        
        # Validate required environment variables
        self._validate_config()
        
        # Setup logging
        self._setup_logging()
        
        # Setup HTTP sessions with retry strategy
        self.source_session = self._create_session(self.source_token)
        self.target_session = self._create_session(self.target_token)
        
        # GitHub API base URL
        self.base_url = "https://api.github.com"
        
        # Rate limiting
        self.rate_limit_remaining = 5000
        self.rate_limit_reset = None
        
        # Repository mapping cache for faster lookups
        self.target_repo_mapping = {}
        
        self.logger.info("GitHubVariablesMigrator initialized successfully")
        self.logger.info(f"Source Organization: {self.source_org}")
        self.logger.info(f"Target Organization: {self.target_org}")

    def _validate_config(self) -> None:
        """Validate that all required environment variables are set"""
        required_vars = {
            'SOURCE_GITHUB_TOKEN': self.source_token,
            'TARGET_GITHUB_TOKEN': self.target_token,
            'SOURCE_ORGANIZATION': self.source_org,
            'TARGET_ORGANIZATION': self.target_org
        }
        missing_vars = [var for var, value in required_vars.items() if not value]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

    def _setup_logging(self) -> None:
        """Setup logging configuration"""
        log_filename = f"github_variable_migration.log"
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_filename),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def _create_session(self, token: str) -> requests.Session:
        """Create a requests session with retry strategy and authentication"""
        session = requests.Session()
        
        # Setup retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Setup headers
        session.headers.update({
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'GitHub-Variables-Migrator/1.0'
        })
        return session

    def _handle_rate_limit(self, response: requests.Response) -> None:
        """Handle GitHub API rate limiting"""
        self.rate_limit_remaining = int(response.headers.get('X-RateLimit-Remaining', 0))
        self.rate_limit_reset = int(response.headers.get('X-RateLimit-Reset', 0))
        
        if response.status_code == 429 or self.rate_limit_remaining < 10:
            reset_time = datetime.fromtimestamp(self.rate_limit_reset)
            wait_time = (reset_time - datetime.now()).total_seconds() + 10
            if wait_time > 0:
                self.logger.warning(f"Rate limit reached. Waiting {wait_time:.0f} seconds until {reset_time}")
                time.sleep(wait_time)

    def _make_request(self, session: requests.Session, method: str, url: str, **kwargs) -> requests.Response:
        """Make an API request with rate limit handling"""
        try:
            response = session.request(method, url, **kwargs)
            self._handle_rate_limit(response)
            return response
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request failed for {url}: {e}")
            raise

    def _get_paginated_data(self, session: requests.Session, url: str) -> List[Dict]:
        """Fetch all pages of data from a paginated API endpoint"""
        all_data = []
        page = 1
        per_page = 100
        
        while True:
            params = {'page': page, 'per_page': per_page}
            response = self._make_request(session, 'GET', url, params=params)
            
            if response.status_code != 200:
                break
            data = response.json()
            if not data:
                break
            
            # Handle both list and dict responses
            if isinstance(data, list):
                all_data.extend(data)
                if len(data) < per_page:
                    break
            elif isinstance(data, dict):
                # For responses like {'repositories': [...]}
                items = data.get('repositories', data.get('variables', []))
                all_data.extend(items)
                if len(items) < per_page:
                    break
            else:
                break
            
            page += 1
            self.logger.debug(f"Fetched page {page-1}, total items so far: {len(all_data)}")
        return all_data

    def get_organization_variables(self, org: str, session: requests.Session) -> List[Dict]:
        """Fetch all organization-level variables with their visibility settings"""
        self.logger.info(f"Fetching organization variables for: {org}")
        
        url = f"{self.base_url}/orgs/{org}/actions/variables"
        response = self._make_request(session, 'GET', url)
        
        if response.status_code != 200:
            self.logger.error(f"Failed to fetch org variables: {response.status_code}")
            if response.status_code == 404:
                self.logger.error("Organization not found or no access to variables")
            return []
        
        try:
            data = response.json()
            self.logger.debug(f"API response type: {type(data)}")
            
            # Handle the GitHub API response format
            if isinstance(data, dict):
                variables = data.get('variables', [])
            elif isinstance(data, list):
                variables = data
            else:
                self.logger.error(f"Unexpected response format: {type(data)}")
                return []
        except Exception as e:
            self.logger.error(f"Failed to parse JSON response: {e}")
            return []
        
        if not variables:
            self.logger.info("No organization variables found")
            return []
        
        # Enhance each variable with detailed visibility information
        enhanced_variables = []
        for i, var in enumerate(variables):
            try:
                if not isinstance(var, dict):
                    self.logger.error(f"Variable {i} is not a dict: {type(var)} - {var}")
                    continue
                var_name = var.get('name')
                if not var_name:
                    self.logger.error(f"Variable {i} has no name: {var}")
                    continue
                
                # Try to get detailed info, but use basic info as fallback
                enhanced_var = self.get_organization_variable_details(org, var_name, session)
                if enhanced_var and isinstance(enhanced_var, dict):
                    enhanced_variables.append(enhanced_var)
                else:
                    # Fallback to basic variable info if detailed fetch fails
                    self.logger.warning(f"Using basic info for variable: {var_name}")
                    # Ensure we have basic visibility info
                    if 'visibility' not in var:
                        var['visibility'] = 'all'  # Default
                    enhanced_variables.append(var)
            except Exception as e:
                self.logger.error(f"Error processing variable {i}: {e}")
                continue
        
        self.logger.info(f"Found {len(enhanced_variables)} organization variables")
        return enhanced_variables

    def get_organization_variable_details(self, org: str, var_name: str, session: requests.Session) -> Optional[Dict]:
        """Fetch detailed information for a specific organization variable including visibility"""
        url = f"{self.base_url}/orgs/{org}/actions/variables/{var_name}"
        response = self._make_request(session, 'GET', url)
        
        if response.status_code != 200:
            self.logger.warning(f"Failed to fetch detailed info for variable {var_name}: {response.status_code}")
            return None
        
        try:
            var_details = response.json()
            if not isinstance(var_details, dict):
                self.logger.error(f"Variable details for {var_name} is not a dict: {type(var_details)}")
                return None
            
            # If visibility is 'selected', get the list of selected repositories
            if var_details.get('visibility') == 'selected':
                selected_repos = self.get_variable_selected_repositories(org, var_name, session)
                var_details['selected_repository_ids'] = [repo['id'] for repo in selected_repos if isinstance(repo, dict) and 'id' in repo]
                var_details['selected_repository_names'] = [repo['name'] for repo in selected_repos if isinstance(repo, dict) and 'name' in repo]
                self.logger.info(f"Variable {var_name} has selected visibility for {len(selected_repos)} repositories")
            return var_details
        except Exception as e:
            self.logger.error(f"Error parsing variable details for {var_name}: {e}")
            return None

    def get_variable_selected_repositories(self, org: str, var_name: str, session: requests.Session) -> List[Dict]:
        """Get the list of repositories that have access to a selected-visibility variable"""
        url = f"{self.base_url}/orgs/{org}/actions/variables/{var_name}/repositories"
        repos = self._get_paginated_data(session, url)
        return repos

    def build_target_repo_mapping(self) -> None:
        """Build a mapping of repository names to IDs in the target organization"""
        if self.target_repo_mapping:
            return  # Already built
        
        self.logger.info("Building target organization repository mapping...")
        target_repos = self.get_organization_repositories(self.target_org, self.target_session)
        
        for repo in target_repos:
            if isinstance(repo, dict) and 'name' in repo and 'id' in repo:
                self.target_repo_mapping[repo['name']] = repo['id']
        self.logger.info(f"Built mapping for {len(self.target_repo_mapping)} target repositories")

    def get_target_repository_ids(self, repo_names: List[str]) -> List[int]:
        """Get target organization repository IDs for given repository names"""
        self.build_target_repo_mapping()
        
        target_ids = []
        missing_repos = []
        
        for repo_name in repo_names:
            if repo_name in self.target_repo_mapping:
                target_ids.append(self.target_repo_mapping[repo_name])
            else:
                missing_repos.append(repo_name)
        
        if missing_repos:
            self.logger.warning(f"Repositories not found in target org: {', '.join(missing_repos)}")
        return target_ids

    def get_repository_variables(self, org: str, repo: str, session: requests.Session) -> List[Dict]:
        """Fetch all repository-level variables"""
        self.logger.debug(f"Fetching repository variables for: {org}/{repo}")
        
        url = f"{self.base_url}/repos/{org}/{repo}/actions/variables"
        response = self._make_request(session, 'GET', url)
        
        if response.status_code != 200:
            if response.status_code == 404:
                self.logger.debug(f"Repository {org}/{repo} not found or no variables endpoint access")
            else:
                self.logger.warning(f"Failed to fetch repo variables for {org}/{repo}: {response.status_code}")
            return []
        
        try:
            data = response.json()
            if isinstance(data, dict):
                variables = data.get('variables', [])
            elif isinstance(data, list):
                variables = data
            else:
                self.logger.error(f"Unexpected repo variables response format: {type(data)}")
                return []
        except Exception as e:
            self.logger.error(f"Error parsing repo variables for {org}/{repo}: {e}")
            return []
        
        if variables:
            self.logger.info(f"Found {len(variables)} repository variables for {org}/{repo}")
        return variables

    def get_organization_repositories(self, org: str, session: requests.Session) -> List[Dict]:
        """Fetch all repositories in an organization"""
        self.logger.info(f"Fetching repositories for organization: {org}")
        url = f"{self.base_url}/orgs/{org}/repos"
        repos = self._get_paginated_data(session, url)
        self.logger.info(f"Found {len(repos)} repositories in {org}")
        return repos

    def export_variables_to_csv(self, variables_data: List[Dict], filename: str) -> None:
        """Export variables data to CSV file"""
        self.logger.info(f"Exporting variables to CSV: {filename}")
        
        if not variables_data:
            self.logger.warning("No variables data to export")
            return
        
        fieldnames = ['scope', 'repository', 'name', 'value', 'visibility', 'selected_repositories', 'created_at', 'updated_at']
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(variables_data)
        self.logger.info(f"Exported {len(variables_data)} variables to {filename}")

    def create_organization_variable(self, org: str, name: str, value: str, visibility: str, 
                                   selected_repo_names: List[str], session: requests.Session) -> bool:
        """Create an organization-level variable with proper visibility settings"""
        url = f"{self.base_url}/orgs/{org}/actions/variables"
        
        data = {
            'name': name,
            'value': value,
            'visibility': visibility
        }
        
        # If visibility is 'selected', we need to set repository IDs
        if visibility == 'selected' and selected_repo_names:
            target_repo_ids = self.get_target_repository_ids(selected_repo_names)
            if target_repo_ids:
                data['selected_repository_ids'] = target_repo_ids
            else:
                self.logger.warning(f"No valid repositories found for variable {name}, setting visibility to 'private'")
                data['visibility'] = 'private'
        
        response = self._make_request(session, 'POST', url, json=data)
        
        if response.status_code == 201:
            visibility_info = f" (visibility: {visibility}"
            if visibility == 'selected':
                visibility_info += f", repositories: {len(selected_repo_names)})"
            else:
                visibility_info += ")"
            self.logger.info(f"Created organization variable: {name}{visibility_info}")
            return True
        elif response.status_code == 409:
            self.logger.info(f"Organization variable already exists, updating: {name}")
            return self.update_organization_variable(org, name, value, visibility, selected_repo_names, session)
        else:
            try:
                error_detail = response.json().get('message', 'Unknown error')
            except:
                error_detail = response.text
            self.logger.error(f"Failed to create organization variable {name}: {response.status_code} - {error_detail}")
            return False

    def update_organization_variable(self, org: str, name: str, value: str, visibility: str,
                                   selected_repo_names: List[str], session: requests.Session) -> bool:
        """Update an organization-level variable with proper visibility settings"""
        url = f"{self.base_url}/orgs/{org}/actions/variables/{name}"
        
        data = {
            'name': name,
            'value': value,
            'visibility': visibility
        }
        
        # If visibility is 'selected', we need to set repository IDs
        if visibility == 'selected' and selected_repo_names:
            target_repo_ids = self.get_target_repository_ids(selected_repo_names)
            if target_repo_ids:
                data['selected_repository_ids'] = target_repo_ids
            else:
                self.logger.warning(f"No valid repositories found for variable {name}, setting visibility to 'private'")
                data['visibility'] = 'private'
        
        response = self._make_request(session, 'PATCH', url, json=data)
        
        if response.status_code == 204:
            visibility_info = f" (visibility: {visibility}"
            if visibility == 'selected':
                visibility_info += f", repositories: {len(selected_repo_names)})"
            else:
                visibility_info += ")"
            self.logger.info(f"Updated organization variable: {name}{visibility_info}")
            return True
        else:
            try:
                error_detail = response.json().get('message', 'Unknown error')
            except:
                error_detail = response.text
            self.logger.error(f"Failed to update organization variable {name}: {response.status_code} - {error_detail}")
            return False

    def create_repository_variable(self, org: str, repo: str, name: str, value: str, session: requests.Session) -> bool:
        """Create a repository-level variable"""
        url = f"{self.base_url}/repos/{org}/{repo}/actions/variables"
        
        data = {
            'name': name,
            'value': value
        }
        
        response = self._make_request(session, 'POST', url, json=data)
        
        if response.status_code == 201:
            self.logger.info(f"Created repository variable: {repo}/{name}")
            return True
        elif response.status_code == 409:
            self.logger.info(f"Repository variable already exists, updating: {repo}/{name}")
            return self.update_repository_variable(org, repo, name, value, session)
        elif response.status_code == 404:
            self.logger.warning(f"Repository {org}/{repo} not found in target organization - skipping variable {name}")
            return False
        else:
            try:
                error_detail = response.json().get('message', 'Unknown error')
            except:
                error_detail = response.text
            self.logger.error(f"Failed to create repository variable {repo}/{name}: {response.status_code} - {error_detail}")
            return False

    def update_repository_variable(self, org: str, repo: str, name: str, value: str, session: requests.Session) -> bool:
        """Update a repository-level variable"""
        url = f"{self.base_url}/repos/{org}/{repo}/actions/variables/{name}"
        
        data = {
            'name': name,
            'value': value
        }
        
        response = self._make_request(session, 'PATCH', url, json=data)
        
        if response.status_code == 204:
            self.logger.info(f"Updated repository variable: {repo}/{name}")
            return True
        else:
            try:
                error_detail = response.json().get('message', 'Unknown error')
            except:
                error_detail = response.text
            self.logger.error(f"Failed to update repository variable {repo}/{name}: {response.status_code} - {error_detail}")
            return False

    def fetch_all_variables(self) -> List[Dict]:
        """Fetch all variables from source organization"""
        all_variables = []
        
        # Fetch organization-level variables
        org_variables = self.get_organization_variables(self.source_org, self.source_session)
        
        for var in org_variables:
            if not isinstance(var, dict):
                self.logger.error(f"Org variable is not a dict: {type(var)} - {var}")
                continue
            
            selected_repos = var.get('selected_repository_names', [])
            all_variables.append({
                'scope': 'organization',
                'repository': '',
                'name': var.get('name', ''),
                'value': var.get('value', ''),
                'visibility': var.get('visibility', 'all'),
                'selected_repositories': ','.join(selected_repos) if selected_repos else '',
                'created_at': var.get('created_at', ''),
                'updated_at': var.get('updated_at', '')
            })
        
        # Fetch repository-level variables
        repos = self.get_organization_repositories(self.source_org, self.source_session)
        
        for repo in repos:
            if not isinstance(repo, dict) or 'name' not in repo:
                continue
            
            repo_name = repo['name']
            repo_variables = self.get_repository_variables(self.source_org, repo_name, self.source_session)
            
            for var in repo_variables:
                if not isinstance(var, dict):
                    self.logger.error(f"Repo variable is not a dict: {type(var)} - {var}")
                    continue
                
                all_variables.append({
                    'scope': 'repository',
                    'repository': repo_name,
                    'name': var.get('name', ''),
                    'value': var.get('value', ''),
                    'visibility': '',  # Repository variables don't have visibility
                    'selected_repositories': '',
                    'created_at': var.get('created_at', ''),
                    'updated_at': var.get('updated_at', '')
                })
        return all_variables

    def migrate_variables(self, variables_data: List[Dict]) -> Tuple[int, int, int]:
        """Migrate variables to target organization"""
        success_count = 0
        error_count = 0
        skipped_count = 0
        
        self.logger.info(f"Starting migration of {len(variables_data)} variables")
        
        for var in variables_data:
            try:
                if not isinstance(var, dict):
                    self.logger.error(f"Variable is not a dict: {type(var)} - {var}")
                    error_count += 1
                    continue
                
                if var.get('scope') == 'organization':
                    selected_repos = var.get('selected_repositories', '').split(',') if var.get('selected_repositories') else []
                    selected_repos = [repo.strip() for repo in selected_repos if repo.strip()]
                    
                    success = self.create_organization_variable(
                        self.target_org, 
                        var.get('name', ''), 
                        var.get('value', ''), 
                        var.get('visibility', 'all'),
                        selected_repos,
                        self.target_session
                    )
                elif var.get('scope') == 'repository':
                    success = self.create_repository_variable(
                        self.target_org, 
                        var.get('repository', ''), 
                        var.get('name', ''), 
                        var.get('value', ''), 
                        self.target_session
                    )
                else:
                    self.logger.error(f"Unknown scope: {var.get('scope')}")
                    success = False
                
                if success:
                    success_count += 1
                elif success is False:  # Explicitly failed
                    error_count += 1
                else:  # Skipped (None)
                    skipped_count += 1
            except Exception as e:
                self.logger.error(f"Error migrating variable {var.get('name', 'UNKNOWN')}: {e}")
                error_count += 1
        
        self.logger.info(f"Migration completed. Success: {success_count}, Errors: {error_count}, Skipped: {skipped_count}")
        return success_count, error_count, skipped_count

    def run_migration(self) -> None:
        """Run the complete migration process"""
        try:
            self.logger.info("Starting GitHub Variables Migration")
            
            # Fetch all variables from source
            variables_data = self.fetch_all_variables()
            
            if not variables_data:
                self.logger.warning("No variables found to migrate")
                return
            
            # Export to CSV
            csv_filename = f"github_variables_export.csv"
            self.export_variables_to_csv(variables_data, csv_filename)
            
            # Migrate variables to target
            success_count, error_count, skipped_count = self.migrate_variables(variables_data)
            
            self.logger.info("Migration process completed successfully")
            self.logger.info(f"Total variables processed: {len(variables_data)}")
            self.logger.info(f"Successfully migrated: {success_count}")
            self.logger.info(f"Errors: {error_count}")
            self.logger.info(f"Skipped: {skipped_count}")
            self.logger.info(f"Variables exported to: {csv_filename}")
        except Exception as e:
            self.logger.error(f"Migration failed: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            raise

def main():
    """Main entry point"""
    try:
        migrator = GitHubVariablesMigrator()
        migrator.run_migration()
    except Exception as e:
        print(f"Error: {e}")
        return 1
    return 0

if __name__ == "__main__":
    exit(main())
