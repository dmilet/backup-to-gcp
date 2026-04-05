#!/usr/bin/env python3
"""
GCP Backup Utility

A utility tool to backup files from a local directory to Google Cloud Storage.
- Files are stored in the Archive storage class (cheapest, most durable)
- An index is maintained in the Standard storage class for frequent access
- Files are organized by backup date
- Modified files trigger new backups with updated dates
"""

import os
import json
import hashlib
import argparse
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Set, Tuple
import logging

from google.cloud import storage
from google.auth.exceptions import DefaultCredentialsError


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class GCPBackupUtility:
    """Handles backup of local files to Google Cloud Storage."""
    
    # Storage classes
    ARCHIVE_CLASS = 'ARCHIVE'  # Cheapest, most durable, for data not accessed within 1 year
    STANDARD_CLASS = 'STANDARD'  # For the index (accessed multiple times per month)
    
    def __init__(self, bucket_name: str, local_path: str, project_id: str = None):
        """
        Initialize the backup utility.
        
        Args:
            bucket_name: GCS bucket name for storing backups
            local_path: Local directory path to backup
            project_id: GCP project ID (optional, inferred from credentials if not provided)
        
        Raises:
            DefaultCredentialsError: If GCP credentials cannot be found
        """
        self.bucket_name = bucket_name
        self.local_path = Path(local_path).resolve()
        self.project_id = project_id
        
        if not self.local_path.exists():
            raise ValueError(f"Local path does not exist: {self.local_path}")
        
        try:
            self.client = storage.Client(project=project_id)
            self.bucket = self.client.bucket(bucket_name)
            logger.info(f"Connected to GCS bucket: {bucket_name}")
        except DefaultCredentialsError:
            raise DefaultCredentialsError(
                "GCP credentials not found. Please set GOOGLE_APPLICATION_CREDENTIALS "
                "or configure gcloud authentication."
            )
    
    def _get_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of a file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def _get_relative_path(self, file_path: Path) -> str:
        """Get the relative path from local_path."""
        return str(file_path.relative_to(self.local_path))
    
    def _load_index(self) -> Dict:
        """
        Load the backup index from GCS.
        
        Returns:
            Dictionary with file index, or empty dict if no index exists
        """
        index_blob_name = 'backup_index.json'
        blob = self.bucket.blob(index_blob_name)
        
        if not blob.exists():
            logger.info("No existing backup index found")
            return {}
        
        try:
            index_content = blob.download_as_string()
            index = json.loads(index_content)
            logger.info(f"Loaded backup index with {len(index)} entries")
            return index
        except Exception as e:
            logger.error(f"Error loading index: {e}")
            return {}
    
    def _save_index(self, index: Dict) -> None:
        """
        Save the backup index to GCS using Standard storage class.
        
        Args:
            index: Dictionary to save as index
        """
        index_blob_name = 'backup_index.json'
        blob = self.bucket.blob(index_blob_name, storage_class=self.STANDARD_CLASS)
        
        try:
            json_data = json.dumps(index, indent=2)
            blob.upload_from_string(
                json_data,
                content_type='application/json'
            )
            logger.info(f"Saved backup index with {len(index)} entries")
        except Exception as e:
            logger.error(f"Error saving index: {e}")
            raise
    
    def _upload_file(self, local_file: Path, backup_date: str, relative_path: str) -> None:
        """
        Upload a file to GCS in Archive storage class.
        
        Args:
            local_file: Path to local file
            backup_date: Date string (YYYY-MM-DD format)
            relative_path: Relative path from local_path
        """
        # Create the GCS blob path: backups/{date}/{relative_path}
        gcs_blob_name = f"backups/{backup_date}/{relative_path}"
        blob = self.bucket.blob(gcs_blob_name, storage_class=self.ARCHIVE_CLASS)
        
        try:
            blob.upload_from_filename(str(local_file))
            logger.info(f"Uploaded: {relative_path} to {gcs_blob_name}")
        except Exception as e:
            logger.error(f"Error uploading {local_file}: {e}")
            raise
    
    def _get_all_local_files(self) -> Dict[str, Path]:
        """
        Get all files in local_path recursively.
        
        Returns:
            Dictionary mapping relative path to absolute Path
        """
        files = {}
        for file_path in self.local_path.rglob('*'):
            if file_path.is_file():
                relative_path = self._get_relative_path(file_path)
                files[relative_path] = file_path
        return files
    
    def backup(self, force: bool = False) -> Dict:
        """
        Perform backup of modified or new files.
        
        Args:
            force: If True, backup all files regardless of modification
        
        Returns:
            Dictionary with backup statistics
        """
        today = date.today().isoformat()  # YYYY-MM-DD format
        
        logger.info(f"Starting backup on {today}")
        logger.info(f"Local path: {self.local_path}")
        
        # Load existing index
        index = self._load_index()
        
        # Get all local files
        local_files = self._get_all_local_files()
        logger.info(f"Found {len(local_files)} local files")
        
        stats = {
            'new_files': 0,
            'modified_files': 0,
            'skipped_files': 0,
            'total_files': len(local_files),
            'backup_date': today
        }
        
        # Process each local file
        for relative_path, local_file in sorted(local_files.items()):
            file_hash = self._get_file_hash(local_file)
            
            # Check if file is already backed up
            if relative_path in index:
                previous_entry = index[relative_path]
                previous_hash = previous_entry.get('hash')
                
                if file_hash == previous_hash and not force:
                    # File unchanged
                    stats['skipped_files'] += 1
                    continue
                else:
                    # File modified
                    logger.info(f"File modified: {relative_path}")
                    stats['modified_files'] += 1
            else:
                # New file
                logger.info(f"New file: {relative_path}")
                stats['new_files'] += 1
            
            # Upload the file
            self._upload_file(local_file, today, relative_path)
            
            # Update index entry
            index[relative_path] = {
                'hash': file_hash,
                'last_backup_date': today,
                'size': local_file.stat().st_size
            }
        
        # Save updated index
        self._save_index(index)
        
        log_msg = (f"Backup complete: {stats['new_files']} new, "
                   f"{stats['modified_files']} modified, "
                   f"{stats['skipped_files']} skipped")
        logger.info(log_msg)
        
        return stats


def main():
    parser = argparse.ArgumentParser(
        description='Backup files to Google Cloud Storage'
    )
    parser.add_argument(
        'bucket',
        help='GCS bucket name'
    )
    parser.add_argument(
        'local_path',
        help='Local directory to backup'
    )
    parser.add_argument(
        '--project-id',
        help='GCP project ID (optional)',
        default=None
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force backup of all files'
    )
    
    args = parser.parse_args()
    
    try:
        utility = GCPBackupUtility(
            bucket_name=args.bucket,
            local_path=args.local_path,
            project_id=args.project_id
        )
        stats = utility.backup(force=args.force)
        print(json.dumps(stats, indent=2))
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        raise


if __name__ == '__main__':
    main()
