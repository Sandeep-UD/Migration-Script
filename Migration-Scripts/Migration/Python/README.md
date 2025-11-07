# GitHub Repository Migration Tool

This tool automates the process of migrating repositories between GitHub organizations using the GitHub Enterprise Importer (GEI).

## Overview

The tool consists of two main components:
- `migrate_github_repos.py`: The main Python script that handles the migration process
- `repos.csv`: A CSV file containing the list of repositories to migrate

## Prerequisites

- Python 3.x
- GitHub CLI (gh) with GitHub Enterprise Importer extension
- Required Python packages:
  - python-dotenv
- GitHub Personal Access Tokens (PATs) with appropriate permissions

## Environment Variables

The following environment variables must be set:
- `GH_SOURCE_PAT`: Personal Access Token for the source GitHub organization
- `GH_PAT`: Personal Access Token for the destination GitHub organization
- `SOURCE`: Name of the source GitHub organization
- `DESTINATION`: Name of the destination GitHub organization

## CSV File Format

The `repos.csv` file should follow this format:
```csv
CURRENT-NAME,NEW-NAME
repo1,repo1
repo2,repo2
```
- `CURRENT-NAME`: The name of the repository in the source organization
- `NEW-NAME`: The desired name for the repository in the destination organization

## Features

- Automated repository migration using GitHub Enterprise Importer
- Detailed logging of migration process
- CSV output with migration status and timing information
- Error handling and validation of environment variables
- Support for custom repository naming in the destination organization

## Usage

1. Set up the required environment variables in a `.env` file or your environment
2. Prepare the `repos.csv` file with the list of repositories to migrate
3. Run the script:
   ```powershell
   python migrate_github_repos.py
   ```

## Output

The script generates:
- Detailed logs of the migration process
- CSV output with migration results including:
  - Source and target repository information
  - Migration status
  - Start and end times
  - Time taken for migration

## Error Handling

The script includes error handling for:
- Missing environment variables
- Migration failures
- Invalid repository names
- GitHub API issues

## License

This project is intended for internal use. Please ensure you have the necessary permissions before migrating repositories.
