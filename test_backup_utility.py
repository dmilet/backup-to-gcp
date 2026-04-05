#!/usr/bin/env python3
"""
Unit tests for the GCP Backup Utility.

Run with: python -m pytest test_backup_utility.py
"""

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import hashlib

from backup_utility import GCPBackupUtility


class TestGCPBackupUtility(unittest.TestCase):
    """Tests for GCPBackupUtility class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_path = Path(self.temp_dir.name)
    
    def tearDown(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()
    
    def test_get_file_hash(self):
        """Test SHA256 file hashing."""
        test_file = self.test_path / "test.txt"
        test_content = b"Hello, World!"
        test_file.write_bytes(test_content)
        
        with patch('backup_utility.storage.Client'):
            utility = GCPBackupUtility('test-bucket', str(self.test_path))
            file_hash = utility._get_file_hash(test_file)
            
            # Verify hash is correct
            expected_hash = hashlib.sha256(test_content).hexdigest()
            self.assertEqual(file_hash, expected_hash)
    
    def test_get_relative_path(self):
        """Test relative path calculation."""
        test_file = self.test_path / "subdir" / "test.txt"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("test")
        
        with patch('backup_utility.storage.Client'):
            utility = GCPBackupUtility('test-bucket', str(self.test_path))
            relative = utility._get_relative_path(test_file)
            
            self.assertEqual(relative, "subdir/test.txt")
    
    def test_get_all_local_files(self):
        """Test recursive file discovery."""
        # Create test directory structure
        (self.test_path / "dir1").mkdir()
        (self.test_path / "dir1" / "file1.txt").write_text("content1")
        (self.test_path / "dir1" / "file2.txt").write_text("content2")
        (self.test_path / "dir2").mkdir()
        (self.test_path / "dir2" / "file3.txt").write_text("content3")
        
        with patch('backup_utility.storage.Client'):
            utility = GCPBackupUtility('test-bucket', str(self.test_path))
            files = utility._get_all_local_files()
            
            self.assertEqual(len(files), 3)
            self.assertIn("dir1/file1.txt", files)
            self.assertIn("dir1/file2.txt", files)
            self.assertIn("dir2/file3.txt", files)
    
    def test_index_serialization(self):
        """Test index save and load."""
        test_index = {
            "file1.txt": {
                "hash": "abc123",
                "last_backup_date": "2024-01-15",
                "size": 1024
            }
        }
        
        with patch('backup_utility.storage.Client') as mock_client:
            mock_bucket = MagicMock()
            mock_client.return_value.bucket.return_value = mock_bucket
            
            mock_blob = MagicMock()
            mock_bucket.blob.return_value = mock_blob
            
            utility = GCPBackupUtility('test-bucket', str(self.test_path))
            utility._save_index(test_index)
            
            # Verify upload was called with JSON
            mock_blob.upload_from_string.assert_called_once()
            call_args = mock_blob.upload_from_string.call_args
            uploaded_json = json.loads(call_args[0][0])
            
            self.assertEqual(uploaded_json, test_index)
    
    def test_storage_classes(self):
        """Test that correct storage classes are used."""
        self.assertEqual(GCPBackupUtility.ARCHIVE_CLASS, 'ARCHIVE')
        self.assertEqual(GCPBackupUtility.STANDARD_CLASS, 'STANDARD')


class TestBackupWorkflow(unittest.TestCase):
    """Integration tests for backup workflow."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_path = Path(self.temp_dir.name)
    
    def tearDown(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()
    
    def test_new_file_detection(self):
        """Test detection of new files."""
        # Create test file
        test_file = self.test_path / "new_file.txt"
        test_file.write_text("new content")
        
        with patch('backup_utility.storage.Client') as mock_client:
            mock_bucket = MagicMock()
            mock_client.return_value.bucket.return_value = mock_bucket
            
            # Mock index load (no previous index)
            mock_blob = MagicMock()
            mock_blob.exists.return_value = False
            mock_bucket.blob.return_value = mock_blob
            
            utility = GCPBackupUtility('test-bucket', str(self.test_path))
            
            with patch.object(utility, '_upload_file'):
                stats = utility.backup()
                
                self.assertEqual(stats['new_files'], 1)
                self.assertEqual(stats['modified_files'], 0)
                self.assertEqual(stats['skipped_files'], 0)


if __name__ == '__main__':
    unittest.main()
