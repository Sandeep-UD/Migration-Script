#!/bin/bash

set -e

LOG_FILE="MigrationLog.txt"
OUTPUT_CSV="MigrationDetails.csv"
LOGS_DIR="logs"
CSV_FILE="repos.csv"
ENV_FILE=".env"

# Logging function
log_message() {
    local level="$1"
    local message="$2"
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "$timestamp [$level] $message" | tee -a "$LOG_FILE"
}

# Load .env
if [[ -f "$ENV_FILE" ]]; then
    export $(grep -v '^#' "$ENV_FILE" | xargs)
    log_message "INFO" "Loaded environment variables from $ENV_FILE"
else
    log_message "ERROR" ".env file not found."
    exit 1
fi

# Validate required env vars
if [[ -z "$GH_SOURCE_PAT" || -z "$GH_PAT" || -z "$SOURCE" || -z "$DESTINATION" ]]; then
    log_message "ERROR" "Required environment variables missing. Ensure GH_SOURCE_PAT, GH_PAT, SOURCE, DESTINATION are set in .env file."
    exit 1
fi

# Prepare logs dir and log file
mkdir -p "$LOGS_DIR"
echo "Migration Log - $(date)" > "$LOG_FILE"

# Prepare output CSV
if [[ ! -f "$OUTPUT_CSV" ]]; then
    echo "SourceOrg,SourceRepo,TargetOrg,TargetRepo,Status,StartTime,EndTime,TimeTakenSeconds" > "$OUTPUT_CSV"
fi

# Check repos.csv
if [[ ! -f "$CSV_FILE" ]]; then
    log_message "ERROR" "CSV file $CSV_FILE not found. Please create with columns: CURRENT-NAME,NEW-NAME"
    exit 1
fi

# Read and process each repo
tail -n +2 "$CSV_FILE" | while IFS=, read -r CURRENT_NAME NEW_NAME; do
    CURRENT_NAME=$(echo "$CURRENT_NAME" | tr -d '\r')
    NEW_NAME=$(echo "$NEW_NAME" | tr -d '\r')
    if [[ -z "$CURRENT_NAME" || -z "$NEW_NAME" ]]; then
        log_message "ERROR" "Missing CURRENT-NAME or NEW-NAME in CSV row. Skipping."
        continue
    fi

    log_message "INFO" "Migrating '$CURRENT_NAME' -> '$NEW_NAME'..."
    START_TIME=$(date '+%Y-%m-%d %H:%M:%S')
    START_TS=$(date +%s)
    STATUS="Success"

    COMMAND="gh gei migrate-repo --github-source-org $SOURCE --source-repo $CURRENT_NAME --github-target-org $DESTINATION --target-repo $NEW_NAME"
    OUTPUT=$($COMMAND 2>&1) || STATUS="Failed"

    if echo "$OUTPUT" | grep -qiE "error|failed"; then
        STATUS="Failed"
        echo "$OUTPUT" > "$LOGS_DIR/$CURRENT_NAME.log"
        log_message "ERROR" "Error log saved to $LOGS_DIR/$CURRENT_NAME.log"
    fi

    END_TIME=$(date '+%Y-%m-%d %H:%M:%S')
    END_TS=$(date +%s)
    TIME_TAKEN=$((END_TS - START_TS))

    echo "$SOURCE,$CURRENT_NAME,$DESTINATION,$NEW_NAME,$STATUS,$START_TIME,$END_TIME,$TIME_TAKEN" >> "$OUTPUT_CSV"
    log_message "INFO" "Migration result: Status=$STATUS, Duration=${TIME_TAKEN}s"
done

log_message "INFO" "All repository migrations complete!"