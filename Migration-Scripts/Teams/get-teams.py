import os
import csv
import logging
import requests
import time
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('team_fetch.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class GitHubTeamFetcher:
    def __init__(self):
        """Initialize the GitHub Team Fetcher with credentials from environment variables."""
        self.token = os.getenv('GH_PAT')
        self.org_name = os.getenv('GH_ORG')
        
        if not self.token:
            raise ValueError("GITHUB_PAT environment variable is required")
        if not self.org_name:
            raise ValueError("GITHUB_ORG environment variable is required")
        
        self.headers = {
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        # Rate limiting settings
        self.rate_limit_delay = 0.5  # Default delay between requests in seconds
        self.max_retries = 3
        self.retry_delay = 60  # Delay when rate limit is hit
        
        logger.info(f"Initialized GitHub Team Fetcher for organization: {self.org_name}")

    def make_api_request(self, method, url, **kwargs):
        """Make API request with rate limiting and retry logic."""
        for attempt in range(self.max_retries):
            try:
                # Add delay between requests
                time.sleep(self.rate_limit_delay)
                
                response = requests.request(method, url, headers=self.headers, **kwargs)
                
                # Check rate limit headers
                remaining = int(response.headers.get('X-RateLimit-Remaining', 0))
                reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                
                # Log rate limit status periodically
                if remaining <= 100:  # Warning when getting close to limit
                    logger.warning(f"Rate limit low: {remaining} requests remaining")
                elif remaining % 500 == 0:  # Log every 500 requests
                    logger.info(f"Rate limit status: {remaining} requests remaining")
                
                # Handle rate limit exceeded
                if response.status_code == 403 and 'rate limit exceeded' in response.text.lower():
                    current_time = time.time()
                    sleep_time = max(reset_time - current_time, self.retry_delay)
                    logger.warning(f"Rate limit exceeded. Sleeping for {sleep_time:.0f} seconds...")
                    time.sleep(sleep_time)
                    continue
                
                # Handle other 4xx/5xx errors with exponential backoff
                # Don't retry on 404 (not found) as it's a valid response for membership checks
                if response.status_code >= 400 and response.status_code != 404:
                    if attempt < self.max_retries - 1:
                        backoff_time = (2 ** attempt) * self.rate_limit_delay
                        logger.warning(f"Request failed with {response.status_code}. Retrying in {backoff_time:.1f}s...")
                        time.sleep(backoff_time)
                        continue
                
                return response
                
            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries - 1:
                    backoff_time = (2 ** attempt) * self.rate_limit_delay
                    logger.warning(f"Request exception: {e}. Retrying in {backoff_time:.1f}s...")
                    time.sleep(backoff_time)
                    continue
                else:
                    logger.error(f"Request failed after {self.max_retries} attempts: {e}")
                    raise
        
        return response

    def check_rate_limit_status(self):
        """Check and display current rate limit status."""
        resp = self.make_api_request("GET", "https://api.github.com/rate_limit")
        if resp.status_code == 200:
            rate_limit = resp.json()
            core_limit = rate_limit['resources']['core']
            remaining = core_limit['remaining']
            limit = core_limit['limit']
            reset_time = core_limit['reset']
            
            # Convert reset time to readable format
            reset_datetime = datetime.fromtimestamp(reset_time)
            logger.info(f"Rate limit status: {remaining}/{limit} requests remaining. Resets at {reset_datetime}")
            
            return remaining, limit, reset_time
        else:
            logger.warning(f"Could not check rate limit status: {resp.status_code}")
            return None, None, None
    
    def get_teams(self):
        """Fetch all teams in the organization."""
        logger.info("Fetching teams from GitHub...")
        url = f"https://api.github.com/orgs/{self.org_name}/teams"
        
        teams = []
        page = 1
        
        while True:
            params = {'page': page, 'per_page': 100}
            response = self.make_api_request("GET", url, params=params)
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch teams: {response.status_code} - {response.text}")
                break
            
            page_teams = response.json()
            if not page_teams:
                break
            
            teams.extend(page_teams)
            logger.info(f"Fetched page {page} with {len(page_teams)} teams")
            page += 1
            
        logger.info(f"Total teams found: {len(teams)}")
        return teams
    
    def get_team_repos(self, team_slug):
        """Fetch repositories for a specific team with permission details."""
        logger.info(f"Fetching repositories for team: {team_slug}")
        url = f"https://api.github.com/orgs/{self.org_name}/teams/{team_slug}/repos"
        
        repos = []
        page = 1
        
        while True:
            params = {'page': page, 'per_page': 100}
            response = self.make_api_request("GET", url, params=params)
            if response.status_code != 200:
                logger.warning(f"Failed to fetch repos for team {team_slug}: {response.status_code}")
                break
            
            page_repos = response.json()
            if not page_repos:
                break
            
            repos.extend(page_repos)
            page += 1
        
        logger.info(f"Found {len(repos)} repositories for team {team_slug}")
        return repos
    
    def get_team_members(self, team_slug):
        """Fetch ONLY direct members of a specific team (excluding inherited members)."""
        logger.info(f"Fetching DIRECT members only for team: {team_slug}")
        
        # Get team info first
        team_url = f"https://api.github.com/orgs/{self.org_name}/teams/{team_slug}"
        team_response = self.make_api_request("GET", team_url)
        
        if team_response.status_code != 200:
            logger.warning(f"Failed to get team info for {team_slug}: {team_response.status_code}")
            return []
        
        team_info = team_response.json()
        has_parent = team_info.get('parent') is not None
        parent_slug = team_info.get('parent', {}).get('slug') if has_parent else None
        
        logger.info(f"Team '{team_slug}' - ID: {team_info['id']}, Has parent: {has_parent}")
        if has_parent:
            logger.info(f"Parent team: {parent_slug}")
        
        # Get all organization members first to iterate through
        org_members_url = f"https://api.github.com/orgs/{self.org_name}/members"
        org_members = []
        page = 1
        
        while True:            
            params = {'page': page, 'per_page': 100}
            response = self.make_api_request("GET", org_members_url, params=params)
            if response.status_code != 200:
                logger.warning(f"Failed to fetch org members: {response.status_code}")
                break
            page_members = response.json()
            if not page_members:
                break
            org_members.extend(page_members)
            page += 1
        
        logger.info(f"Found {len(org_members)} total organization members")
        
        # Check each member for DIRECT membership in this specific team
        direct_members = []
        
        # Now check for direct membership in current team
        for member in org_members:
            username = member['login']
            membership_url = f"https://api.github.com/orgs/{self.org_name}/teams/{team_slug}/memberships/{username}"
            membership_response = self.make_api_request("GET", membership_url)
            
            if membership_response.status_code == 200:
                membership_data = membership_response.json()
                if membership_data.get('state') == 'active':
                    # For child teams: include users who are directly added to the child team
                    if has_parent:
                        # This is a child team - include all active members
                        # Users in child teams should be included regardless of parent membership
                        member_with_role = {
                            'user': member,
                            'role': membership_data.get('role', 'member')
                        }
                        direct_members.append(member_with_role)
                        logger.info(f"[OK] Member of child team: {username} (role: {membership_data.get('role', 'member')})")
                    else:
                        # This is a parent team or standalone team
                        # Need to check if this user is directly in parent or just inherited from child
                        is_direct_parent_member = True
                        
                        # Check if this user is in any child teams of this parent
                        child_teams_url = f"https://api.github.com/orgs/{self.org_name}/teams"
                        child_response = self.make_api_request("GET", child_teams_url)
                        
                        if child_response.status_code == 200:
                            try:
                                all_teams = child_response.json()
                            except (ValueError, TypeError) as e:
                                logger.warning(f"Failed to parse teams JSON response: {e}")
                                all_teams = []
                            
                            # Filter child teams of this parent
                            child_teams = []
                            if all_teams:
                                for team in all_teams:
                                    if team and isinstance(team, dict):
                                        parent = team.get('parent')
                                        if parent and isinstance(parent, dict) and parent.get('slug') == team_slug:
                                            child_teams.append(team)
                            
                            # Check if user is directly in any child teams
                            for child_team in child_teams:
                                child_slug = child_team['slug']
                                child_membership_url = f"https://api.github.com/orgs/{self.org_name}/teams/{child_slug}/memberships/{username}"
                                child_check = self.make_api_request("GET", child_membership_url)
                                
                                if child_check.status_code == 200:
                                    child_membership = child_check.json()
                                    if child_membership.get('state') == 'active':
                                        # User is in child team - they're appearing in parent due to inheritance
                                        # Check if they're ALSO directly in parent by using the role
                                        # If role is 'member' and they're in child, they're likely just inherited
                                        parent_role = membership_data.get('role', 'member')
                                        
                                        # Conservative approach: if user is in child team, exclude from parent
                                        # unless they have maintainer/admin role in parent (indicating direct addition)
                                        if parent_role == 'member':
                                            is_direct_parent_member = False
                                            logger.info(f"[EXCLUDE] User {username} excluded from parent team (member of child team {child_slug})")
                                            break
                                        else:
                                            logger.info(f"[OK] User {username} kept in parent team (has {parent_role} role despite being in child team {child_slug})")
                        
                        if is_direct_parent_member:
                            member_with_role = {
                                'user': member,
                                'role': membership_data.get('role', 'member')
                            }
                            direct_members.append(member_with_role)
                            logger.info(f"[OK] Direct member of parent team: {username} (role: {membership_data.get('role', 'member')})")
                        else:
                            logger.info(f"[EXCLUDE] User {username} excluded from parent team (inherited from child team)")
        
        member_logins = [member_data['user']['login'] for member_data in direct_members]
        logger.info(f"Final result - {len(direct_members)} DIRECT members for team {team_slug}: {member_logins}")
        return direct_members
    
    def fetch_team_details(self):
        """Fetch essential information for recreating teams in target organization."""
        teams = self.get_teams()
        team_recreation_data = []
        
        for team in teams:
            team_name = team['name']
            team_slug = team['slug']
            team_description = team.get('description', '')
            team_privacy = team.get('privacy', 'closed')  # closed, secret
            team_parent = team.get('parent', {}).get('name', '') if team.get('parent') else ''
            
            logger.info(f"Processing team: {team_name}")
            
            # Get members for this team
            members = self.get_team_members(team_slug)
            member_data = [(member_info['user']['login'], member_info['role']) for member_info in members]
            
            # Debug: Log team details
            logger.info(f"Team '{team_name}' ({team_slug}) - Privacy: {team_privacy}, Parent: {team_parent}")
            logger.info(f"Team '{team_name}' members: {member_data}")
            
            # Get repositories for this team
            repos = self.get_team_repos(team_slug)
            
            if repos:
                for repo in repos:
                    # Determine the permission level (GitHub API returns granular permissions)
                    permissions = repo.get('permissions', {})
                    permission_level = 'pull'  # Default
                    
                    if permissions.get('admin'):
                        permission_level = 'admin'
                    elif permissions.get('maintain'):
                        permission_level = 'maintain'
                    elif permissions.get('push'):
                        permission_level = 'push'
                    elif permissions.get('triage'):
                        permission_level = 'triage'
                    
                    # Create a row for each member-repo combination
                    if member_data:
                        for member_username, member_role in member_data:
                            team_recreation_data.append({
                                'team_name': team_name,
                                'team_slug': team_slug,
                                'team_description': team_description,
                                'team_privacy': team_privacy,
                                'parent_team': team_parent,
                                'member': member_username,
                                'member_role': member_role,
                                'repo_name': repo['name'],
                                'repo_permission': permission_level
                            })
                    else:
                        # Team has repos but no members
                        team_recreation_data.append({
                            'team_name': team_name,
                            'team_slug': team_slug,
                            'team_description': team_description,
                            'team_privacy': team_privacy,
                            'parent_team': team_parent,
                            'member': '',
                            'member_role': '',
                            'repo_name': repo['name'],
                            'repo_permission': permission_level
                        })
            else:
                # Team with no repositories
                if member_data:
                    for member_username, member_role in member_data:
                        team_recreation_data.append({
                            'team_name': team_name,
                            'team_slug': team_slug,
                            'team_description': team_description,
                            'team_privacy': team_privacy,
                            'parent_team': team_parent,
                            'member': member_username,
                            'member_role': member_role,
                            'repo_name': '',
                            'repo_permission': ''
                        })
                else:
                    # Team with no repos and no members
                    team_recreation_data.append({
                        'team_name': team_name,
                        'team_slug': team_slug,
                        'team_description': team_description,
                        'team_privacy': team_privacy,
                        'parent_team': team_parent,
                        'member': '',
                        'member_role': '',
                        'repo_name': '',
                        'repo_permission': ''
                    })
        
        return team_recreation_data
    
    def save_to_csv(self, team_details, filename=None):
        """Save team details to a CSV file."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"github_teams.csv"
        
        logger.info(f"Saving team details to CSV file: {filename}")
        
        fieldnames = [
            'team_name', 'team_slug', 'team_description', 'team_privacy',
            'parent_team', 'member', 'member_role', 'repo_name', 'repo_permission'
        ]
        
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(team_details)
            
            logger.info(f"Successfully saved {len(team_details)} records to {filename}")
            return filename
        except Exception as e:
            logger.error(f"Failed to save CSV file: {str(e)}")
            raise

    def estimate_api_calls(self):
        """Estimate the total number of API calls needed for the operation."""
        logger.info("Estimating API calls needed...")
        
        # Get basic team count first
        teams = self.get_teams()
        team_count = len(teams)
        
        # Get organization member count
        org_members_url = f"https://api.github.com/orgs/{self.org_name}/members"
        response = self.make_api_request("GET", org_members_url, params={'per_page': 1})
        
        if response.status_code == 200:
            # Get total count from Link header if available
            link_header = response.headers.get('Link', '')
            if 'rel="last"' in link_header:
                import re
                last_page_match = re.search(r'page=(\d+).*rel="last"', link_header)
                if last_page_match:
                    estimated_members = int(last_page_match.group(1)) * 100
                else:
                    estimated_members = 100  # Conservative estimate
            else:
                estimated_members = len(response.json())
        else:
            estimated_members = 100  # Conservative estimate
        
        # Estimate API calls:
        # 1. Get teams: ~1-5 calls (depends on team count)
        # 2. Get team info: 1 call per team
        # 3. Get team repos: 1 call per team (minimum)
        # 4. Get org members: ~1-10 calls (depends on member count)
        # 5. Check team membership: 1 call per member per team
        # 6. Parent team checks: additional calls for child teams
        
        basic_calls = (team_count // 100) + 1  # Get teams
        basic_calls += team_count  # Get team info
        basic_calls += team_count  # Get team repos
        basic_calls += (estimated_members // 100) + 1  # Get org members
        membership_calls = team_count * estimated_members  # Check memberships
        
        # Add overhead for parent/child relationships (conservative estimate)
        overhead_calls = team_count * 50  # Additional calls for hierarchy checks
        
        total_estimated = basic_calls + membership_calls + overhead_calls
        
        logger.info(f"Estimation: {team_count} teams, ~{estimated_members} members")
        logger.info(f"Estimated API calls: {total_estimated:,}")
        logger.info(f"Estimated time: {(total_estimated * self.rate_limit_delay) / 60:.1f} minutes")
        
        return total_estimated

def main():
    """Main function to execute the team fetching process."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Fetch GitHub team details and save to CSV")
    parser.add_argument('--rate-limit-delay', type=float, default=0.5, 
                       help="Delay between API requests in seconds (default: 0.5)")
    parser.add_argument('--csv-file', type=str, default='github_teams.csv',
                       help="Output CSV file name (default: github_teams.csv)")
    parser.add_argument('--org', type=str, 
                       help="GitHub organization name (overrides GITHUB_ORG env var)")
    parser.add_argument('--estimate-only', action='store_true',
                       help="Only estimate API calls needed, don't fetch data")
    args = parser.parse_args()
    
    # Override environment variables if provided
    if args.org:
        os.environ['GITHUB_ORG'] = args.org
    
    try:
        logger.info("Starting GitHub team details fetch process...")
        
        # Initialize the fetcher
        fetcher = GitHubTeamFetcher()
        
        # Set custom rate limit delay if provided
        if args.rate_limit_delay != 0.5:
            fetcher.rate_limit_delay = args.rate_limit_delay
            logger.info(f"Using custom rate limit delay: {args.rate_limit_delay} seconds")
        
        # Check rate limit status before starting
        logger.info("Checking rate limit status...")
        remaining, limit, reset_time = fetcher.check_rate_limit_status()
        
        if remaining is not None and remaining < 100:
            logger.warning(f"Low rate limit remaining ({remaining}). Consider waiting or increasing delay.")
        
        # Estimate API calls needed
        estimated_calls = fetcher.estimate_api_calls()
        
        if args.estimate_only:
            logger.info("Estimation complete. Exiting without fetching data.")
            return
            
        if remaining is not None and estimated_calls > remaining:
            logger.warning(f"Estimated calls ({estimated_calls:,}) exceed remaining limit ({remaining})")
            logger.warning("Consider increasing --rate-limit-delay or waiting for rate limit reset")
            logger.info("Proceeding with execution - rate limiting will handle any issues automatically")
        
        # Fetch team details
        team_details = fetcher.fetch_team_details()
        
        if not team_details:
            logger.warning("No team details found")
            return
        
        # Save to CSV
        filename = fetcher.save_to_csv(team_details, args.csv_file)
        
        logger.info(f"Process completed successfully. CSV file saved as: {filename}")
        logger.info(f"Total records processed: {len(team_details)}")
        
        # Check rate limit status after completion
        logger.info("Final rate limit status:")
        fetcher.check_rate_limit_status()
        
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        raise

if __name__ == "__main__":
    main()