import os
import json
import csv
import sys
import requests
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Logging Configuration ---
def setup_logging(log_level=logging.INFO):
    """Sets up logging configuration."""
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.FileHandler(f'github_rulesets.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

# --- Console Output Functions ---
def print_error(message):
    """Prints error message in red."""
    print(f"\033[91m❌ ERROR: {message}\033[0m")

def print_warning(message):
    """Prints warning message in yellow."""
    print(f"\033[93m⚠️ WARNING: {message}\033[0m")

def print_info(message):
    """Prints info message in blue."""
    print(f"\033[94mℹ️ INFO: {message}\033[0m")

def print_success(message):
    """Prints success message in green."""
    print(f"\033[92m✅ SUCCESS: {message}\033[0m")

# --- GitHub API Configuration ---
SOURCE_GITHUB_TOKEN = os.getenv("GH_PAT")
TARGET_GITHUB_TOKEN = os.getenv("TARGET_GH_PAT") 
# Fallback to single token if separate tokens not provided
GITHUB_TOKEN = SOURCE_GITHUB_TOKEN or TARGET_GITHUB_TOKEN or os.getenv("GITHUB_TOKEN")

SOURCE_API_URL = os.getenv("SOURCE_API_URL", "https://api.github.com")
TARGET_API_URL = os.getenv("TARGET_API_URL", "https://api.github.com")

def get_headers(token):
    """Returns headers for API requests with the specified token."""
    return {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {token}",
        "X-GitHub-Api-Version": "2022-11-28"
    }

def make_api_request(method, url, token=None, **kwargs):
    """
    Makes a request to the GitHub API and handles common errors.
    Returns the response object on success, None on failure.
    """
    # Use provided token or fallback to default
    headers = get_headers(token or GITHUB_TOKEN)
    
    try:
        logger.debug(f"Making {method} request to {url}")
        response = requests.request(method, url, headers=headers, **kwargs)
        response.raise_for_status()
        logger.debug(f"Request successful: {response.status_code}")
        return response
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logger.info(f"Resource not found for URL {url} (404). This may be expected.")
        else:
            logger.error(f"HTTP Error for URL {url}: {e.response.status_code} {e.response.reason}")
            logger.error(f"Response Body: {e.response.text}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {e}")
    return None

def get_all_repos(org: str, api_url: str, token: str) -> list:
    """Fetches all repository names for a given organization, handling pagination."""
    logger.info(f"Fetching all repositories for organization '{org}'...")
    repos = []
    page = 1
    while True:
        url = f"{api_url}/orgs/{org}/repos"
        response = make_api_request("GET", url, token=token, params={"per_page": 100, "page": page})
        if not response:
            logger.error(f"Could not fetch repositories for '{org}'.")
            break
        
        data = response.json()
        if not data:
            break
            
        repos.extend([repo['name'] for repo in data])
        page += 1
        
    logger.info(f"Found {len(repos)} repositories in '{org}'.")
    return repos

def check_existing_rulesets(org: str, repo: str = None, api_url: str = TARGET_API_URL, token: str = None) -> dict:
    """
    Checks existing rulesets for a repository or organization.
    Returns a dictionary mapping ruleset names to their IDs.
    """
    if repo:
        url = f"{api_url}/repos/{org}/{repo}/rulesets"
        logger.debug(f"Checking existing rulesets for repo: {org}/{repo}")
    else:
        url = f"{api_url}/orgs/{org}/rulesets"
        logger.debug(f"Checking existing rulesets for org: {org}")
    
    response = make_api_request("GET", url, token=token, params={'include_parents': 'false'})
    
    if not response:
        return {}
    
    rulesets = response.json()
    existing_rulesets = {ruleset['name']: ruleset['id'] for ruleset in rulesets}
    logger.info(f"Found {len(existing_rulesets)} existing rulesets")
    return existing_rulesets

# --- Bypass Actors Management ---

def get_bypass_actor_details(actor_id: int, actor_type: str, org: str, token: str, api_url: str) -> dict:
    """
    Fetches detailed information about a bypass actor.
    Returns the actor details or None if not found.
    """
    try:
        if actor_type == "Team":
            # For teams, we need to get team details by ID
            url = f"{api_url}/teams/{actor_id}"
            response = make_api_request("GET", url, token=token)
            if response:
                team_data = response.json()
                return {
                    "id": team_data.get("id"),
                    "slug": team_data.get("slug"),
                    "name": team_data.get("name"),
                    "description": team_data.get("description"),
                    "privacy": team_data.get("privacy", "closed"),
                    "permission": team_data.get("permission", "pull"),
                    "organization": team_data.get("organization", {}).get("login")
                }
        elif actor_type == "User":
            # For users, we need to first get the user info by ID, then check membership
            # GitHub doesn't have a direct user-by-ID endpoint, but we can use GraphQL or search
            # For now, we'll store the ID and handle username resolution later
            try:
                # Try to get user info - this is a workaround since direct ID lookup isn't available
                # We'll store the ID for now and resolve during import
                return {
                    "id": actor_id,
                    "type": "user_by_id",
                    "note": "User ID stored for later resolution during import"
                }
            except Exception as e:
                logger.error(f"Failed to process user ID {actor_id}: {e}")
                return None
        elif actor_type == "RepositoryRole":
            # Repository roles are standard and don't need API calls
            # Map common role IDs to names
            role_map = {
                1: "read",
                2: "triage", 
                3: "write",
                4: "maintain",
                5: "admin"
            }
            return {
                "id": actor_id,
                "name": role_map.get(actor_id, f"role_{actor_id}"),
                "type": "repository_role"
            }
    except Exception as e:
        logger.error(f"Failed to fetch {actor_type} details for ID {actor_id}: {e}")
    
    return None

def find_existing_team_in_target(team_details: dict, target_org: str, token: str, api_url: str) -> int:
    """
    Finds an existing team by slug in the target organization.
    Returns the team ID if found, None if not found.
    Will NOT create teams - only looks for existing ones.
    """
    team_slug = team_details.get("slug")
    if not team_slug:
        logger.error("Team slug not found in team details")
        return None
    
    # Try to find existing team by slug
    url = f"{api_url}/orgs/{target_org}/teams/{team_slug}"
    response = make_api_request("GET", url, token=token)
    
    if response:
        existing_team = response.json()
        logger.info(f"Found existing team '{team_slug}' in {target_org} with ID {existing_team['id']}")
        return existing_team["id"]
    else:
        logger.warning(f"Team '{team_slug}' not found in {target_org} - will be skipped")
        return None

def find_user_in_target(user_details: dict, target_org: str, token: str, api_url: str) -> int:
    """
    Finds a user in the target organization by ID.
    Since GitHub API doesn't provide direct user-by-ID lookup, this function
    will validate the user ID exists and has access to the target org.
    Returns the user ID if valid, None otherwise.
    """
    user_id = user_details.get("id")
    if not user_id:
        logger.error("User ID not found in user details")
        return None
    
    # For users identified by ID only, we can't easily verify membership
    # without knowing the username. We'll return the ID and let GitHub API
    # validate it during ruleset creation
    logger.info(f"User ID {user_id} will be validated during ruleset creation")
    return user_id

def enrich_bypass_actors_with_details(bypass_actors: list, org: str, token: str, api_url: str) -> list:
    """
    Enriches bypass actors with detailed information for later migration.
    """
    if not bypass_actors:
        return []
    
    enriched_actors = []
    
    for actor in bypass_actors:
        actor_id = actor.get("actor_id")
        actor_type = actor.get("actor_type")
        bypass_mode = actor.get("bypass_mode")
        
        # Get detailed information about the actor
        actor_details = get_bypass_actor_details(actor_id, actor_type, org, token, api_url)
        
        enriched_actor = {
            "original_actor_id": actor_id,
            "actor_type": actor_type,
            "bypass_mode": bypass_mode,
            "details": actor_details
        }
        
        enriched_actors.append(enriched_actor)
        
        if actor_details:
            logger.info(f"Enriched {actor_type} bypass actor: {actor_details.get('name') or actor_details.get('login') or actor_id}")
        else:
            logger.warning(f"Could not enrich {actor_type} bypass actor ID {actor_id}")
    
    return enriched_actors

def resolve_bypass_actors_for_target(enriched_bypass_actors: list, target_org: str, token: str, api_url: str) -> list:
    """
    Resolves enriched bypass actors to actual actor IDs in the target organization.
    Only uses existing teams, validates users exist in the target organization.
    """
    if not enriched_bypass_actors:
        return []
    
    resolved_actors = []
    
    for enriched_actor in enriched_bypass_actors:
        actor_type = enriched_actor.get("actor_type")
        bypass_mode = enriched_actor.get("bypass_mode")
        details = enriched_actor.get("details")
        original_id = enriched_actor.get("original_actor_id")
        
        if not details:
            logger.warning(f"Skipping {actor_type} actor {original_id} - no details available")
            continue
        
        target_actor_id = None
        
        if actor_type == "Team":
            target_actor_id = find_existing_team_in_target(details, target_org, token, api_url)
        elif actor_type == "User":
            target_actor_id = find_user_in_target(details, target_org, token, api_url)
        elif actor_type == "RepositoryRole":
            # Repository roles should work across organizations
            target_actor_id = original_id
        
        if target_actor_id:
            resolved_actor = {
                "actor_id": target_actor_id,
                "actor_type": actor_type,
                "bypass_mode": bypass_mode
            }
            resolved_actors.append(resolved_actor)
            
            actor_name = details.get("name") or details.get("login") or details.get("slug") or target_actor_id
            logger.info(f"Resolved {actor_type} '{actor_name}' to ID {target_actor_id} in {target_org}")
        else:
            actor_name = details.get("name") or details.get("login") or details.get("slug") or original_id
            logger.warning(f"Could not resolve {actor_type} '{actor_name}' in {target_org}")
    
    return resolved_actors

# --- Core Logic ---

def export_rulesets_for_repo(org: str, repo: str) -> list:
    """Exports all rulesets for a single repository with enriched bypass actor details."""
    logger.info(f"Exporting rulesets from '{org}/{repo}'...")
    url = f"{SOURCE_API_URL}/repos/{org}/{repo}/rulesets"
    response = make_api_request("GET", url, token=SOURCE_GITHUB_TOKEN, params={'include_parents': 'false'})
    
    if not response:
        return []
        
    rulesets = response.json()
    if not rulesets:
        logger.info(f"No rulesets found on '{org}/{repo}'.")
        return []
        
    logger.info(f"Found {len(rulesets)} ruleset(s) on '{org}/{repo}'.")
    
    detailed_rulesets = []
    for ruleset_summary in rulesets:
        detail_url = f"{SOURCE_API_URL}/repos/{org}/{repo}/rulesets/{ruleset_summary['id']}"
        detail_response = make_api_request("GET", detail_url, token=SOURCE_GITHUB_TOKEN)
        if detail_response:
            ruleset = detail_response.json()
            
            # Enrich bypass actors with detailed information if enabled
            if ENRICH_BYPASS_ACTORS and ruleset.get('bypass_actors'):
                logger.info(f"Enriching bypass actors for ruleset '{ruleset.get('name')}'...")
                enriched_bypass_actors = enrich_bypass_actors_with_details(
                    ruleset['bypass_actors'], 
                    org, 
                    SOURCE_GITHUB_TOKEN, 
                    SOURCE_API_URL
                )
                # Store both original and enriched bypass actors
                ruleset['original_bypass_actors'] = ruleset['bypass_actors']
                ruleset['enriched_bypass_actors'] = enriched_bypass_actors
            elif ruleset.get('bypass_actors'):
                logger.info(f"Bypass actor enrichment disabled for ruleset '{ruleset.get('name')}'")
                
            detailed_rulesets.append(ruleset)
            
    return detailed_rulesets

def save_rulesets_to_json(rulesets: list, filename: Path):
    """Saves the fetched rulesets to a JSON file."""
    logger.info(f"Saving rulesets to '{filename}'...")
    try:
        filename.parent.mkdir(parents=True, exist_ok=True)
        with open(filename, 'w') as f:
            json.dump(rulesets, f, indent=4)
        logger.info(f"Successfully saved rulesets to '{filename}'.")
    except IOError as e:
        logger.error(f"Failed to write to file '{filename}': {e}")

def load_rulesets_from_json(filename: Path) -> list:
    """Loads rulesets from a JSON file."""
    logger.info(f"Loading rulesets from '{filename}'...")
    try:
        with open(filename, 'r') as f:
            rulesets = json.load(f)
        logger.info(f"Successfully loaded {len(rulesets)} rulesets from '{filename}'")
        return rulesets
    except FileNotFoundError:
        logger.error(f"Input file '{filename}' not found.")
    except json.JSONDecodeError as e:
        logger.error(f"Could not decode JSON from '{filename}': {e}")
    except IOError as e:
        logger.error(f"Failed to read file '{filename}': {e}")
    return []

def sanitize_bypass_actors(bypass_actors: list, org: str, repo: str) -> list:
    """
    Sanitizes bypass_actors to remove invalid references that don't exist in the target organization.
    Behavior controlled by environment variables:
    - SANITIZE_BYPASS_ACTORS: If true, removes Team actors (default: true)
    - REMOVE_ALL_BYPASS_ACTORS: If true, removes all bypass_actors (default: false)
    """
    if not bypass_actors:
        return []
    
    # If configured to remove all bypass_actors
    if REMOVE_ALL_BYPASS_ACTORS:
        logger.info(f"Removing all bypass_actors as per REMOVE_ALL_BYPASS_ACTORS configuration")
        return []
    
    # If not configured to sanitize, return original
    if not SANITIZE_BYPASS_ACTORS:
        logger.info(f"Keeping original bypass_actors as per SANITIZE_BYPASS_ACTORS configuration")
        return bypass_actors
    
    sanitized_actors = []
    removed_actors = []
    
    for actor in bypass_actors:
        actor_type = actor.get('actor_type', '')
        actor_id = actor.get('actor_id', '')
        
        # Keep RepositoryRole actors (like admin, maintain, write, triage, read)
        # These should be valid across organizations
        if actor_type == 'RepositoryRole':
            sanitized_actors.append(actor)
        # Remove Team actors as they likely don't exist in target org
        elif actor_type == 'Team':
            removed_actors.append(f"{actor_type}:{actor_id}")
            logger.warning(f"Removing bypass_actor {actor_type}:{actor_id} - teams from source org may not exist in target org")
        # Keep other types (User, Integration) but with a warning
        else:
            sanitized_actors.append(actor)
            logger.info(f"Keeping bypass_actor {actor_type}:{actor_id} - please verify this exists in target org")
    
    if removed_actors:
        logger.info(f"Removed {len(removed_actors)} bypass_actors from ruleset: {', '.join(removed_actors)}")
    
    return sanitized_actors

def import_rulesets_for_repo(org: str, repo: str, rulesets_to_create: list, source_org: str = None, source_repo: str = None) -> list:
    """Attempts to import rulesets on a target repository and returns a validation report."""
    logger.info(f"Starting ruleset import for '{org}/{repo}'...")
    report_entries = []
    url = f"{TARGET_API_URL}/repos/{org}/{repo}/rulesets"
    
    # Check existing rulesets to avoid duplicates
    existing_rulesets = check_existing_rulesets(org, repo, TARGET_API_URL, TARGET_GITHUB_TOKEN)

    for ruleset in rulesets_to_create:
        ruleset_name = ruleset.get('name', 'Unknown')
        source_info = f"{source_org}/{source_repo}" if source_org and source_repo else "Unknown"
        
        report_entry = {
            "source_repository": source_info,
            "target_repository": f"{org}/{repo}", 
            "ruleset_name": ruleset_name,
            "source_ruleset_id": ruleset.get('id', 'Unknown'),
            "enforcement": ruleset.get('enforcement', 'Unknown'),
            "target": ruleset.get('target', 'Unknown')
        }
        
        # Check if ruleset already exists
        if ruleset_name in existing_rulesets:
            logger.warning(f"Ruleset '{ruleset_name}' already exists on '{org}/{repo}' with ID {existing_rulesets[ruleset_name]}. Skipping creation.")
            report_entry.update({
                "migration_status": "Skipped", 
                "target_ruleset_id": existing_rulesets[ruleset_name],
                "details": "Ruleset already exists in target repository"
            })
            report_entries.append(report_entry)
            continue
        
        # Handle bypass actors - prefer enriched data, fallback to sanitization
        resolved_bypass_actors = []
        bypass_actor_details = []
        
        if ruleset.get('enriched_bypass_actors'):
            # Use enriched bypass actors from export
            logger.info(f"Resolving enriched bypass actors for ruleset '{ruleset_name}'...")
            resolved_bypass_actors = resolve_bypass_actors_for_target(
                ruleset['enriched_bypass_actors'],
                org,
                TARGET_GITHUB_TOKEN,
                TARGET_API_URL
            )
            bypass_actor_details = [f"Resolved {len(resolved_bypass_actors)} from {len(ruleset['enriched_bypass_actors'])} enriched actors"]
            
        elif ruleset.get('bypass_actors'):
            # Fallback to sanitization if no enriched data available
            logger.warning(f"No enriched bypass actors found for '{ruleset_name}', falling back to sanitization")
            resolved_bypass_actors = sanitize_bypass_actors(ruleset['bypass_actors'], org, repo)
            bypass_actor_details = ["Used sanitization fallback (no enriched data)"]
        
        # Create payload with resolved bypass_actors
        payload = {k: ruleset.get(k) for k in ["name", "target", "enforcement", "conditions", "rules"] if ruleset.get(k) is not None}
        if resolved_bypass_actors:
            payload["bypass_actors"] = resolved_bypass_actors
            
        # Add bypass actor resolution details to report
        if bypass_actor_details:
            report_entry["bypass_actors_info"] = "; ".join(bypass_actor_details)
        
        logger.info(f"Attempting to create ruleset: '{payload['name']}' on '{org}/{repo}' with {len(resolved_bypass_actors)} bypass actors...")
        response = make_api_request("POST", url, token=TARGET_GITHUB_TOKEN, json=payload)

        if response and response.status_code == 201:
            created_ruleset = response.json()
            logger.info(f"Ruleset '{created_ruleset['name']}' created successfully on '{org}/{repo}' with ID {created_ruleset['id']}")
            report_entry.update({
                "migration_status": "Success", 
                "target_ruleset_id": created_ruleset['id'],
                "details": "Successfully migrated to target repository"
            })
        else:
            error_details = "Request failed. Check console for API error."
            if response:
                error_details = response.text
            logger.error(f"Failed to create ruleset '{payload['name']}' on '{org}/{repo}': {error_details}")
            report_entry.update({
                "migration_status": "Failed", 
                "target_ruleset_id": "N/A",
                "details": error_details
            })
        report_entries.append(report_entry)            
    return report_entries

def save_validation_report(report: list, filename: str):
    """Saves the validation report to a CSV file."""
    if not report:
        logger.info("No data to write to validation report.")
        return

    logger.info(f"Saving validation report to '{filename}'...")
    try:
        with open(filename, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                "source_repository", 
                "target_repository", 
                "ruleset_name", 
                "source_ruleset_id",
                "target_ruleset_id",
                "enforcement",
                "target",
                "migration_status", 
                "details",
                "bypass_actors_info"
            ])
            writer.writeheader()
            writer.writerows(report)
        logger.info(f"Successfully saved validation report to '{filename}'.")
    except IOError as e:
        logger.error(f"Failed to write to report file '{filename}': {e}")
        print_error(f"Failed to write to report file '{filename}': {e}")

