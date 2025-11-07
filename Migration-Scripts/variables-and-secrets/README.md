# GitHub Variables and Secrets Migration

A comprehensive collection of tools for migrating GitHub Actions variables and secrets between organizations. This toolkit provides separate specialized tools for handling variables (which can be fully migrated) and secrets (which require special handling due to security constraints).

## Table of Contents

1. [Overview](#1-overview)
2. [Project Structure](#2-project-structure)
3. [Prerequisites](#3-prerequisites)
4. [Installation](#4-installation)
5. [Migration Tools](#5-migration-tools)
   - 5.1. [Variables Migration](#51-variables-migration)
   - 5.2. [Secrets Migration](#52-secrets-migration)
6. [Migration Strategy](#6-migration-strategy)
7. [Security Considerations](#7-security-considerations)
8. [Best Practices](#8-best-practices)
9. [Troubleshooting](#9-troubleshooting)
10. [Contributing](#10-contributing)

## 1. Overview

This collection provides specialized tools for migrating GitHub Actions variables and secrets between organizations. Due to the different security models of variables and secrets in GitHub, separate tools are provided to handle each type of configuration optimally.

### Key Differences

**Variables**:
- Values can be retrieved via API
- Complete end-to-end migration possible
- Values are visible in GitHub UI
- Used for non-sensitive configuration

**Secrets**:
- Values cannot be retrieved via API (security feature)
- Structure migration with placeholder values
- Values are encrypted and hidden
- Used for sensitive data (API keys, passwords)

## 2. Project Structure

```
variables-and-secrets/
├── README.md                    # This file
├── variables/                   # Variables migration tools
│   ├── README.md
│   ├── github_variables_migration.py
│   ├── github_variables_export.csv
│   ├── github_variable_migration.log
│   └── requirements.txt
└── secrets/                     # Secrets migration tools
    ├── README.md
    ├── github_secrets_migration.py
    ├── github_secrets_export.csv
    ├── github_secrets_migration.log
    └── requirements.txt
```

## 3. Prerequisites

### 3.1. System Requirements

- Python 3.7 or higher
- Internet connection for GitHub API access

### 3.2. GitHub Access Requirements

- GitHub Personal Access Tokens (PAT) for both source and target organizations
- Organization admin permissions or specific permissions as detailed below

### 3.3. Required GitHub PAT Scopes

**For Variables Migration**:
- `repo` - Repository access
- `admin:org` - Organization administration
- `read:org` / `write:org` - Organization data access

**For Secrets Migration**:
- `repo` - Repository access
- `admin:org` - Organization administration
- `read:org` / `write:org` - Organization data access
- `read:repo_security` / `write:repo_security` - Repository security settings

## 4. Installation

### 4.1. Install Dependencies

Each tool has its own requirements file:

```bash
# For variables migration
cd variables/
pip install -r requirements.txt

# For secrets migration
cd ../secrets/
pip install -r requirements.txt

# Or install all dependencies at once
find . -name "requirements.txt" -exec pip install -r {} \;
```

### 4.2. Configuration

Create `.env` files in each subdirectory:

```env
# GitHub Authentication
SOURCE_GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
TARGET_GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx

# Organizations
SOURCE_ORGANIZATION=source-organization-name
TARGET_ORGANIZATION=target-organization-name
```

## 5. Migration Tools

### 5.1. Variables Migration

**Location**: `variables/`

Handles GitHub Actions variables with complete value migration.

**Key Features**:
- Complete variable value migration
- Organization and repository level variables
- Visibility settings preservation (`all`, `private`, `selected`)
- Repository access mapping for selected visibility
- CSV export for backup and review

**Usage**:
```bash
cd variables/
python github_variables_migration.py
```

The script automatically:
- Fetches all variables from the source organization
- Migrates them to the target organization with actual values
- Exports a CSV file for backup and review
- Provides detailed logging

For detailed information, see [variables/README.md](variables/README.md).

### 5.2. Secrets Migration

**Location**: `secrets/`

Handles GitHub Actions secrets with structure migration and secure placeholder values.

**Key Features**:
- Secret structure migration (values cannot be retrieved due to security)
- Secure placeholder value creation
- Organization and repository level secrets
- Visibility settings preservation
- CSV export for manual value entry reference
- Proper encryption using GitHub's public key API

**Usage**:
```bash
cd secrets/
python github_secrets_migration.py
```

The script automatically:
- Fetches all secret metadata from the source organization
- Creates secrets in the target organization with placeholder values
- Exports a CSV file showing secret structure
- Requires manual value updates in GitHub UI after migration

For detailed information, see [secrets/README.md](secrets/README.md).

## 6. Migration Strategy

### 6.1. Recommended Migration Order

1. **Variables First**: Migrate variables completely using the variables tool
2. **Secrets Structure**: Migrate secret structure using the secrets tool
3. **Manual Secret Values**: Update secret values manually via GitHub UI or API

### 6.2. Planning Phase

**Inventory Current State**:

Both scripts run export and migration together automatically. The CSV files can be reviewed after running:
- `github_variables_export.csv` - shows all variables and their values
- `github_secrets_export.csv` - shows secret structure (no values for security)

**Review Exports**:
- Review `github_variables_export.csv` for variable configurations
- Review `github_secrets_export.csv` for secret structure planning
- Identify critical secrets that need immediate value updates

### 6.3. Migration Execution

**Phase 1 - Variables Migration**:
```bash
cd variables/
python github_variables_migration.py
```

**Phase 2 - Secrets Structure Migration**:
```bash
cd secrets/
python github_secrets_migration.py
```

**Phase 3 - Secret Values Update**:
- Use GitHub UI to update critical secret values
- Or use the CSV import feature for bulk updates

## 7. Security Considerations

### 7.1. Token Security

- **Principle of Least Privilege**: Use tokens with minimum required scopes
- **Token Rotation**: Rotate tokens after migration completion
- **Secure Storage**: Never commit `.env` files to version control
- **Access Auditing**: Review token access logs after migration

### 7.2. Secret Handling

- **Placeholder Values**: Secrets are created with secure placeholder values
- **Manual Updates Required**: Critical secrets need manual value updates
- **Value Verification**: Verify secret values after migration
- **Audit Trail**: Maintain records of which secrets were updated

### 7.3. Network Security

- **Encrypted Transmission**: All API communications use HTTPS
- **Rate Limiting**: Respect GitHub API rate limits
- **Error Handling**: Avoid logging sensitive information

## 8. Best Practices

### 8.1. Pre-Migration

1. **Backup**: Export current configurations for backup
2. **Documentation**: Document secret purposes and critical values
3. **Testing**: Test migration in non-production environment
4. **Team Coordination**: Coordinate with teams using the secrets/variables

### 8.2. During Migration

1. **Monitor Progress**: Watch logs for errors and progress
2. **Verify Results**: Check target organization for successful migration
3. **Handle Errors**: Address any failed migrations immediately
4. **Document Issues**: Record any problems for future reference

### 8.3. Post-Migration

1. **Value Verification**: Verify all critical secret values are updated
2. **Access Testing**: Test applications to ensure they can access new variables/secrets
3. **Cleanup**: Remove old configurations after successful migration
4. **Documentation Update**: Update team documentation with new locations

## 9. Troubleshooting

### 9.1. Common Issues

**Authentication Errors**:
```
Error: 401 Unauthorized
Solution: Verify token scopes and organization access
```

**Rate Limiting**:
```
Warning: Rate limit exceeded
Solution: Tools automatically handle rate limiting with backoff
```

**Permission Errors**:
```
Error: 403 Forbidden
Solution: Ensure tokens have required organization permissions
```

**Variable/Secret Already Exists**:
```
Warning: Variable/Secret already exists
Solution: Tools skip existing items by default
```

### 9.2. Debugging

**Enable Detailed Logging**:
```bash
# Variables
python github_variables_migration.py --debug

# Secrets
python github_secrets_migration.py --debug
```

**Check Log Files**:
- `github_variable_migration.log`
- `github_secrets_migration.log`

### 9.3. Recovery Procedures

**Partial Migration Recovery**:
1. Check log files for last successful operation
2. Review CSV exports to identify missing items
3. Re-run migration (tools skip existing items)
4. Manually create any remaining items

## 10. Contributing

### 10.1. Development Setup

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run tests
python -m pytest tests/

# Code quality checks
flake8 *.py
black *.py
```

### 10.2. Feature Enhancement Ideas

- Integration with secret management systems (HashiCorp Vault, Azure Key Vault)
- Automated secret value migration from external sources
- Integration with CI/CD pipeline validation
- Advanced filtering and transformation capabilities
- Integration with compliance and audit tools

---

**Note**: Always test migration tools in a non-production environment first. Ensure you have proper authorization and backup procedures before migrating production secrets and variables.

**Last Updated**: October 2025
**Version**: 2.0.0