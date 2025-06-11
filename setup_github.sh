#!/bin/bash

# GitHub setup script for LoyaltyPro Analytics Dashboard
# Replace 'your-repo-name' with your actual repository name

echo "Setting up GitHub repository..."

# Initialize git repository
git init

# Add all files
git add .

# Create initial commit
git commit -m "Initial commit: LoyaltyPro Analytics Dashboard with Streamlit, Google Sheets, Jira integration, and AI-powered analysis"

# Add your GitHub repository as remote
git remote add origin https://github.com/prakarsh4195/TicketInsight.git
git branch -M main
git push -u origin main

echo "Code successfully pushed to https://github.com/prakarsh4195/TicketInsight"