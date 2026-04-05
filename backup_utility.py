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
import getpass
import secrets
import shutil
import tempfile
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Set, Tuple, Optional
import logging

from google.cloud import storage
from google.auth.exceptions import DefaultCredentialsError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


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
    
    def __init__(self, bucket_name: str, local_path: str,
                 encryption_key: Optional[bytes] = None, preview_mode: bool = False):
        """
        Initialize the backup utility.
        
        Args:
            bucket_name: GCS bucket name for storing backups
            local_path: Local directory path to backup
            encryption_key: 32-byte encryption key for AES-256-GCM (optional)
            preview_mode: If True, save encrypted files locally instead of uploading
        
        Raises:
            DefaultCredentialsError: If GCP credentials cannot be found
        """
        self.bucket_name = bucket_name
        self.local_path = Path(local_path).resolve()
        self.encryption_key = encryption_key
        self.use_encryption = encryption_key is not None
        self.preview_mode = preview_mode
        
        if not self.local_path.exists():
            raise ValueError(f"Local path does not exist: {self.local_path}")
        
        try:
            self.client = storage.Client()
            self.bucket = self.client.bucket(bucket_name)
            logger.info(f"Connected to GCS bucket: {bucket_name}")
        except DefaultCredentialsError:
            raise DefaultCredentialsError(
                "GCP credentials not found. Please set GOOGLE_APPLICATION_CREDENTIALS "
                "or configure gcloud authentication."
            )
    
    @staticmethod
    def derive_key_from_passphrase(passphrase: str, salt: bytes = None) -> Tuple[bytes, bytes]:
        """
        Derive a 32-byte encryption key from a passphrase using PBKDF2.
        
        Args:
            passphrase: User-provided passphrase
            salt: Optional salt (16 bytes). If None, generates a new random salt.
        
        Returns:
            Tuple of (key, salt)
        """
        if salt is None:
            salt = secrets.token_bytes(16)
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # 256 bits for AES-256
            salt=salt,
            iterations=480000,  # OWASP recommendation as of 2023
        )
        key = kdf.derive(passphrase.encode('utf-8'))
        return key, salt
    
    def _get_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of a file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def _encrypt_file(self, input_path: Path, output_path: Path) -> str:
        """
        Encrypt a file using AES-256-GCM and return its hash.
        
        Args:
            input_path: Path to the file to encrypt
            output_path: Path where encrypted file will be written
        
        Returns:
            SHA256 hash of the encrypted file
        """
        # Generate a random 96-bit (12-byte) nonce for GCM
        nonce = secrets.token_bytes(12)
        
        # Initialize AES-GCM cipher
        aesgcm = AESGCM(self.encryption_key)
        
        # Read the plaintext file
        with open(input_path, 'rb') as f:
            plaintext = f.read()
        
        # Encrypt the data
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        
        # Write nonce + ciphertext to output file
        # Format: [12-byte nonce][encrypted data with auth tag]
        encrypted_data = nonce + ciphertext
        
        with open(output_path, 'wb') as f:
            f.write(encrypted_data)
        
        # Compute and return hash of encrypted file
        return hashlib.sha256(encrypted_data).hexdigest()
    
    def _get_relative_path(self, file_path: Path) -> str:
        """Get the relative path from local_path, including the leaf directory."""
        relative_to_parent = file_path.relative_to(self.local_path)
        return str(Path(self.local_path.name) / relative_to_parent)
    
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
        blob = self.bucket.blob(index_blob_name)
        blob.storage_class=self.STANDARD_CLASS
        
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
    
    def _save_preview_file(self, local_file: Path, backup_date: str, relative_path: str) -> Optional[str]:
        """
        Save encrypted file to local preview directory.
        
        Args:
            local_file: Path to local file
            backup_date: Date string (YYYY-MM-DD format)
            relative_path: Relative path from local_path
        
        Returns:
            SHA256 hash of encrypted file if encryption is enabled, None otherwise
        """
        # Create preview directory structure
        preview_base = Path.cwd() / "preview" / "backups" / backup_date
        preview_file_path = preview_base / relative_path
        
        # Add .encrypted extension if using encryption
        if self.use_encryption:
            preview_file_path = Path(str(preview_file_path) + ".encrypted")
        
        # Create parent directories
        preview_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            encrypted_hash = None
            
            if self.use_encryption:
                # Encrypt and save file
                encrypted_hash = self._encrypt_file(local_file, preview_file_path)
                logger.info(f"Saved (encrypted): {relative_path} to {preview_file_path}")
            else:
                # Copy plaintext file
                shutil.copy2(local_file, preview_file_path)
                logger.info(f"Saved: {relative_path} to {preview_file_path}")
            
            return encrypted_hash
            
        except Exception as e:
            logger.error(f"Error saving preview file {local_file}: {e}")
            raise
    
    def _upload_file(self, local_file: Path, backup_date: str, relative_path: str) -> Optional[str]:
        """
        Upload a file to GCS in Archive storage class.
        Encrypts the file first if encryption is enabled.
        
        Args:
            local_file: Path to local file
            backup_date: Date string (YYYY-MM-DD format)
            relative_path: Relative path from local_path
        
        Returns:
            SHA256 hash of encrypted file if encryption is enabled, None otherwise
        """
        # Create the GCS blob path: backups/{date}/{relative_path}
        gcs_blob_name = f"backups/{backup_date}/{relative_path}"
        
        # Add .encrypted extension if using encryption
        if self.use_encryption:
            gcs_blob_name += ".encrypted"
        
        blob = self.bucket.blob(gcs_blob_name)
        blob.storage_class=self.ARCHIVE_CLASS
        
        try:
            encrypted_hash = None
            
            if self.use_encryption:
                # Create temporary file for encrypted data
                with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                    tmp_path = Path(tmp_file.name)
                
                try:
                    # Encrypt the file
                    encrypted_hash = self._encrypt_file(local_file, tmp_path)
                    
                    # Upload encrypted file
                    blob.upload_from_filename(str(tmp_path))
                    logger.info(f"Uploaded (encrypted): {relative_path} to {gcs_blob_name}")
                finally:
                    # Clean up temporary file
                    tmp_path.unlink(missing_ok=True)
            else:
                # Upload plaintext file
                blob.upload_from_filename(str(local_file))
                logger.info(f"Uploaded: {relative_path} to {gcs_blob_name}")
            
            return encrypted_hash
            
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
    
    def backup(self) -> Dict:
        """
        Perform backup of modified or new files.
        
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
                
                if file_hash == previous_hash:
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
            
            # Upload or save preview file (encrypted if encryption is enabled)
            if self.preview_mode:
                encrypted_hash = self._save_preview_file(local_file, today, relative_path)
            else:
                encrypted_hash = self._upload_file(local_file, today, relative_path)
            
            # Update index entry
            index[relative_path] = {
                'hash': file_hash,  # Original file hash
                'last_backup_date': today,
                'size': local_file.stat().st_size,
                'encrypted': self.use_encryption
            }
            
            # Store encrypted file hash if encryption was used
            if encrypted_hash:
                index[relative_path]['encrypted_hash'] = encrypted_hash
        
        # Save updated index (skip in preview mode)
        if not self.preview_mode:
            self._save_index(index)
        else:
            # Save index locally in preview mode
            preview_index_path = Path.cwd() / "preview" / "backup_index.json"
            preview_index_path.parent.mkdir(parents=True, exist_ok=True)
            with open(preview_index_path, 'w') as f:
                json.dump(index, f, indent=2)
            logger.info(f"Saved preview index to {preview_index_path}")
        
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
        '--bucket',
        required=True,
        help='GCS bucket name'
    )
    parser.add_argument(
        '--source-dir',
        required=True,
        help='Local directory to backup'
    )
    parser.add_argument(
        '--no-encryption',
        action='store_true',
        help='Skip file encryption (files uploaded in plaintext)'
    )
    parser.add_argument(
        '--preview',
        action='store_true',
        help='Preview mode: encrypt files locally to ./preview directory without uploading'
    )
    
    args = parser.parse_args()
    
    # Handle encryption key
    encryption_key = None
    if not args.no_encryption:
        passphrase = getpass.getpass("Enter encryption passphrase: ")
        if not passphrase:
            logger.error("Encryption passphrase is required (use --no-encryption to skip)")
            return
        encryption_key, _ = GCPBackupUtility.derive_key_from_passphrase(passphrase)
        logger.info("Encryption enabled (AES-256-GCM)")
    else:
        if args.preview:
            logger.warning("⚠️  Encryption disabled - files will be saved in plaintext!")
        else:
            logger.warning("⚠️  Encryption disabled - files will be uploaded in plaintext!")
    
    try:
        utility = GCPBackupUtility(
            bucket_name=args.bucket,
            local_path=args.source_dir,
            encryption_key=encryption_key,
            preview_mode=args.preview
        )
        stats = utility.backup()
        print(json.dumps(stats, indent=2))
        
        if args.preview:
            preview_dir = Path.cwd() / "preview"
            logger.info(f"Preview files saved to: {preview_dir}")
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        raise


if __name__ == '__main__':
    main()
