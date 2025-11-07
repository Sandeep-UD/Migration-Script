# Import .env file
function Import-EnvFile {
    param (
        [string]$Path
    )
    Get-Content $Path | ForEach-Object {
        $_ = $_.Trim() 
        if (-not [string]::IsNullOrWhiteSpace($_) -and -not $_.StartsWith("#")) {
            if ($_ -match "^(?<Key>[^=]+)=(?<Value>.+)$") {
                $key = $matches['Key'].Trim()
                $value = $matches['Value'].Trim()
                if (-not [string]::IsNullOrWhiteSpace($key) -and -not [string]::IsNullOrWhiteSpace($value)) {
                    Set-Item -Path Env:$key -Value $value
                } else {
                    Log-Message "Skipping invalid or empty key/value in .env file: '$_'" "WARNING"
                }
            } else {
                Log-Message "Skipping malformed line in .env file: '$_'" "WARNING"
            }
        }
    }
}

# Initialize log files and folders
$logFilePath = "MigrationLog.txt"
$outputCsvFile = "MigrationDetails.csv"
$logsFolder = "logs"

if (-not (Test-Path $logsFolder)) {
    New-Item -ItemType Directory -Path $logsFolder | Out-Null
}

Write-Host "Initializing log file at $logFilePath..."
"Migration Log - $(Get-Date)" | Out-File -FilePath $logFilePath

# Log function
function Log-Message {
    param (
        [string]$Message,
        [string]$Level = "INFO"
    )
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "$timestamp [$Level] $Message"
    Write-Host $logEntry
    $logEntry | Out-File -FilePath $logFilePath -Append
}

# Load .env
$envFilePath = ".env"
if (Test-Path $envFilePath) {
    Log-Message "Loading environment variables from $envFilePath..."
    Import-EnvFile -Path $envFilePath
} else {
    Log-Message ".env file not found." "ERROR"
    exit 1
}

# Validate required environment variables
if (-not $env:GH_SOURCE_PAT -or -not $env:GH_PAT -or -not $env:SOURCE -or -not $env:DESTINATION) {
    Log-Message "Required environment variables missing. Ensure GH_SOURCE_PAT, GH_PAT, SOURCE, DESTINATION are set in .env file." "ERROR"
    exit 1
}

# CSV file
$csvFilePath = "repos.csv"
if (-not (Test-Path $csvFilePath)) {
    Log-Message "CSV file $csvFilePath not found. Please create with columns: CURRENT-NAME, NEW-NAME" "ERROR"
    exit 1
}

# Initialize CSV output file with header if not exist
if (-not (Test-Path $outputCsvFile)) {
    $headerObject = [PSCustomObject]@{
        SourceOrg = ""
        SourceRepo = ""
        TargetOrg = ""
        TargetRepo = ""
        Status = ""
        StartTime = ""
        EndTime = ""
        TimeTakenSeconds = ""
    }
    $headerObject | Export-Csv -Path $outputCsvFile -NoTypeInformation
}

# Read repos.csv
Log-Message "Reading repository details from $csvFilePath..."
$repos = Import-Csv -Path $csvFilePath

foreach ($repo in $repos) {
    $currentName = $repo.'CURRENT-NAME'
    $newName = $repo.'NEW-NAME'

    if (-not $currentName -or -not $newName) {
        Log-Message "Missing CURRENT-NAME or NEW-NAME in CSV row. Skipping." "ERROR"
        continue
    }

    Log-Message "Migrating '$currentName' -> '$newName'..."
    $startTime = Get-Date
    $status = "Success"

    $command = "gh gei migrate-repo --github-source-org $env:SOURCE --source-repo $currentName --github-target-org $env:DESTINATION --target-repo $newName"

    try {
        $output = Invoke-Expression $command 2>&1
        Log-Message "Command output for '$currentName': $output"

        if ($output -match "error" -or $output -match "failed") {
            $status = "Failed"
            $repoLogFile = Join-Path $logsFolder "$currentName.log"
            $output | Out-File -FilePath $repoLogFile -Encoding UTF8
            Log-Message "Error log saved to $repoLogFile" "ERROR"
        }
    } catch {
        $status = "Failed"
        $repoLogFile = Join-Path $logsFolder "$currentName.log"
        $_ | Out-File -FilePath $repoLogFile -Encoding UTF8
        Log-Message "Exception caught during migration of '$currentName'. See $repoLogFile for details." "ERROR"
    }

    $endTime = Get-Date
    $startTimeFormatted = $startTime.ToString("yyyy-MM-dd HH:mm:ss")
    $endTimeFormatted = $endTime.ToString("yyyy-MM-dd HH:mm:ss")
    $timeTaken = [math]::Round(($endTime - $startTime).TotalSeconds, 2)

    # Write details to CSV (proper structured)
    $csvObject = [PSCustomObject]@{
        SourceOrg = $env:SOURCE
        SourceRepo = $currentName
        TargetOrg = $env:DESTINATION
        TargetRepo = $newName
        Status = $status
        StartTime = $startTimeFormatted
        EndTime = $endTimeFormatted
        TimeTakenSeconds = $timeTaken
    }
    $csvObject | Export-Csv -Path $outputCsvFile -Append -NoTypeInformation

    Log-Message "Migration result: Status=$status, Duration=${timeTaken}s"
}

Log-Message "All repository migrations complete!"