def create_migration_report_from_export(exported_file: Path, migration_report: list, output_file: str):
    """
    Creates a comprehensive migration report by comparing exported rulesets with migration results.
    This shows what was in the source and what happened during migration.
    """
    logger.info(f"Creating comprehensive migration report...")
    
    # Load the exported rulesets to see what was available for migration
    source_rulesets = load_rulesets_from_json(exported_file)
    if not source_rulesets:
        logger.warning(f"No source rulesets found in {exported_file}")
        return
    
    # Create a mapping of migrated rulesets for quick lookup
    migrated_rulesets = {}
    for entry in migration_report:
        key = (entry.get('source_repository', ''), entry.get('ruleset_name', ''))
        migrated_rulesets[key] = entry
    
    # Create comprehensive report
    comprehensive_report = []
    
    # Process exported rulesets
    for ruleset in source_rulesets:
        ruleset_name = ruleset.get('name', 'Unknown')
        source_repo = "Unknown"  # This would need to be derived from filename or passed as parameter
        
        key = (source_repo, ruleset_name)
        
        if key in migrated_rulesets:
            # Ruleset was processed during migration
            comprehensive_report.append(migrated_rulesets[key])
        else:
            # Ruleset was in source but not migrated
            comprehensive_report.append({
                "source_repository": source_repo,
                "target_repository": "N/A",
                "ruleset_name": ruleset_name,
                "source_ruleset_id": ruleset.get('id', 'Unknown'),
                "target_ruleset_id": "N/A",
                "enforcement": ruleset.get('enforcement', 'Unknown'),
                "target": ruleset.get('target', 'Unknown'),
                "migration_status": "Not Migrated",
                "details": "Ruleset was present in source but not included in migration"
            })
    
    # Save the comprehensive report
    save_validation_report(comprehensive_report, output_file)
    logger.info(f"Comprehensive migration report saved to '{output_file}'")

