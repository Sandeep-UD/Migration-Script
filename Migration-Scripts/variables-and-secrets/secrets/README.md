# GitHub Actions Secrets Migration Tool

A comprehensive Python script for migrating GitHub Actions secrets between organizations. This tool handles both organization-level and repository-level secrets, providing secure migration with proper encryption and comprehensive audit trails.

## Table of Contents

1. [Overview](#1-overview)
2. [Features](#2-features)
3. [Prerequisites](#3-prerequisites)
4. [Installation](#4-installation)
5. [Configuration](#5-configuration)
6. [Usage](#6-usage)
7. [Security Considerations](#7-security-considerations)
8. [Migration Process](#8-migration-process)
9. [Output Files](#9-output-files)
10. [Troubleshooting](#10-troubleshooting)
11. [Contributing](#11-contributing)

## 1. Overview

The GitHub Actions Secrets Migration Tool automates the transfer of GitHub Actions secrets from source to target organizations. Due to GitHub's security model, secret values cannot be retrieved via API, so this tool creates the secret structure with placeholder values and provides workflows for manual value updates.

## 2. Features

- **Complete Secret Structure Migration**: Export and recreate all secret configurations
- **Organization and Repository Secrets**: Handle both organization-level and repository-level secrets
- **Secure Placeholder Creation**: Create secrets with secure placeholder values
- **Visibility Settings Preservation**: Maintain secret visibility and repository access
- **CSV Export/Import**: Support for manual secret value management
- **Proper Encryption**: Use GitHub's public key encryption for secure secret creation
- **Rate Limit Management**: Built-in GitHub API rate limiting with automatic backoff
- **Comprehensive Logging**: Detailed audit trails for compliance and debugging
- **Error Recovery**: Robust error handling with retry mechanisms
- **Duplicate Prevention**: Skip existing secrets to prevent overwrites

## 3. Prerequisites

### 3.1. System Requirements

- Python 3.7 or higher
- Internet connection for GitHub API access

### 3.2. GitHub Access Requirements

- GitHub Personal Access Token (PAT) for source organization
- GitHub Personal Access Token (PAT) for target organization
- Appropriate permissions for secret management

### 3.3. Required GitHub PAT Scopes

**Source Organization Token**:
- `repo` - Repository access
- `admin:org` - Organization administration
- `read:org` - Read organization data
- `read:repo_security` - Read repository security settings

**Target Organization Token**:
- `repo` - Repository access
- `admin:org` - Organization administration
- `write:org` - Write organization data
- `write:repo_security` - Write repository security settings
  - **Target PAT**: `repo`, `admin:org`, `write:org`, `write:repo_security`

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment variables:**
   Create a `.env` file in the same directory:
   ```env
   SOURCE_GITHUB_TOKEN=your_source_github_token_here
   TARGET_GITHUB_TOKEN=your_target_github_token_here
   SOURCE_ORGANIZATION=your_source_organization
   TARGET_ORGANIZATION=your_target_organization
   ```

## Usage

### Default Migration (Complete Workflow)

The script runs a complete migration by default:

```bash
python github_secrets_migration.py
```

This executes the complete migration process which:
1. Fetches all secret metadata from source organization (both org-level and repo-level)
2. Creates all secrets in target organization with secure placeholder values
3. Generates `github_secrets_export.csv` for reference and manual value updates
4. Skips secrets that already exist in the target organization
5. Provides detailed logging to `github_secrets_migration.log`

**Important**: Secret values cannot be retrieved from GitHub API for security reasons, so placeholder values are used. You must manually update critical secret values in the GitHub UI after migration.
```python
def main():
    migrator = GitHubSecretsMigrator()
    migrator.run_export_only()
    return 0
```

#### Migrate from CSV Mode
```python
def main():
    migrator = GitHubSecretsMigrator()
    migrator.run_migration_from_csv("github_secrets_export.csv", create_placeholder=True)
    return 0
```

#### Migrate Only with Actual Values
```python
def main():
    migrator = GitHubSecretsMigrator()
    migrator.run_migration_from_csv("my_secrets_with_values.csv", create_placeholder=False)
    return 0
```

## Available Methods

The [`GitHubSecretsMigrator`](github_secrets_migration.py) class provides these main methods:

- [`run_complete_migration()`](github_secrets_migration.py): Export + migrate with placeholders (default)
- [`run_export_only()`](github_secrets_migration.py): Only export secret structure to CSV
- [`run_migration_from_csv(csv_filename, create_placeholder=True)`](github_secrets_migration.py): Migrate from prepared CSV file

## Examples

### Standard usage (default):
```bash
python github_secrets_migration.py
```

### With setup:
```bash
# First time setup
python setup.py

# Run migration
python github_secrets_migration.py
```

## Workflow Recommendations

### Default Workflow (Recommended)
1. **Setup**: `python setup.py` (one time only)
2. **Configure**: Edit `.env` file with your tokens and organizations
3. **Migrate**: `python github_secrets_migration.py`
4. **Update Values**: Use GitHub UI to set actual secret values for placeholder secrets
5. **Verify**: Test your workflows to ensure secrets work correctly

### Advanced Workflow (Manual Value Entry)
1. **Export**: Modify script to call `run_export_only()`
2. **Edit CSV**: Manually enter actual secret values in the generated CSV
3. **Migrate**: Modify script to call `run_migration_from_csv()` with `create_placeholder=False`

## CSV File Format

The CSV file generated by [`export_secrets_to_csv`](github_secrets_migration.py) contains:

| Column | Description |
|--------|-------------|
| `scope` | Either "organization" or "repository" |
| `repository` | Repository name (only for repository-scoped secrets) |
| `name` | Secret name |
| `value` | Secret value (`[ENCRYPTED_SECRET_VALUE]` for placeholders) |
| `visibility` | For org secrets: "all", "private", or "selected" |
| `selected_repositories` | Comma-separated list of repository names (for selected visibility) |
| `created_at` | Creation timestamp (informational) |
| `updated_at` | Last update timestamp (informational) |

## Security Features

1. **Proper Encryption**: Uses GitHub's public key API and NaCl encryption via [`encrypt_secret`](github_secrets_migration.py)
2. **Placeholder Support**: Creates secrets with safe placeholder values "PLACEHOLDER_VALUE_SET_MANUALLY"
3. **No Value Logging**: Secret values are never logged or printed
4. **Secure Transport**: All API communications use HTTPS
5. **Token Validation**: Validates required environment variables via [`_validate_config`](github_secrets_migration.py)
6. **Existing Secret Detection**: Checks and skips existing secrets to prevent overwrites

## Error Handling

The script includes comprehensive error handling for:
- Missing or invalid authentication tokens
- Rate limiting (automatic backoff and retry via [`_handle_rate_limit`](github_secrets_migration.py))
- Network connectivity issues (retry strategy in [`_create_session`](github_secrets_migration.py))
- Invalid repository or organization names
- Missing target repositories
- Encryption failures

## Logging

All operations are logged via [`_setup_logging`](github_secrets_migration.py) to:
- Console output (INFO level and above)
- `github_secrets_migration.log` file (detailed logging)

Log entries include timestamps, operation details, and error information.

## Visibility Settings

### Organization Secrets
- **all**: Available to all repositories in the organization
- **private**: Available only to private repositories  
- **selected**: Available to specific repositories (handled by [`get_target_repository_ids`](github_secrets_migration.py))

### Repository Secrets
- No visibility setting (always scoped to the specific repository)

## How Placeholder Values Work

When using the default migration or `create_placeholder=True`:

1. **Placeholder Creation**: Secrets are created with the value "PLACEHOLDER_VALUE_SET_MANUALLY"
2. **Structure Preservation**: All metadata (names, visibility, repositories) is preserved
3. **Manual Update Required**: You must manually update the actual values via GitHub UI
4. **Security**: Placeholder values are clearly identifiable and don't expose sensitive data

## Key Classes and Methods

### Main Class
- [`GitHubSecretsMigrator`](github_secrets_migration.py): Main class handling all migration operations

### Core Methods
- [`fetch_all_secrets()`](github_secrets_migration.py): Retrieves all secrets from source organization
- [`get_organization_secrets()`](github_secrets_migration.py): Gets org-level secrets with visibility info
- [`get_repository_secrets()`](github_secrets_migration.py): Gets repo-level secrets
- [`create_organization_secret()`](github_secrets_migration.py): Creates org secrets with proper visibility
- [`create_repository_secret()`](github_secrets_migration.py): Creates repo secrets
- [`encrypt_secret()`](github_secrets_migration.py): Handles secret encryption using GitHub's public key

### Utility Methods
- [`_make_request()`](github_secrets_migration.py): HTTP requests with rate limit handling
- [`_get_paginated_data()`](github_secrets_migration.py): Handles GitHub API pagination
- [`build_target_repo_mapping()`](github_secrets_migration.py): Maps repository names to IDs

## Post-Migration Steps

After running the migration:

1. **Review Logs**: Check `github_secrets_migration.log` for any errors
2. **Verify Structure**: Confirm all secrets were created in target organization
3. **Update Values**: 
   - For placeholder secrets: Update via GitHub UI (Settings → Secrets and variables → Actions)
   - For actual value secrets: Verify they work correctly
4. **Test**: Run a test workflow to ensure secrets are accessible
5. **Cleanup**: Securely delete any CSV files containing actual secret values

## Troubleshooting

### Common Issues

1. **"No access to secrets"**: Ensure your PAT has the required `read:repo_security` and `write:repo_security` permissions

2. **"Repository not found"**: The target organization may not have a repository with the same name, or your PAT lacks access

3. **"Rate limit exceeded"**: The script automatically handles rate limiting via [`_handle_rate_limit`](github_secrets_migration.py)

4. **"Encryption failed"**: Ensure PyNaCl is properly installed: `pip install PyNaCl`

5. **"Placeholder values in production"**: Remember to update placeholder secrets with actual values after migration

6. **"Secret already exists"**: The script skips existing secrets - check logs for details

### Debug Mode

For detailed debugging, modify the logging level in [`_setup_logging`](github_secrets_migration.py):
```python
logging.basicConfig(level=logging.DEBUG, ...)
```

## Security Best Practices

1. **Secure Storage**: Never commit `.env` files or CSV files with actual secret values to version control
2. **Access Control**: Use PATs with minimum required permissions
3. **Cleanup**: Delete CSV files with actual secret values after migration
4. **Audit**: Review the export CSV before migration to ensure only intended secrets are migrated
5. **Testing**: Test with a small subset of secrets first
6. **Placeholder Management**: Regularly audit and update placeholder secrets
7. **Documentation**: Keep track of which secrets need manual value updates

## Limitations

1. **Secret Values**: Cannot retrieve existing secret values via GitHub API (security feature)
2. **Repository Mapping**: Target repositories must exist with the same names
3. **Environment Variables**: Cannot migrate repository environment-specific secrets
4. **Overwrite Protection**: Existing secrets are skipped to prevent accidental overwrites

## Dependencies

From [requirements.txt](requirements.txt):
- `requests==2.31.0`: HTTP library for GitHub API calls
- `urllib3==2.0.7`: HTTP client library
- `python-dotenv==1.0.0`: Environment variable management
- `PyNaCl==1.5.0`: Cryptography library for secret encryption

## License

This tool is provided as-is for educational and migration purposes. Please ensure compliance with your organization's security policies before use.