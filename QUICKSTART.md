# Quick Start Guide

Get your GCP Backup Utility running in 5 minutes.

## Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 2: Set Up GCP Authentication

Choose one method:

### Option A: Service Account (Recommended)
```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
```

### Option B: User Credentials

#### Installl Google Cloud CLI
```bash
sudo apt-get update
sudo apt-get install ca-certificates gnupg curl
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee -a /etc/pt/sources.list.d/google-cloud-sdk.list
sudo apt-get update && sudo apt-get install google-cloud-cli
```

#### Authenticate and select project
```bash
gcloud auth application-default login
gcloud init
```

## Step 3: Create a GCS Bucket

If you don't already have a bucket:
```bash
gcloud storage buckets create gs://cold-backup-david \
       --default-storage-class=ARCHIVE \
       --location=US-CENTRAL1 \
       --uniform-bucket-level-access \
       --public-access-prevention
```

## Step 4: Run Your First Backup

```bash
# Basic backup
python backup_utility.py my-backup-bucket /path/to/backup

# With force flag (backup all files)
python backup_utility.py my-backup-bucket /path/to/backup --force
```

## Step 5: Verify Results

Check the GCS bucket:
```bash
gcloud storage objects list gs://my-backup-bucket --recursive
```

You should see:
- `backups/YYYY-MM-DD/` directories with your files
- `backup_index.json` metadata file

## Step 6: Schedule Regular Backups

### Linux/macOS: Add to Crontab
```bash
# Edit crontab
crontab -e

# Add this line for daily 2 AM backup
0 2 * * * cd /home/user/backup-to-gcp && python3 backup_utility.py my-backup-bucket /home/user/documents >> /var/log/backup.log 2>&1
```

## Common Issues

### "ModuleNotFoundError: No module named 'google'"
```bash
pip install -r requirements.txt
```

### "Credentials not found"
```bash
# Set credentials file
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json

# OR authenticate with gcloud
gcloud auth application-default login
```

### "Bucket does not exist"
```bash
# Create the bucket
gcloud storage buckets create gs://cold-backup-david \
    --default-storage-class=ARCHIVE \
    --location=US-CENTRAL1 \
    --uniform-bucket-level-access \
    --public-access-prevention
```

## Next Steps

- Read [README.md](README.md) for detailed documentation
- Check [backup_utility.py](backup_utility.py) for API reference
- Use [example_usage.py](example_usage.py) for programmatic access
- Review storage costs: https://cloud.google.com/storage/pricing

## Cost Estimation

For a typical backup of 100 GB:
- **Archive Storage**: ~$0.40/month
- **Index (Standard)**: ~$0.00001/month
- **Total**: ~$0.40/month

(Prices as of 2024, verify current rates at cloud.google.com/storage/pricing)

## Support

For issues:
1. Check the logs: `cat /var/log/backup.log`
2. Run with increased verbosity (debug level in backup_utility.py)
3. Verify GCP permissions: `gcloud storage buckets add-iam-policy-binding gs://bucket-name --member=user:address@example.com --role=roles/storage.objectAdmin`
