# GitHub Repository Migration Script

This Python script automates the migration of repositories from a source GitHub organization to a target organization using the GitHub Enterprise Importer (gh gei) CLI tool.

## Features

- ✅ Bulk repository migration using `gh gei` CLI
- ✅ Environment variable configuration for security
- ✅ API rate limiting handling
- ✅ Streamlined console output with real-time progress
- ✅ Comprehensive file-based logging with per-repository logs
- ✅ Migration validation and reporting
- ✅ Excel report generation with detailed comparison and timing data
- ✅ Error handling and retry mechanisms
- ✅ Fast processing with no artificial delays

## Prerequisites

### 1. Install GitHub CLI and GEI Extension

```powershell
# Install GitHub CLI (if not already installed)
winget install GitHub.cli

# Install GitHub Enterprise Importer extension
gh extension install github/gh-gei
```

### 2. Python Dependencies

Install the required Python packages:

```powershell
pip install -r requirements.txt
```

## Setup

### 1. Environment Configuration

1. Copy the template file:
   ```powershell
   Copy-Item .env.template .env
   ```

2. Edit the `.env` file with your actual values:
   ```
   SOURCE_GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
   TARGET_GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
   SOURCE_ORGANIZATION=source-org-name
   TARGET_ORGANIZATION=target-org-name
   ```

### 2. Token Permissions

Your GitHub Personal Access Tokens need the following permissions:

**Source Token:**
- `repo` (Full control of private repositories)
- `read:org` (Read org membership)
- `read:user` (Read user profile data)

**Target Token:**
- `repo` (Full control of private repositories)
- `admin:org` (Full control of orgs and teams)
- `user` (Update user data)

### 3. Repository List

Ensure your `repos.csv` file contains the repositories to migrate:

```csv
source_repo_name,target_repo_name
repo1,repo1
repo2,repo2-renamed
```

## Usage

### Basic Migration

```powershell
python migrate_repos.py
```

### Console Output

The script provides clean, minimal console output focusing on essential progress:

```
[1/3] Migrating: source-org/repo1 -> target-org/repo1
✓ SUCCESS: repo1 migrated in 45.2s
[2/3] Migrating: source-org/repo2 -> target-org/repo2
✓ SUCCESS: repo2 migrated in 38.7s
[3/3] Migrating: source-org/repo3 -> target-org/repo3
✗ FAILED: repo3 migration failed

Migration Summary:
  Total: 3 repositories
  Success: 2
  Failed: 1
Generating migration report...
Migration report generated successfully
Migration process completed!
```

### What the Script Does

1. **Silent Startup**: Initializes without verbose console messages
2. **Validation**: Checks environment variables and CLI tool availability
3. **Migration**: Uses `gh gei migrate-repo` to migrate each repository with real-time progress
4. **Post-migration Analysis**: Collects detailed information about migrated repositories
5. **Report Generation**: Creates comprehensive Excel report with timing data and comparison

## Output Files

### Log Files
- `logs/migration_YYYYMMDD_HHMMSS.log` - Detailed execution log with all migration activities
- `migration_errors.log` - Error-specific logging for failed operations
- `logs/reponame__to__targetname.log` - Individual log file for each repository migration with real-time gh gei output

### Migration Report
- `migration_report_YYYYMMDD_HHMMSS.xlsx` - Comprehensive Excel report with multiple sheets:
  - **Migration_Summary**: Overall migration status with timing data and final status column
  - **Source_Repositories**: Source repository details
  - **Target_Repositories**: Target repository details
  - **Branches_Comparison**: Branch count comparison
  - **Issues_Comparison**: Issues count comparison
  - **PRs_Comparison**: Pull requests comparison
  - **Releases_Comparison**: Releases comparison
  - **Commits_Comparison**: Commits count comparison

## Report Details

The migration report includes the following information:

### Migration Summary Sheet
- Source Organization
- Source Repository
- Target Organization
- Target Repository
- Start Time (YYYY-MM-DD HH:MM:SS)
- End Time (YYYY-MM-DD HH:MM:SS)
- Duration (Seconds)
- Duration (Minutes)
- Migration Status (Success/Failed) - **Final column**

### Repository Information (Source & Target sheets)
- Organization name
- Repository name
- Default branch
- Total number of branches

### Issues Analysis
- Total issues count
- Open issues count
- Closed issues count

### Pull Requests Analysis
- Total PRs count
- Open PRs count
- Closed PRs count

### Additional Metrics
- Total releases count
- Total commits count (approximate)

## Error Handling

The script includes robust error handling:

- **API Rate Limiting**: Automatically waits when rate limits are approached
- **Network Failures**: Retries with exponential backoff
- **Migration Failures**: Logs detailed error information
- **Timeout Handling**: 1-hour timeout per repository migration

## Logging

Streamlined logging approach:

### Console Output
- **Minimal, clean progress indicators** with ✓/✗ symbols
- **Real-time migration status** showing current repository and timing
- **Summary statistics** at completion
- **No verbose startup messages** for distraction-free operation

### File Logging
- **Comprehensive main log** (`logs/migration_YYYYMMDD_HHMMSS.log`) with all details
- **Error-specific log** (`migration_errors.log`) for troubleshooting
- **Per-repository logs** (`logs/repo__to__target.log`) with individual migration output
- **UTF-8 encoding** for proper Unicode character handling

## Troubleshooting

### Common Issues

1. **"gh gei command not found"**
   - Install the GEI extension: `gh extension install github/gh-gei`

2. **"Rate limit exceeded"**
   - The script automatically handles this, but ensure your tokens have sufficient rate limits

3. **"Repository not found"**
   - Verify repository names in `repos.csv`
   - Check token permissions

4. **"Migration failed"**
   - Check `migration_errors.log` for specific error details
   - Review individual repository logs in `logs/` directory
   - Verify target organization permissions

### Debug Mode

For more detailed debugging, modify the logging level in the script:

```python
logging.basicConfig(level=logging.DEBUG, ...)
```

## Recent Improvements

### Version 2.0 Updates
- 🚀 **Streamlined Console Output**: Removed verbose startup messages and logging noise
- ⚡ **Faster Processing**: Eliminated artificial 30-second delays between migrations
- 📊 **Enhanced Excel Reports**: Added timing data with Migration Status as the final column
- 📝 **Improved Logging Structure**: 
  - File-only detailed logging (no console spam)
  - Per-repository log files with real-time gh gei output
  - Separate error log for troubleshooting
- 🎯 **Better User Experience**: Clean progress indicators with ✓/✗ symbols and timing
- 🗂️ **Simplified Output**: Removed redundant CSV file generation

## Security Notes

- Never commit your `.env` file to version control
- Use fine-grained personal access tokens when possible
- Regularly rotate your access tokens
- Store tokens securely using environment variables or secret management tools

## Limitations

- The commit count is approximate (based on contributors API)
- Large repositories may take significant time to migrate (no artificial delays added)
- Some GitHub features may not be fully migrated (check GEI documentation)
- Console output is minimal by design - detailed information is in log files

## Support

For issues with:
- **This script**: Check the logs and troubleshooting section
- **GitHub Enterprise Importer**: Refer to [GitHub GEI documentation](https://docs.github.com/en/migrations/using-github-enterprise-importer)
- **GitHub CLI**: Refer to [GitHub CLI documentation](https://cli.github.com/)