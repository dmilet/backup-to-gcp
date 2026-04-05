#!/bin/bash

# GCP Backup Utility Setup Script
# This script helps set up the GCP Backup Utility with proper authentication

set -e

echo "=== GCP Backup Utility Setup ==="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

echo "✓ Python 3 found: $(python3 --version)"
echo ""

# Check if gcloud CLI is installed
if ! command -v gcloud &> /dev/null; then
    echo "Warning: gcloud CLI is not installed"
    echo "Please install it from: https://cloud.google.com/sdk/docs/install"
    echo ""
fi

# Install dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt
echo "✓ Dependencies installed"
echo ""

# Get GCP project ID
echo "Enter your GCP Project ID (or press Enter to auto-detect):"
read -r PROJECT_ID

# Create config file
echo ""
echo "Enter the GCS bucket name (must already exist):"
read -r BUCKET_NAME

echo "Enter the local directory path to backup:"
read -r LOCAL_PATH

# Validate local path
if [ ! -d "$LOCAL_PATH" ]; then
    echo "Error: Local path does not exist: $LOCAL_PATH"
    exit 1
fi

# Set up authentication
echo ""
echo "=== Authentication Setup ==="
echo ""
echo "Choose authentication method:"
echo "1. Service Account (recommended for production)"
echo "2. User credentials (gcloud auth application-default login)"
read -r AUTH_METHOD

if [ "$AUTH_METHOD" = "1" ]; then
    echo ""
    echo "Enter path to your service account JSON key file:"
    read -r KEY_FILE
    
    if [ ! -f "$KEY_FILE" ]; then
        echo "Error: Key file not found: $KEY_FILE"
        exit 1
    fi
    
    export GOOGLE_APPLICATION_CREDENTIALS="$KEY_FILE"
    echo "✓ GOOGLE_APPLICATION_CREDENTIALS set to: $KEY_FILE"
    
elif [ "$AUTH_METHOD" = "2" ]; then
    echo ""
    echo "Running gcloud authentication..."
    gcloud auth application-default login
    echo "✓ Authentication complete"
else
    echo "Invalid selection"
    exit 1
fi

# Test the setup
echo ""
echo "=== Testing Setup ==="
echo ""

PYTHON_CMD="python3 backup_utility.py"

if [ -n "$PROJECT_ID" ]; then
    PYTHON_CMD="$PYTHON_CMD --project-id $PROJECT_ID"
fi

# Test with a small number of files
echo "Testing backup with: $BUCKET_NAME"
echo "Local path: $LOCAL_PATH"
echo ""

if $PYTHON_CMD "$BUCKET_NAME" "$LOCAL_PATH" --force; then
    echo ""
    echo "✓ Setup successful!"
    echo ""
    echo "You can now run backups with:"
    echo "  python3 backup_utility.py $BUCKET_NAME $LOCAL_PATH"
    echo ""
    echo "Next steps:"
    echo "1. Copy config.template to config.sh and customize it"
    echo "2. Set up a cron job or task scheduler for automated backups"
    echo "3. See README.md for detailed documentation"
else
    echo ""
    echo "✗ Setup test failed"
    echo "Please check the error messages above"
    exit 1
fi
