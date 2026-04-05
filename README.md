# GCP Backup Utility

A Python utility for efficiently backing up files from local directories to Google Cloud Storage with intelligent versioning and deduplication.

## Features

- **Efficient backups**: Only backs up new or modified files
- **Storage optimization**: Uses Archive storage class (cheapest, most durable) for long-term data
- **Index management**: Maintains a lightweight index in Standard storage for frequent access
- **File versioning**: Automatically creates new backup directories when files are modified
- **Date-based organization**: Files organized per backup date for easy historical retrieval
- **File integrity**: Uses SHA256 hashing to detect changes and ensure deduplication

## Storage Classes

- **Archive**: Used for backup data (accessed less than once per year) - most economical
- **Standard**: Used for the backup index (accessed multiple times per month)

## Prerequisites

1. Python 3.7+
2. Google Cloud Storage account with a bucket
3. GCP credentials configured via `GOOGLE_APPLICATION_CREDENTIALS` environment variable or gcloud CLI

## Installation

```bash
pip install -r requirements.txt
```

## Setup

### 1. Create a GCS Bucket

```bash
gsutil mb gs://your-backup-bucket-name
```

### 2. Configure GCP Credentials

Option A: Using service account key file:
```bash
export GOOGLE_APPLICATION_CREDENTIALS=${HOME}/.config/gcloud/application_default_credentials.json
```

Option B: Using gcloud CLI:
```bash
gcloud auth application-default login
```

### 3. Set correct permissions on the bucket

The service account or user needs these permissions:
- `storage.objects.create`
- `storage.objects.get`
- `storage.objects.delete`
- `storage.buckets.get`

## Usage

### Basic backup:
```bash
python backup_utility.py --bucket <bucket-name> --source-dir <local-directory>
```

Example:
```bash
python backup_utility.py --bucket my-backup-bucket --source-dir /home/user/documents
```



## How It Works

1. **First backup**: All files from the local directory are uploaded to `backups/{YYYY-MM-DD}/` in Archive storage
2. **Subsequent backups**: 
   - Files are compared using SHA256 hashes
   - Unchanged files are skipped
   - Modified files are uploaded to a new directory with today's date: `backups/{NEW-DATE}/`
   - New files are uploaded to today's backup directory
3. **Index maintenance**:
   - A `backup_index.json` file is maintained in Standard storage
   - Tracks each file's hash and last backup date
   - Updated after each backup run

## GCS Directory Structure

```
gs://bucket-name/
├── backups/
│   ├── 2024-01-15/
│   │   ├── documents/report.pdf
│   │   └── data/config.json
│   ├── 2024-01-16/
│   │   └── documents/report.pdf  (modified version)
│   └── 2024-01-17/
│       └── photos/vacation.jpg
└── backup_index.json (Standard storage class)
```

## Index Format

The `backup_index.json` file contains:
```json
{
  "documents/report.pdf": {
    "hash": "abc123def456...",
    "last_backup_date": "2024-01-16",
    "size": 2048576
  },
  "data/config.json": {
    "hash": "xyz789uvw012...",
    "last_backup_date": "2024-01-15",
    "size": 4096
  }
}
```

## Scheduling Backups

### Linux/macOS (crontab)

```bash
# Daily backup at 2 AM
0 2 * * * cd /home/user/backup-to-gcp && python backup_utility.py my-backup-bucket /home/user/documents >> /var/log/backup.log 2>&1
```

### Windows (Task Scheduler)

1. Create a batch file `backup.bat`:
```batch
cd C:\path\to\backup-to-gcp
python backup_utility.py my-backup-bucket C:\path\to\documents >> C:\backup\backup.log 2>&1
```

2. Schedule via Task Scheduler to run at desired intervals

## Cost Optimization

This utility is designed for cost efficiency:

- **Archive storage**: ~$0.004/GB/month (vs $0.020 for Standard)
- **Index in Standard storage**: Very small (~KB), minimal cost impact
- **Deduplication**: Only changed files are uploaded, reducing bandwidth costs

## Error Handling

The utility will:
- Log all operations to console and filesystem
- Report backup statistics (new, modified, skipped files)
- Raise exceptions on critical errors that interrupt the backup

## Logging

Set the logging level in `backup_utility.py`:
```python
logging.basicConfig(level=logging.DEBUG)  # For verbose output
```

## Troubleshooting

### "Credentials not found" error
- Ensure `GOOGLE_APPLICATION_CREDENTIALS` is set correctly
- Or run `gcloud auth application-default login`

### "Bucket does not exist" error
- Verify bucket name is correct
- Check if bucket exists: `gsutil ls -b gs://bucket-name`

### Permission denied errors
- Verify service account has required permissions
- Check bucket IAM settings

## Performance Notes

- The first backup may take longer due to uploading all files
- Subsequent backups are fast as only changed files are processed
- File hashing is done locally to minimize GCS API calls
- Index is cached locally during backup runs

## Security

- Files are encrypted in transit (HTTPS)
- Archive storage class provides 99.99999999% (11 nines) durability
- Consider enabling bucket versioning for additional protection
- Use service accounts with minimal required permissions

## License

[Your License Here]
