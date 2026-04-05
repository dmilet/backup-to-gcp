#!/usr/bin/env python3
"""
Example usage of the GCP Backup Utility.

This script demonstrates how to use the backup utility programmatically.
"""

import os
import json
from backup_utility import GCPBackupUtility


def main():
    # Configuration
    bucket_name = 'my-backup-bucket'
    local_path = '/home/user/documents'
    
    # Ensure credentials are configured
    if 'GOOGLE_APPLICATION_CREDENTIALS' not in os.environ:
        print("Error: GOOGLE_APPLICATION_CREDENTIALS not set")
        print("Please set it to your service account key file path")
        return
    
    try:
        # Initialize backup utility
        backup = GCPBackupUtility(
            bucket_name=bucket_name,
            local_path=local_path,
            project_id=None  # Will be inferred from credentials
        )
        
        # Perform backup
        stats = backup.backup(force=False)
        
        # Print results
        print("\nBackup Statistics:")
        print(json.dumps(stats, indent=2))
        
        if stats['new_files'] > 0 or stats['modified_files'] > 0:
            print(f"\n✓ Successfully backed up {stats['new_files'] + stats['modified_files']} files")
        else:
            print("\n✓ No changes to backup")
    
    except Exception as e:
        print(f"\n✗ Backup failed: {e}")
        raise


if __name__ == '__main__':
    main()
