# GitHub Actions Variables Migration Tool

A comprehensive Python script for migrating GitHub Actions variables between organizations. This tool handles both organization-level and repository-level variables with full support for visibility settings and repository access configurations.

## Table of Contents

1. [Overview](#1-overview)
2. [Features](#2-features)
3. [Prerequisites](#3-prerequisites)
4. [Installation](#4-installation)
5. [Configuration](#5-configuration)
6. [Usage](#6-usage)
7. [Variable Types](#7-variable-types)
8. [Migration Process](#8-migration-process)
9. [Output Files](#9-output-files)
10. [Troubleshooting](#10-troubleshooting)
11. [Contributing](#11-contributing)

## 1. Overview

The GitHub Actions Variables Migration Tool automates the transfer of GitHub Actions variables from source to target organizations. Unlike secrets, variables values can be retrieved and migrated directly, making this tool capable of complete end-to-end variable migration with all settings preserved.

## 2. Features

- **Complete Variable Migration**: Export and recreate all variable configurations and values
- **Organization and Repository Variables**: Handle both organization-level and repository-level variables
- **Full Visibility Support**: Maintain all visibility settings (`all`, `private`, `selected`)
- **Repository Access Mapping**: Preserve repository access for `selected` visibility variables
- **CSV Export/Import**: Export variables for review and backup purposes
- **Value Preservation**: Migrate actual variable values (unlike secrets)
- **Rate Limit Management**: Built-in GitHub API rate limiting with automatic backoff
- **Comprehensive Logging**: Detailed audit trails for compliance and debugging
- **Error Recovery**: Robust error handling with retry mechanisms
- **Duplicate Handling**: Smart handling of existing variables

## 3. Prerequisites

### 3.1. System Requirements

- Python 3.7 or higher
- Internet connection for GitHub API access

### 3.2. GitHub Access Requirements

- GitHub Personal Access Token (PAT) for source organization
- GitHub Personal Access Token (PAT) for target organization
- Appropriate permissions for variable management

### 3.3. Required GitHub PAT Scopes

**Source Organization Token**:
- `repo` - Repository access
- `admin:org` - Organization administration
- `read:org` - Read organization data

**Target Organization Token**:
- `repo` - Repository access
- `admin:org` - Organization administration
- `write:org` - Write organization data

## 4. Installation

### 4.1. Dependencies

Install required packages:

```bash
pip install -r requirements.txt
```

Required packages:
```
requests>=2.28.0
python-dotenv>=0.19.0
pandas>=1.5.0
openpyxl>=3.0.10
```

## 5. Configuration

### 5.1. Environment Variables

Create a `.env` file in the script directory:

```env
# GitHub Authentication (Required)
SOURCE_GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
TARGET_GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx

# Organizations (Required)
SOURCE_ORGANIZATION=source-organization-name
TARGET_ORGANIZATION=target-organization-name
```

**Note**: The script automatically generates output files:
- `github_variables_export.csv` for backup and review
- `github_variable_migration.log` for detailed operation logs

# Optional: Rate Limiting
RATE_LIMIT_DELAY=1
MAX_RETRIES=3
```

## 6. Usage

### 6.1. Basic Migration

Run the complete migration process:

```bash
python github_variables_migration.py
```

The script automatically:
1. Fetches all variables from the source organization (both org-level and repository-level)
2. Migrates them to the target organization with actual values preserved
3. Handles all visibility settings (`all`, `private`, `selected`)
4. Maps repository access for `selected` visibility variables
5. Exports a backup CSV file with all variable data
6. Provides detailed logging of the entire process

**Note**: The script reads all configuration from the `.env` file and doesn't accept command-line arguments.

1. **Validation**: Checks that all required environment variables are set
2. **Fetching**: Retrieves all organization and repository-level variables from the source organization
3. **Visibility Detection**: For organization variables, detects visibility settings and selected repositories
4. **Export**: Saves all variables to `github_variables_export.csv` for backup
5. **Repository Mapping**: Maps source repository names to target repository IDs
6. **Migration**: Creates/updates variables in the target organization with proper visibility
7. **Logging**: Provides detailed logs of the entire process

## Output Files

The script generates the following files:

- **CSV Export**: `github_variables_export.csv`
  - Contains all variables with their scope, repository, name, value, visibility, and timestamps
  
- **Log File**: `github_variable_migration.log`
  - Detailed logs of the migration process

## CSV Format

The exported CSV contains the following columns:

| Column | Description |
|--------|-------------|
| scope | `organization` or `repository` |
| repository | Repository name (empty for org-level variables) |
| name | Variable name |
| value | Variable value |
| visibility | Visibility setting for org variables (`all`, `private`, `selected`) |
| selected_repositories | Comma-separated list of repository names (for `selected` visibility) |
| created_at | When the variable was created |
| updated_at | When the variable was last updated |

## Organization Variable Visibility Support

The script fully supports GitHub organization variable visibility settings:

### Visibility Types
- **`all`** - Variable is available to all repositories in the organization
- **`private`** - Variable is only available to private repositories  
- **`selected`** - Variable is only available to specific selected repositories

### How Repository Visibility Works

1. **Detection**: The script uses [`get_organization_variable_details`](github_variables_migration.py) to detect visibility settings
2. **Repository Mapping**: For `selected` visibility, [`get_variable_selected_repositories`](github_variables_migration.py) fetches the list of repositories
3. **Target Mapping**: [`build_target_repo_mapping`](github_variables_migration.py) maps source repository names to target repository IDs
4. **Recreation**: Variables are recreated with the same visibility settings using [`create_organization_variable`](github_variables_migration.py)

### Repository Mapping Features

- **Automatic Mapping**: [`build_target_repo_mapping`](github_variables_migration.py) builds a cache of target organization repositories
- **Missing Repository Handling**: If repositories don't exist in target org, logs warnings and falls back to `private` visibility
- **Efficient Lookup**: Repository mapping is cached for better performance

## Rate Limiting

The script automatically handles GitHub API rate limits:

- **Monitoring**: [`_handle_rate_limit`](github_variables_migration.py) monitors remaining API calls
- **Automatic Waiting**: Waits when rate limit is approached (< 10 calls remaining)
- **Retry Strategy**: Implements exponential backoff for HTTP errors (429, 500-504)
- **Detailed Logging**: Logs rate limit status and wait times

## Error Handling

- **Configuration Validation**: [`_validate_config`](github_variables_migration.py) checks required environment variables
- **Graceful API Errors**: Handles API errors and continues migration
- **Automatic Updates**: If variable exists (409 error), automatically updates it
- **Detailed Error Logging**: Provides specific error messages from GitHub API
- **Migration Summary**: Returns counts of successful, failed, and skipped operations

## Security Notes

- Keep your `.env` file secure and never commit it to version control
- Use tokens with minimal required permissions
- Consider using GitHub Apps for better security in production environments
- The script logs variable names but values are only stored in the CSV export
- Variable values are transmitted securely via GitHub's HTTPS API

## Troubleshooting

### Common Issues

1. **"Missing required environment variables"**
   - Check that your `.env` file exists and contains all required variables
   - Ensure variable names match exactly: `SOURCE_PAT`, `TARGET_PAT`, `SOURCE_ORG`, `TARGET_ORG`
   
2. **"403 Forbidden" errors**
   - Verify your PAT has the required permissions (`repo`, `admin:org`)
   - Check that the organizations exist and you have access
   
3. **"Rate limit exceeded"**
   - The script handles this automatically with [`_handle_rate_limit`](github_variables_migration.py)
   - Large organizations may take longer due to automatic waiting
   
4. **"Repository not found" warnings**
   - Some repositories may be private, archived, or renamed
   - Check the logs for specific repository names
   - Variables will fallback to `private` visibility if no valid repositories found

### Debug Mode

To enable more detailed logging, modify the logging level in [`_setup_logging`](github_variables_migration.py):

```python
logging.basicConfig(level=logging.DEBUG, ...)
```

## Script Architecture

### Key Classes and Methods

- **[`GitHubVariablesMigrator`](github_variables_migration.py)**: Main class handling the migration process
- **[`get_organization_variables`](github_variables_migration.py)**: Fetches org-level variables with visibility
- **[`get_repository_variables`](github_variables_migration.py)**: Fetches repo-level variables
- **[`create_organization_variable`](github_variables_migration.py)**: Creates org variables with visibility settings
- **[`create_repository_variable`](github_variables_migration.py)**: Creates repo-level variables
- **[`_get_paginated_data`](github_variables_migration.py)**: Handles GitHub API pagination
- **[`run_migration`](github_variables_migration.py)**: Main migration workflow

### HTTP Session Management

- **Retry Strategy**: 3 retries with exponential backoff
- **Custom Headers**: Proper GitHub API headers with User-Agent
- **Authentication**: Token-based authentication for both source and target

## Limitations

- Repository-level variables require the repository to exist in the target organization
- Encrypted secrets are not supported (use GitHub's secrets API separately)
- Variables are migrated with their current values (no encryption in transit beyond HTTPS)
- Large organizations may take significant time due to rate limiting

## Example Migration Flow

1. **Initialization**: Load environment variables and setup sessions
2. **Fetch**: Get all variables from source organization
3. **Export**: Save to [`github_variables_export.csv`](github_variables_export.csv)
4. **Map**: Build repository mapping for target organization
5. **Migrate**: Create/update variables in target organization
6. **Summary**: Log final counts and completion status

Based on your [`github_variables_export.csv`](github_variables_export.csv), the script successfully handles:
- Organization variables with `selected` visibility
- Repository variables from multiple repositories
- Proper CSV formatting with all required columns

## Contributing

Feel free to submit issues and enhancement requests! The script is designed to be extensible and maintainable.

## Recent Updates

- ✅ Full organization variable visibility support (`all`, `private`, `selected`)
- ✅ Repository mapping and automatic fallback handling
- ✅ Enhanced error handling with automatic updates for existing variables
- ✅ Comprehensive CSV export with visibility information
- ✅ Improved logging and