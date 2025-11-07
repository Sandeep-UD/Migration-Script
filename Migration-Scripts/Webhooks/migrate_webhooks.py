import os
import sys
import argparse
import logging
import csv
import json
from datetime import datetime
from github import Github, GithubException
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Configuration from Environment Variables ---
SOURCE_ORG = os.getenv('GH_ORG')
TARGET_ORG = os.getenv('TARGET_GH_ORG')
SOURCE_TOKEN = os.getenv('GH_PAT')
TARGET_TOKEN = os.getenv('TARGET_GH_PAT')
REPOSITORIES_CSV = os.getenv('REPOSITORIES_CSV', 'repositories.csv')
WEBHOOKS_EXPORT_FILE = os.getenv('WEBHOOKS_EXPORT_FILE', 'exported_webhooks.json')
LOG_FILE = os.getenv('LOG_FILE', 'webhook_migration.log')
CSV_REPORT_FILE = os.getenv('CSV_REPORT_FILE', 'webhook_migration_report.csv')

# --- Setup Logging ---
def setup_logging():
    """Configures logging to both console and a file."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stdout)
        ]
    )

class GitHubWebhookMigrator:
    """
    Handles the export and import of GitHub webhooks between repositories
    using separate authentication for source and target organizations.
    """

    def __init__(self):
        """
        Initializes the webhook migrator using environment variables.
        """
        # Validate required environment variables
        if not all([SOURCE_ORG, TARGET_ORG, SOURCE_TOKEN, TARGET_TOKEN]):
            missing_vars = []
            if not SOURCE_ORG: missing_vars.append('SOURCE_ORG')
            if not TARGET_ORG: missing_vars.append('TARGET_ORG') 
            if not SOURCE_TOKEN: missing_vars.append('GITHUB_SOURCE_TOKEN')
            if not TARGET_TOKEN: missing_vars.append('GITHUB_TARGET_TOKEN')
            
            logging.error(f"Missing required environment variables: {', '.join(missing_vars)}")
            logging.error("Please check your .env file and ensure all required variables are set.")
            sys.exit(1)

        self.source_org = SOURCE_ORG
        self.target_org = TARGET_ORG
        self.migration_results = []        # --- Authenticate to Source and Target GitHub ---
        try:
            self.source_github_api = Github(SOURCE_TOKEN)
            # Verify authentication by making a simple API call
            user = self.source_github_api.get_user()
            user.login  # Force the API call to verify token
            logging.info("Source GitHub authentication successful")
        except GithubException as e:
            if e.status == 401:
                logging.error("Source GitHub authentication failed: Invalid or expired token")
                logging.error("Please check your GITHUB_SOURCE_TOKEN in the .env file")
            else:
                logging.error(f"Source GitHub authentication failed: {e}")
            sys.exit(1)
        except Exception as e:
            logging.error(f"Source GitHub authentication error: {e}")
            sys.exit(1)

        try:
            self.target_github_api = Github(TARGET_TOKEN)
            # Verify authentication by making a simple API call
            user = self.target_github_api.get_user()
            user.login  # Force the API call to verify token
            logging.info("Target GitHub authentication successful")
        except GithubException as e:
            if e.status == 401:
                logging.error("Target GitHub authentication failed: Invalid or expired token")
                logging.error("Please check your GITHUB_TARGET_TOKEN in the .env file")
            else:
                logging.error(f"Target GitHub authentication failed: {e}")
            sys.exit(1)
        except Exception as e:
            logging.error(f"Target GitHub authentication error: {e}")
            sys.exit(1)

    def _get_repository(self, github_api, org, repo_name):
        """Fetches a repository object from the GitHub API."""
        repo_full_name = f"{org}/{repo_name}"
        
        try:
            logging.info(f"Fetching repository: {repo_full_name}")
            gh_repo = github_api.get_repo(repo_full_name)
            logging.info(f"Repository found: {repo_full_name}")
            return gh_repo
        except GithubException as e:
            logging.error(f"Could not find repository: {repo_full_name}. Error: {e}")
            return None

    def _get_webhooks(self, gh_repo, repo_full_name):
        """Retrieves a list of all webhooks from a repository."""
        logging.info(f"Fetching webhooks from {repo_full_name}...")
        try:
            hooks = gh_repo.get_hooks()
            logging.info(f"Found {hooks.totalCount} webhook(s) in the repository.")
            return list(hooks)
        except GithubException as e:
            logging.error(f"Failed to fetch webhooks from repository: {e}")
            return []

    def export_webhooks(self):
        """
        Exports webhooks from all source repositories listed in the CSV file.
        """
        logging.info("Starting webhook export process...")
        
        repositories = self.read_repositories_from_csv()
        if not repositories:
            logging.error("No valid repositories found in CSV file.")
            return

        exported_data = {
            'export_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'source_org': self.source_org,
            'target_org': self.target_org,
            'repositories': {}
        }

        for repo_mapping in repositories:
            source_repo = repo_mapping['source_repo']
            
            # Get source repository
            source_gh_repo = self._get_repository(self.source_github_api, self.source_org, source_repo)
            
            if source_gh_repo is None:
                logging.error(f"Skipping {source_repo} - could not access repository")
                continue
            
            # Get webhooks from source repository
            source_hooks = self._get_webhooks(source_gh_repo, f"{self.source_org}/{source_repo}")
            
            webhook_data = []
            for hook in source_hooks:
                if hook.active:  # Only export active webhooks
                    webhook_info = {
                        'url': hook.config.get('url'),
                        'content_type': hook.config.get('content_type', 'json'),
                        'insecure_ssl': hook.config.get('insecure_ssl', '0'),
                        'events': hook.events,
                        'active': hook.active
                    }
                    webhook_data.append(webhook_info)
                    logging.info(f"Exported webhook: {hook.config.get('url')}")
                else:
                    logging.info(f"Skipped inactive webhook: {hook.config.get('url')}")
            
            exported_data['repositories'][source_repo] = {
                'target_repo': repo_mapping['target_repo'],
                'webhooks': webhook_data
            }
            
            logging.info(f"Exported {len(webhook_data)} active webhooks from {source_repo}")

        # Save exported data to JSON file
        try:
            with open(WEBHOOKS_EXPORT_FILE, 'w', encoding='utf-8') as f:
                json.dump(exported_data, f, indent=2)
            logging.info(f"Webhooks exported successfully to {WEBHOOKS_EXPORT_FILE}")
            logging.info(f"Total repositories processed: {len(exported_data['repositories'])}")
        except Exception as e:
            logging.error(f"Failed to save exported webhooks: {e}")

    def import_webhooks(self):
        """
        Imports webhooks to target repositories from the exported JSON file.
        """
        logging.info("Starting webhook import process...")
        
        if not os.path.exists(WEBHOOKS_EXPORT_FILE):
            logging.error(f"Export file not found: {WEBHOOKS_EXPORT_FILE}")
            logging.error("Please run 'python migrate_webhooks.py export' first.")
            return

        try:
            with open(WEBHOOKS_EXPORT_FILE, 'r', encoding='utf-8') as f:
                exported_data = json.load(f)
        except Exception as e:
            logging.error(f"Failed to read export file: {e}")
            return

        logging.info(f"Import file created on: {exported_data.get('export_date', 'Unknown')}")
        
        for source_repo, repo_data in exported_data['repositories'].items():
            target_repo = repo_data['target_repo']
            webhooks = repo_data['webhooks']
            
            if not webhooks:
                logging.info(f"No webhooks to import for {source_repo} -> {target_repo}")
                continue
            
            # Get target repository
            target_gh_repo = self._get_repository(self.target_github_api, self.target_org, target_repo)
            
            if target_gh_repo is None:
                logging.error(f"Skipping {target_repo} - could not access repository")
                self._add_migration_result(source_repo, target_repo, 'N/A', 'N/A', 'FAILED', 'Could not access target repository')
                continue
            
            # Get existing target webhooks to avoid creating duplicates
            existing_target_hooks = {h.config.get('url') for h in target_gh_repo.get_hooks()}
            
            logging.info(f"Importing {len(webhooks)} webhooks to {target_repo}")
            
            for webhook in webhooks:
                webhook_url = webhook['url']
                
                if webhook_url in existing_target_hooks:
                    logging.warning(f"Webhook already exists in target: {webhook_url}")
                    self._add_migration_result(source_repo, target_repo, webhook_url, webhook['events'], 'SKIPPED', 'Webhook already exists in target')
                    continue
                
                # Prepare config for the new webhook
                new_config = {
                    "url": webhook['url'],
                    "content_type": webhook['content_type'],
                    "insecure_ssl": webhook['insecure_ssl']
                }
                
                try:
                    target_gh_repo.create_hook(
                        name="web",
                        config=new_config,
                        events=webhook['events'],
                        active=webhook['active']
                    )
                    logging.info(f"Successfully imported webhook: {webhook_url}")
                    self._add_migration_result(source_repo, target_repo, webhook_url, webhook['events'], 'SUCCESS', '')
                except GithubException as e:
                    logging.error(f"Failed to import webhook {webhook_url}: {e}")
                    self._add_migration_result(source_repo, target_repo, webhook_url, webhook['events'], 'FAILED', str(e))

        # Generate CSV report
        self.generate_csv_report()
        logging.info("Webhook import process finished.")

    def _add_migration_result(self, source_repo, target_repo, webhook_url, events, status, reason):
        """Helper method to add migration result."""
        result = {
            'source_org': self.source_org,
            'source_repo': source_repo,
            'target_org': self.target_org,
            'target_repo': target_repo,
            'webhook_url': webhook_url,
            'events': events,
            'status': status,
            'reason': reason,
            'migration_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        self.migration_results.append(result)

    def generate_csv_report(self):
        """Generates a CSV report of the migration process."""
        logging.info(f"Generating CSV migration report at {CSV_REPORT_FILE}")
        
        fieldnames = [
            'migration_date',
            'source_org',
            'source_repo',
            'target_org', 
            'target_repo',
            'webhook_url',
            'events',
            'status',
            'reason'
        ]

        try:
            with open(CSV_REPORT_FILE, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()

                if not self.migration_results:
                    writer.writerow({
                        'migration_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'source_org': 'N/A',
                        'source_repo': 'N/A',
                        'target_org': 'N/A',
                        'target_repo': 'N/A',
                        'webhook_url': 'N/A',
                        'events': 'N/A',
                        'status': 'NO_MIGRATION_PERFORMED',
                        'reason': 'No repositories processed'
                    })
                else:
                    for result in self.migration_results:
                        # Convert events list to comma-separated string for CSV
                        events_str = ', '.join(result['events']) if isinstance(result['events'], list) else str(result['events'])
                        
                        writer.writerow({
                            'migration_date': result['migration_date'],
                            'source_org': result['source_org'],
                            'source_repo': result['source_repo'],
                            'target_org': result['target_org'],
                            'target_repo': result['target_repo'],
                            'webhook_url': result['webhook_url'],
                            'events': events_str,
                            'status': result['status'],
                            'reason': result['reason']
                        })

            logging.info("CSV report generation complete.")
            
        except Exception as e:
            logging.error(f"Failed to generate CSV report: {e}")

    def read_repositories_from_csv(self):
        """
        Reads repository mappings from a CSV file.
        
        Expected CSV format:
        source_repo,target_repo
        repo1,target-repo1
        repo2,target-repo2
        
        Returns:
            list: List of dictionaries containing repository mappings
        """
        repositories = []
        
        if not os.path.exists(REPOSITORIES_CSV):
            logging.error(f"CSV file not found: {REPOSITORIES_CSV}")
            return repositories
            
        try:
            with open(REPOSITORIES_CSV, 'r', newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                
                # Validate required columns
                required_columns = {'source_repo', 'target_repo'}
                if not required_columns.issubset(reader.fieldnames):
                    missing_columns = required_columns - set(reader.fieldnames)
                    logging.error(f"Missing required columns in CSV: {missing_columns}")
                    logging.error(f"Available columns: {reader.fieldnames}")
                    return repositories
                
                for row_num, row in enumerate(reader, start=2):  # Start at 2 because of header
                    # Skip empty rows
                    if not any(row.values()):
                        continue
                        
                    # Validate required fields are not empty
                    missing_fields = [field for field in required_columns if not row[field].strip()]
                    if missing_fields:
                        logging.warning(f"Row {row_num}: Skipping row with missing fields: {missing_fields}")
                        continue
                    
                    repo_mapping = {
                        'source_repo': row['source_repo'].strip(),
                        'target_repo': row['target_repo'].strip()
                    }
                    repositories.append(repo_mapping)
                    
            logging.info(f"Successfully loaded {len(repositories)} repository mappings from CSV")
            return repositories
            
        except Exception as e:
            logging.error(f"Failed to read CSV file {REPOSITORIES_CSV}: {e}")
            return repositories

def main():
    """Main function to parse arguments and run the migrator."""
    setup_logging()

    parser = argparse.ArgumentParser(
        description="Export and import GitHub webhooks between repositories using environment variables.",
        epilog="""
Examples:
  python migrate_webhooks.py export   # Export webhooks from source repositories
  python migrate_webhooks.py import   # Import webhooks to target repositories
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        'command', 
        choices=['export', 'import'], 
        help='Command to execute: export webhooks from source repos or import to target repos'
    )

    args = parser.parse_args()

    # Check if .env file exists
    if not os.path.exists('.env'):
        logging.error(".env file not found. Please create a .env file with the required environment variables.")
        logging.error("Required variables: GITHUB_SOURCE_TOKEN, GITHUB_TARGET_TOKEN, SOURCE_ORG, TARGET_ORG")
        sys.exit(1)

    # Initialize the migrator
    migrator = GitHubWebhookMigrator()

    if args.command == 'export':
        logging.info("=== Starting Webhook Export Process ===")
        migrator.export_webhooks()
    elif args.command == 'import':
        logging.info("=== Starting Webhook Import Process ===")
        migrator.import_webhooks()

if __name__ == '__main__':
    main()
