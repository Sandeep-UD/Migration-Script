#!/usr/bin/env python3
import os
import csv
import time
import base64
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv
from nacl import encoding, public

class GitHubSecretsMigrator:
    """GitHub Actions Secrets Migration Tool"""
    
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
        
        # Public key cache for encryption
        self.org_public_key_cache = {}
        self.repo_public_key_cache = {}
        
        self.logger.info("GitHubSecretsMigrator initialized successfully")
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
        log_filename = f"github_secrets_migration.log"
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
            'User-Agent': 'GitHub-Secrets-Migrator/1.0'
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
                # For responses like {'repositories': [...], 'secrets': [...]}
                items = data.get('repositories', data.get('secrets', []))
                all_data.extend(items)
                if len(items) < per_page:
                    break
            else:
                break
            
            page += 1
            self.logger.debug(f"Fetched page {page-1}, total items so far: {len(all_data)}")
        return all_data

    def get_organization_public_key(self, org: str, session: requests.Session) -> Optional[Dict]:
        """Get the organization's public key for secret encryption"""
        if org in self.org_public_key_cache:
            return self.org_public_key_cache[org]
        
        url = f"{self.base_url}/orgs/{org}/actions/secrets/public-key"
        response = self._make_request(session, 'GET', url)
        
        if response.status_code != 200:
            self.logger.error(f"Failed to fetch org public key for {org}: {response.status_code}")
            return None
        
        try:
            public_key = response.json()
            self.org_public_key_cache[org] = public_key
            return public_key
        except Exception as e:
            self.logger.error(f"Error parsing org public key for {org}: {e}")
            return None

    def get_repository_public_key(self, org: str, repo: str, session: requests.Session) -> Optional[Dict]:
        """Get the repository's public key for secret encryption"""
        cache_key = f"{org}/{repo}"
        if cache_key in self.repo_public_key_cache:
            return self.repo_public_key_cache[cache_key]
        
        url = f"{self.base_url}/repos/{org}/{repo}/actions/secrets/public-key"
        response = self._make_request(session, 'GET', url)
        
        if response.status_code != 200:
            self.logger.error(f"Failed to fetch repo public key for {org}/{repo}: {response.status_code}")
            return None
        
        try:
            public_key = response.json()
            self.repo_public_key_cache[cache_key] = public_key
            return public_key
        except Exception as e:
            self.logger.error(f"Error parsing repo public key for {org}/{repo}: {e}")
            return None

    def encrypt_secret(self, secret_value: str, public_key: str) -> str:
        """Encrypt a secret using the public key"""
        try:
            public_key_bytes = base64.b64decode(public_key)
            public_key_obj = public.PublicKey(public_key_bytes)
            box = public.SealedBox(public_key_obj)
            encrypted = box.encrypt(secret_value.encode("utf-8"))
            return base64.b64encode(encrypted).decode("utf-8")
        except Exception as e:
            self.logger.error(f"Error encrypting secret: {e}")
            raise

    def get_organization_secrets(self, org: str, session: requests.Session) -> List[Dict]:
        """Fetch all organization-level secrets with their visibility settings"""
        self.logger.info(f"Fetching organization secrets for: {org}")
        
        url = f"{self.base_url}/orgs/{org}/actions/secrets"
        response = self._make_request(session, 'GET', url)
        
        if response.status_code != 200:
            self.logger.error(f"Failed to fetch org secrets: {response.status_code}")
            if response.status_code == 404:
                self.logger.error("Organization not found or no access to secrets")
            return []
        
        try:
            data = response.json()
            self.logger.debug(f"API response type: {type(data)}")
            
            # Handle the GitHub API response format
            if isinstance(data, dict):
                secrets = data.get('secrets', [])
            elif isinstance(data, list):
                secrets = data
            else:
                self.logger.error(f"Unexpected response format: {type(data)}")
                return []
        except Exception as e:
            self.logger.error(f"Failed to parse JSON response: {e}")
            return []
        
        if not secrets:
            self.logger.info("No organization secrets found")
            return []
        
        # Enhance each secret with detailed visibility information
        enhanced_secrets = []
        for i, secret in enumerate(secrets):
            try:
                if not isinstance(secret, dict):
                    self.logger.error(f"Secret {i} is not a dict: {type(secret)} - {secret}")
                    continue
                secret_name = secret.get('name')
                if not secret_name:
                    self.logger.error(f"Secret {i} has no name: {secret}")
                    continue
                
                # Try to get detailed info, but use basic info as fallback
                enhanced_secret = self.get_organization_secret_details(org, secret_name, session)
                if enhanced_secret and isinstance(enhanced_secret, dict):
                    enhanced_secrets.append(enhanced_secret)
                else:
                    # Fallback to basic secret info if detailed fetch fails
                    self.logger.warning(f"Using basic info for secret: {secret_name}")
                    # Ensure we have basic visibility info
                    if 'visibility' not in secret:
                        secret['visibility'] = 'all'  # Default
                    enhanced_secrets.append(secret)
            except Exception as e:
                self.logger.error(f"Error processing secret {i}: {e}")
                continue
        
        self.logger.info(f"Found {len(enhanced_secrets)} organization secrets")
        return enhanced_secrets

    def get_organization_secret_details(self, org: str, secret_name: str, session: requests.Session) -> Optional[Dict]:
        """Fetch detailed information for a specific organization secret including visibility"""
        url = f"{self.base_url}/orgs/{org}/actions/secrets/{secret_name}"
        response = self._make_request(session, 'GET', url)
        
        if response.status_code != 200:
            self.logger.warning(f"Failed to fetch detailed info for secret {secret_name}: {response.status_code}")
            return None
        
        try:
            secret_details = response.json()
            if not isinstance(secret_details, dict):
                self.logger.error(f"Secret details for {secret_name} is not a dict: {type(secret_details)}")
                return None
            
            # If visibility is 'selected', get the list of selected repositories
            if secret_details.get('visibility') == 'selected':
                selected_repos = self.get_secret_selected_repositories(org, secret_name, session)
                secret_details['selected_repository_ids'] = [repo['id'] for repo in selected_repos if isinstance(repo, dict) and 'id' in repo]
                secret_details['selected_repository_names'] = [repo['name'] for repo in selected_repos if isinstance(repo, dict) and 'name' in repo]
                self.logger.info(f"Secret {secret_name} has selected visibility for {len(selected_repos)} repositories")
            
            # Note: Secret values cannot be retrieved via API for security reasons
            secret_details['value'] = '[ENCRYPTED_SECRET_VALUE]'
            return secret_details
        except Exception as e:
            self.logger.error(f"Error parsing secret details for {secret_name}: {e}")
            return None

    def get_secret_selected_repositories(self, org: str, secret_name: str, session: requests.Session) -> List[Dict]:
        """Get the list of repositories that have access to a selected-visibility secret"""
        url = f"{self.base_url}/orgs/{org}/actions/secrets/{secret_name}/repositories"
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

    def get_repository_secrets(self, org: str, repo: str, session: requests.Session) -> List[Dict]:
        """Fetch all repository-level secrets"""
        self.logger.debug(f"Fetching repository secrets for: {org}/{repo}")
        
        url = f"{self.base_url}/repos/{org}/{repo}/actions/secrets"
        response = self._make_request(session, 'GET', url)
        
        if response.status_code != 200:
            if response.status_code == 404:
                self.logger.debug(f"Repository {org}/{repo} not found or no secrets endpoint access")
            else:
                self.logger.warning(f"Failed to fetch repo secrets for {org}/{repo}: {response.status_code}")
            return []
        
        try:
            data = response.json()
            if isinstance(data, dict):
                secrets = data.get('secrets', [])
            elif isinstance(data, list):
                secrets = data
            else:
                self.logger.error(f"Unexpected repo secrets response format: {type(data)}")
                return []
        except Exception as e:
            self.logger.error(f"Error parsing repo secrets for {org}/{repo}: {e}")
            return []
        
        # Add placeholder values for secrets (values cannot be retrieved)
        for secret in secrets:
            if isinstance(secret, dict):
                secret['value'] = '[ENCRYPTED_SECRET_VALUE]'
        
        if secrets:
            self.logger.info(f"Found {len(secrets)} repository secrets for {org}/{repo}")
        return secrets

    def get_organization_repositories(self, org: str, session: requests.Session) -> List[Dict]:
        """Fetch all repositories in an organization"""
        self.logger.info(f"Fetching repositories for organization: {org}")
        url = f"{self.base_url}/orgs/{org}/repos"
        repos = self._get_paginated_data(session, url)
        self.logger.info(f"Found {len(repos)} repositories in {org}")
        return repos

    def check_organization_secret_exists(self, org: str, secret_name: str, session: requests.Session) -> bool:
        """Check if an organization secret already exists"""
        self.logger.info(f"Checking if organization secret '{secret_name}' exists in {org}")
        url = f"{self.base_url}/orgs/{org}/actions/secrets/{secret_name}"
        response = self._make_request(session, 'GET', url)
        
        if response.status_code == 200:
            self.logger.info(f"Organization secret '{secret_name}' already exists in {org} - will skip")
            return True
        elif response.status_code == 404:
            self.logger.info(f"Organization secret '{secret_name}' does not exist in {org} - will create")
            return False
        else:
            self.logger.warning(f"Unexpected response when checking org secret {secret_name}: {response.status_code}")
            return False

    def check_repository_secret_exists(self, org: str, repo: str, secret_name: str, session: requests.Session) -> bool:
        """Check if a repository secret already exists"""
        self.logger.info(f"Checking if repository secret '{secret_name}' exists in {org}/{repo}")
        url = f"{self.base_url}/repos/{org}/{repo}/actions/secrets/{secret_name}"
        response = self._make_request(session, 'GET', url)
        
        if response.status_code == 200:
            self.logger.info(f"Repository secret '{secret_name}' already exists in {org}/{repo} - will skip")
            return True
        elif response.status_code == 404:
            self.logger.info(f"Repository secret '{secret_name}' does not exist in {org}/{repo} - will create")
            return False
        else:
            self.logger.warning(f"Unexpected response when checking repo secret {repo}/{secret_name}: {response.status_code}")
            return False

    def export_secrets_to_csv(self, secrets_data: List[Dict], filename: str) -> None:
        """Export secrets data to CSV file"""
        self.logger.info(f"Exporting secrets to CSV: {filename}")
        
        if not secrets_data:
            self.logger.warning("No secrets data to export")
            return
        
        fieldnames = ['scope', 'repository', 'name', 'value', 'visibility', 'selected_repositories', 'created_at', 'updated_at']
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(secrets_data)
        self.logger.info(f"Exported {len(secrets_data)} secrets to {filename}")

    def create_organization_secret(self, org: str, name: str, value: str, visibility: str, 
                                  selected_repo_names: List[str], session: requests.Session, 
                                  create_placeholder: bool = True) -> bool:
        """Create an organization-level secret with proper visibility settings"""
        # Check if secret already exists
        if self.check_organization_secret_exists(org, name, session):
            self.logger.info(f"Organization secret '{name}' already exists - skipping")
            return None  # Return None to indicate skipped
        
        # If no actual value provided and create_placeholder is True, use a placeholder value
        if value == '[ENCRYPTED_SECRET_VALUE]' or not value.strip():
            if create_placeholder:
                self.logger.info(f"Creating secret {name} with placeholder value (to be set manually later)")
                value = "PLACEHOLDER_VALUE_SET_MANUALLY"
            else:
                self.logger.warning(f"Cannot create secret {name} - no actual value provided")
                return False
        
        # Get public key for encryption
        public_key_info = self.get_organization_public_key(org, session)
        if not public_key_info:
            self.logger.error(f"Failed to get public key for organization {org}")
            return False
        
        try:
            encrypted_value = self.encrypt_secret(value, public_key_info['key'])
        except Exception as e:
            self.logger.error(f"Failed to encrypt secret {name}: {e}")
            return False
        
        url = f"{self.base_url}/orgs/{org}/actions/secrets/{name}"
        
        data = {
            'encrypted_value': encrypted_value,
            'key_id': public_key_info['key_id'],
            'visibility': visibility
        }
        
        # If visibility is 'selected', we need to set repository IDs
        if visibility == 'selected' and selected_repo_names:
            target_repo_ids = self.get_target_repository_ids(selected_repo_names)
            if target_repo_ids:
                data['selected_repository_ids'] = target_repo_ids
            else:
                self.logger.warning(f"No valid repositories found for secret {name}, setting visibility to 'private'")
                data['visibility'] = 'private'
        
        response = self._make_request(session, 'PUT', url, json=data)
        
        if response.status_code in [201, 204]:
            visibility_info = f" (visibility: {visibility}"
            if visibility == 'selected':
                visibility_info += f", repositories: {len(selected_repo_names)})"
            else:
                visibility_info += ")"
            action = "Created/Updated"
            if value == "PLACEHOLDER_VALUE_SET_MANUALLY":
                action += " [PLACEHOLDER]"
            self.logger.info(f"{action} organization secret: {name}{visibility_info}")
            return True
        else:
            try:
                error_detail = response.json().get('message', 'Unknown error')
            except:
                error_detail = response.text
            self.logger.error(f"Failed to create organization secret {name}: {response.status_code} - {error_detail}")
            return False

    def create_repository_secret(self, org: str, repo: str, name: str, value: str, session: requests.Session, 
                                create_placeholder: bool = True) -> bool:
        """Create a repository-level secret"""
        # Check if secret already exists
        if self.check_repository_secret_exists(org, repo, name, session):
            self.logger.info(f"Repository secret '{name}' already exists in {repo} - skipping")
            return None  # Return None to indicate skipped
        
        # If no actual value provided and create_placeholder is True, use a placeholder value
        if value == '[ENCRYPTED_SECRET_VALUE]' or not value.strip():
            if create_placeholder:
                self.logger.info(f"Creating secret {name} in {repo} with placeholder value (to be set manually later)")
                value = "PLACEHOLDER_VALUE_SET_MANUALLY"
            else:
                self.logger.warning(f"Cannot create secret {name} in {repo} - no actual value provided")
                return False
        
        # Get public key for encryption
        public_key_info = self.get_repository_public_key(org, repo, session)
        if not public_key_info:
            self.logger.error(f"Failed to get public key for repository {org}/{repo}")
            return False
        
        try:
            encrypted_value = self.encrypt_secret(value, public_key_info['key'])
        except Exception as e:
            self.logger.error(f"Failed to encrypt secret {name}: {e}")
            return False
        
        url = f"{self.base_url}/repos/{org}/{repo}/actions/secrets/{name}"
        
        data = {
            'encrypted_value': encrypted_value,
            'key_id': public_key_info['key_id']
        }
        
        response = self._make_request(session, 'PUT', url, json=data)
        
        if response.status_code in [201, 204]:
            action = "Created/Updated"
            if value == "PLACEHOLDER_VALUE_SET_MANUALLY":
                action += " [PLACEHOLDER]"
            self.logger.info(f"{action} repository secret: {repo}/{name}")
            return True
        elif response.status_code == 404:
            self.logger.warning(f"Repository {org}/{repo} not found in target organization - skipping secret {name}")
            return False
        else:
            try:
                error_detail = response.json().get('message', 'Unknown error')
            except:
                error_detail = response.text
            self.logger.error(f"Failed to create repository secret {repo}/{name}: {response.status_code} - {error_detail}")
            return False

    def fetch_all_secrets(self) -> List[Dict]:
        """Fetch all secrets from source organization"""
        all_secrets = []
        
        # Fetch organization-level secrets
        org_secrets = self.get_organization_secrets(self.source_org, self.source_session)
        
        for secret in org_secrets:
            if not isinstance(secret, dict):
                self.logger.error(f"Org secret is not a dict: {type(secret)} - {secret}")
                continue
            
            selected_repos = secret.get('selected_repository_names', [])
            all_secrets.append({
                'scope': 'organization',
                'repository': '',
                'name': secret.get('name', ''),
                'value': secret.get('value', '[ENCRYPTED_SECRET_VALUE]'),
                'visibility': secret.get('visibility', 'all'),
                'selected_repositories': ','.join(selected_repos) if selected_repos else '',
                'created_at': secret.get('created_at', ''),
                'updated_at': secret.get('updated_at', '')
            })
        
        # Fetch repository-level secrets
        repos = self.get_organization_repositories(self.source_org, self.source_session)
        
        for repo in repos:
            if not isinstance(repo, dict) or 'name' not in repo:
                continue
            
            repo_name = repo['name']
            repo_secrets = self.get_repository_secrets(self.source_org, repo_name, self.source_session)
            
            for secret in repo_secrets:
                if not isinstance(secret, dict):
                    self.logger.error(f"Repo secret is not a dict: {type(secret)} - {secret}")
                    continue
                
                all_secrets.append({
                    'scope': 'repository',
                    'repository': repo_name,
                    'name': secret.get('name', ''),
                    'value': secret.get('value', '[ENCRYPTED_SECRET_VALUE]'),
                    'visibility': '',  # Repository secrets don't have visibility
                    'selected_repositories': '',
                    'created_at': secret.get('created_at', ''),
                    'updated_at': secret.get('updated_at', '')
                })
        return all_secrets

    def migrate_secrets_from_csv(self, csv_filename: str, create_placeholder: bool = True) -> Tuple[int, int, int]:
        """Migrate secrets from a CSV file where actual secret values have been manually provided"""
        self.logger.info(f"Loading secrets from CSV file: {csv_filename}")
        
        if not os.path.exists(csv_filename):
            self.logger.error(f"CSV file not found: {csv_filename}")
            return 0, 1, 0
        
        secrets_data = []
        try:
            with open(csv_filename, 'r', newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                secrets_data = list(reader)
        except Exception as e:
            self.logger.error(f"Failed to read CSV file: {e}")
            return 0, 1, 0
        
        return self.migrate_secrets(secrets_data, create_placeholder)

    def migrate_secrets(self, secrets_data: List[Dict], create_placeholder: bool = True) -> Tuple[int, int, int]:
        """Migrate secrets to target organization"""
        success_count = 0
        error_count = 0
        skipped_count = 0
        
        mode = "with placeholder values" if create_placeholder else "only with actual values"
        self.logger.info(f"Starting migration of {len(secrets_data)} secrets {mode}")
        
        for secret in secrets_data:
            try:
                if not isinstance(secret, dict):
                    self.logger.error(f"Secret is not a dict: {type(secret)} - {secret}")
                    error_count += 1
                    continue
                
                if secret.get('scope') == 'organization':
                    selected_repos = secret.get('selected_repositories', '').split(',') if secret.get('selected_repositories') else []
                    selected_repos = [repo.strip() for repo in selected_repos if repo.strip()]
                    
                    success = self.create_organization_secret(
                        self.target_org, 
                        secret.get('name', ''), 
                        secret.get('value', ''), 
                        secret.get('visibility', 'all'),
                        selected_repos,
                        self.target_session,
                        create_placeholder
                    )
                elif secret.get('scope') == 'repository':
                    success = self.create_repository_secret(
                        self.target_org, 
                        secret.get('repository', ''), 
                        secret.get('name', ''), 
                        secret.get('value', ''), 
                        self.target_session,
                        create_placeholder
                    )
                else:
                    self.logger.error(f"Unknown scope: {secret.get('scope')}")
                    success = False
                
                if success:
                    success_count += 1
                elif success is False:  # Explicitly failed
                    error_count += 1
                else:  # Skipped (None)
                    skipped_count += 1
            except Exception as e:
                self.logger.error(f"Error migrating secret {secret.get('name', 'UNKNOWN')}: {e}")
                error_count += 1
        
        self.logger.info(f"Migration completed. Success: {success_count}, Errors: {error_count}, Skipped: {skipped_count}")
        return success_count, error_count, skipped_count

    def run_export_only(self) -> None:
        """Run export process only (for inspection and manual value entry)"""
        try:
            self.logger.info("Starting GitHub Secrets Export (Export Only Mode)")
            
            # Fetch all secrets from source
            secrets_data = self.fetch_all_secrets()
            
            if not secrets_data:
                self.logger.warning("No secrets found to export")
                return
            
            # Export to CSV
            csv_filename = f"github_secrets_export.csv"
            self.export_secrets_to_csv(secrets_data, csv_filename)
            
            self.logger.info("Export process completed successfully")
            self.logger.info(f"Total secrets exported: {len(secrets_data)}")
            self.logger.info(f"Secrets exported to: {csv_filename}")
            self.logger.info("NOTE: You need to manually enter actual secret values in the CSV file before running migration")
        except Exception as e:
            self.logger.error(f"Export failed: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    def run_migration_from_csv(self, csv_filename: str, create_placeholder: bool = True) -> None:
        """Run migration from a prepared CSV file"""
        try:
            mode = "with placeholder values" if create_placeholder else "only with actual values"
            self.logger.info(f"Starting GitHub Secrets Migration from CSV {mode}")
            
            # Migrate secrets from CSV
            success_count, error_count, skipped_count = self.migrate_secrets_from_csv(csv_filename, create_placeholder)
            
            self.logger.info("Migration process completed successfully")
            self.logger.info(f"Successfully migrated: {success_count}")
            self.logger.info(f"Errors: {error_count}")
            self.logger.info(f"Skipped: {skipped_count}")
            
            if create_placeholder and success_count > 0:
                self.logger.info("NOTE: Secrets created with placeholder values need to be manually updated with actual values")
        except Exception as e:
            self.logger.error(f"Migration failed: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    def run_complete_migration(self) -> None:
        """Run the complete migration process: export and then migrate with placeholders"""
        try:
            self.logger.info("Starting Complete GitHub Secrets Migration (Export + Migrate with Placeholders)")
            
            # Fetch all secrets from source
            secrets_data = self.fetch_all_secrets()
            
            if not secrets_data:
                self.logger.warning("No secrets found to migrate")
                return
            
            # Export to CSV
            csv_filename = f"github_secrets_export.csv"
            self.export_secrets_to_csv(secrets_data, csv_filename)
            
            # Migrate secrets with placeholder values
            success_count, error_count, skipped_count = self.migrate_secrets(secrets_data, create_placeholder=True)
            
            self.logger.info("Complete migration process completed successfully")
            self.logger.info(f"Total secrets processed: {len(secrets_data)}")
            self.logger.info(f"Successfully migrated: {success_count}")
            self.logger.info(f"Errors: {error_count}")
            self.logger.info(f"Skipped: {skipped_count}")
            self.logger.info(f"Secrets structure exported to: {csv_filename}")
            self.logger.info("NOTE: Secrets created with placeholder values - update them manually in GitHub UI")
        except Exception as e:
            self.logger.error(f"Migration failed: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            raise

def main():
    """Main entry point"""
    try:
        migrator = GitHubSecretsMigrator()
        migrator.run_complete_migration()
    except Exception as e:
        print(f"Error: {e}")
        return 1
    return 0

if __name__ == "__main__":
    exit(main())
