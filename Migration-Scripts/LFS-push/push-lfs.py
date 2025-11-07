import os
import csv
import subprocess
import sys
import shutil
from pathlib import Path

def load_env_variables():
    """Load environment variables from .env file"""
    env_file = Path('.env')
    if not env_file.exists():
        print("Error: .env file not found.", file=sys.stderr)
        sys.exit(1)
    
    with open(env_file, 'r') as file:
        for line in file:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()

def run_command(command, log_file, cwd=None):
    """Run a command and log the output"""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd
        )
        
        # Log both stdout and stderr
        output = result.stdout + result.stderr
        if output:
            print(output.strip())
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(output + '\n')
        
        return result.returncode
    except Exception as e:
        error_msg = f"Error running command '{command}': {str(e)}"
        print(error_msg, file=sys.stderr)
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(error_msg + '\n')
        return 1

def cleanup_repo_directory(repo_path):
    """Clean up repository directory if it exists"""
    if repo_path.exists():
        try:
            # Try to remove read-only attributes on Windows
            if os.name == 'nt':  # Windows
                os.system(f'attrib -R "{repo_path}" /S /D')
            shutil.rmtree(repo_path)
            print(f"Cleaned up existing directory: {repo_path}")
        except Exception as e:
            print(f"Warning: Could not clean up directory {repo_path}: {e}")

def main():
    # Load environment variables from .env file
    load_env_variables()
    
    # Read Personal Access Tokens
    source_token = os.environ.get("Soucre-Access-Token")
    target_token = os.environ.get("Target-Access-Token")
    
    if not source_token or not target_token:
        print("Error: Missing source or target access token.", file=sys.stderr)
        sys.exit(1)
    
    # Read CSV file
    csv_file = "repos.csv"
    if not Path(csv_file).exists():
        print(f"Error: CSV file '{csv_file}' not found.", file=sys.stderr)
        sys.exit(1)
    
    # Create a log file
    log_file = "migration_log.txt"
    if Path(log_file).exists():
        Path(log_file).unlink()
    
    # Read repositories from CSV
    with open(csv_file, 'r', newline='', encoding='utf-8') as file:
        csv_reader = csv.DictReader(file)
        repos = list(csv_reader)
    
    for repo in repos:
        source_org = repo["Source-Org"]
        target_org = repo["Target-Org"]
        repo_name = repo["reponame"]
        
        print(f"\033[96mProcessing repository: {repo_name}\033[0m")
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"Processing repository: {repo_name}\n")
        
        repo_path = Path(repo_name)
        
        # Clean up any existing directory first
        cleanup_repo_directory(repo_path)
        
        # Clone the repository with additional options
        clone_url = f"https://{source_token}@github.com/{source_org}/{repo_name}.git"
        print(f"Cloning repository: {clone_url}")
        
        # Try cloning with additional git config options
        clone_command = f'git -c core.longpaths=true clone "{clone_url}"'
        if run_command(clone_command, log_file) != 0:
            print(f"\033[91mError cloning repository: {repo_name}\033[0m", file=sys.stderr)
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"Error cloning repository: {repo_name}\n")
            
            # Try alternative: clone to a different temp directory
            temp_name = f"temp_{repo_name}"
            temp_path = Path(temp_name)
            cleanup_repo_directory(temp_path)
            
            print(f"Retrying with temporary directory: {temp_name}")
            alt_clone_command = f'git -c core.longpaths=true clone "{clone_url}" "{temp_name}"'
            if run_command(alt_clone_command, log_file) != 0:
                print(f"\033[91mFailed to clone repository with alternative method: {repo_name}\033[0m", file=sys.stderr)
                cleanup_repo_directory(temp_path)
                continue
            else:
                # Rename temp directory to final name
                try:
                    temp_path.rename(repo_path)
                except Exception as e:
                    print(f"Error renaming directory: {e}")
                    cleanup_repo_directory(temp_path)
                    continue
        
        # Verify the repository directory exists and is accessible
        if not repo_path.exists() or not (repo_path / '.git').exists():
            print(f"\033[91mRepository directory not properly created: {repo_name}\033[0m", file=sys.stderr)
            continue
        
        try:
            # Fetch all LFS objects
            print("Fetching LFS objects...")
            run_command("git lfs fetch --all", log_file, cwd=repo_path)
            run_command("git lfs ls-files", log_file, cwd=repo_path)
            
            # Add new remote for target organization
            target_url = f"https://{target_token}@github.com/{target_org}/{repo_name}.git"
            print(f"Adding remote: {target_url}")
            run_command(f'git remote add origin1 "{target_url}"', log_file, cwd=repo_path)
            
            # Push LFS files to new remote
            print("Pushing LFS files to target...")
            if run_command("git lfs push --all origin1", log_file, cwd=repo_path) != 0:
                print(f"\033[91mError pushing LFS files for repository: {repo_name}\033[0m", file=sys.stderr)
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"Error pushing LFS files for repository: {repo_name}\n")
            else:
                print(f"\033[92mSuccessfully migrated: {repo_name}\033[0m")
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"Successfully migrated: {repo_name}\n")
        
        except Exception as e:
            print(f"\033[91mError processing repository {repo_name}: {e}\033[0m", file=sys.stderr)
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"Error processing repository {repo_name}: {e}\n")
        
        finally:
            # Clean up the cloned repository to save space
            cleanup_repo_directory(repo_path)
    
    print(f"\033[93mMigration process completed. Check {log_file} for details.\033[0m")

if __name__ == "__main__":
    main()