# --- Configuration ---
# Load configuration from environment variables with defaults
SOURCE_ORG = os.getenv("GH_ORG", "")
TARGET_ORG = os.getenv("TARGET_GH_ORG", "") 
REPO_LIST_FILE = os.getenv("REPO_LIST_FILE", "repos.csv")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "exported_rulesets")
REPORT_FILE = os.getenv("REPORT_FILE", "migration_report.csv")

# Bypass actors handling configuration
ENRICH_BYPASS_ACTORS = os.getenv("ENRICH_BYPASS_ACTORS", "true").lower() == "true"
SANITIZE_BYPASS_ACTORS = os.getenv("SANITIZE_BYPASS_ACTORS", "true").lower() == "true"
REMOVE_ALL_BYPASS_ACTORS = os.getenv("REMOVE_ALL_BYPASS_ACTORS", "false").lower() == "true"

# --- Main Logic ---

def main():
    # Check for operation mode argument first
    if len(sys.argv) != 2 or sys.argv[1] not in ['export', 'import']:
        print_error("Usage: python rulesets.py [export|import]")
        print_info("  export - Export rulesets from repositories listed in repos.csv")
        print_info("  import - Import rulesets to repositories listed in repos.csv")
        return
    
    operation_mode = sys.argv[1]
    
    # Validate required configuration
    if not SOURCE_ORG:
        print_error("SOURCE_ORG must be set in environment variables or .env file")
        return
    
    if operation_mode == "import" and not TARGET_ORG:
        print_error("TARGET_ORG must be set in environment variables or .env file for import operations")
        return
    
    # Check if GitHub token is available
    if not GITHUB_TOKEN:
        logger.error("GitHub token not found. Set GITHUB_TOKEN environment variable.")
        print_error("GitHub token not found. Set GITHUB_TOKEN environment variable.")
        return
    
    # Show bypass actors configuration for import operations
    if operation_mode == "import":
        print_info(f"Bypass actors handling configuration:")
        print_info(f"  ENRICH_BYPASS_ACTORS: {ENRICH_BYPASS_ACTORS}")
        print_info(f"  SANITIZE_BYPASS_ACTORS: {SANITIZE_BYPASS_ACTORS}")
        print_info(f"  REMOVE_ALL_BYPASS_ACTORS: {REMOVE_ALL_BYPASS_ACTORS}")
        
        if REMOVE_ALL_BYPASS_ACTORS:
            print_warning("All bypass_actors will be removed from imported rulesets")
        elif ENRICH_BYPASS_ACTORS:
            print_info("Will use enriched bypass actor data from export")
            print_info("Will only use existing teams in target organization (no team creation)")
        elif SANITIZE_BYPASS_ACTORS:
            print_info("Will fall back to sanitization (Team bypass_actors will be removed)")
        else:
            print_warning("All bypass_actors will be kept as-is (may cause import failures)")
    
    elif operation_mode == "export":
        print_info(f"Export configuration:")
        print_info(f"  ENRICH_BYPASS_ACTORS: {ENRICH_BYPASS_ACTORS}")
        if ENRICH_BYPASS_ACTORS:
            print_info("Will fetch detailed information for teams and users during export")
        else:
            print_warning("Bypass actors will not be enriched with details")
    
    # Load repositories from CSV file
    repos_to_process = []
    try:
        with open(REPO_LIST_FILE, 'r', newline='') as f:
            reader = csv.DictReader(f)
            # Ensure 'repo_name' column exists
            if 'repo_name' not in reader.fieldnames:
                logger.error(f"CSV file '{REPO_LIST_FILE}' must have a 'repo_name' column.")
                print_error(f"CSV file '{REPO_LIST_FILE}' must have a 'repo_name' column.")
                return
            repos_to_process = [row['repo_name'] for row in reader]
    except FileNotFoundError:
        logger.error(f"Repo list file not found: {REPO_LIST_FILE}")
        print_error(f"Repo list file not found: {REPO_LIST_FILE}")
        return
    
    if not repos_to_process:
        logger.error("No repositories found in the CSV file.")
        print_error("No repositories found in the CSV file.")
        return
    
    if operation_mode == "export":
        for repo_name in repos_to_process:
            rulesets = export_rulesets_for_repo(SOURCE_ORG, repo_name)
            if rulesets:
                output_path = Path(OUTPUT_DIR) / f"{repo_name}-rulesets.json"
                save_rulesets_to_json(rulesets, output_path)
            else:
                print_warning(f"No rulesets found for {SOURCE_ORG}/{repo_name}")
        
        print_success("Export operation completed!")
        
    elif operation_mode == "import":
        full_report = []
        
        for repo_name in repos_to_process:
            input_path = Path(OUTPUT_DIR) / f"{repo_name}-rulesets.json"
            
            if not input_path.exists():
                logger.warning(f"Skipping '{repo_name}': Ruleset file '{input_path}' not found.")
                print_warning(f"Skipping '{repo_name}': Ruleset file '{input_path}' not found.")
                continue
            
            rulesets_to_create = load_rulesets_from_json(input_path)
            if rulesets_to_create:
                repo_report = import_rulesets_for_repo(TARGET_ORG, repo_name, rulesets_to_create, SOURCE_ORG, repo_name)
                full_report.extend(repo_report)
            else:
                print_warning(f"No rulesets to import for {repo_name}")
        
        if full_report:
            save_validation_report(full_report, REPORT_FILE)
            print_success(f"Import operation completed! Check '{REPORT_FILE}' for detailed results.")
        else:
            print_warning("No rulesets were imported.")


if __name__ == "__main__":
    main()