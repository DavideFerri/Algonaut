"""Configuration utilities for the Jira to PR automation system.

This module provides configuration helpers that work with the main dependencies.settings.
"""

from typing import Dict, Any, List
from pathlib import Path

from dependencies.settings import settings


def validate_jira_to_pr_config() -> List[str]:
    """
    Validate configuration specific to Jira to PR automation.
    
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    # Check required environment variables
    required_vars = [
        ("JIRA_URL", settings.jira_url),
        ("JIRA_EMAIL", settings.jira_email),
        ("JIRA_API_TOKEN", settings.jira_api_token),
        ("GITHUB_TOKEN", settings.github_token),
        ("OPENAI_API_KEY", settings.openai_api_key),
    ]
    
    for var_name, var_value in required_vars:
        if not var_value:
            errors.append(f"Missing required environment variable: {var_name}")
    
    # Validate directory permissions
    directories = [
        settings.workspace_dir,
        settings.repos_dir,
        settings.cache_dir,
    ]
    
    for directory in directories:
        path = Path(directory)
        if not path.exists():
            try:
                path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                errors.append(f"Cannot create directory {directory}: {e}")
    
    # Validate workflow settings
    if settings.max_tickets_per_run < 1 or settings.max_tickets_per_run > 20:
        errors.append("MAX_TICKETS_PER_RUN must be between 1 and 20")
    
    if settings.max_repositories_per_ticket < 1 or settings.max_repositories_per_ticket > 10:
        errors.append("MAX_REPOS_PER_TICKET must be between 1 and 10")
    
    return errors


def get_jira_to_pr_config() -> Dict[str, Any]:
    """Get Jira to PR specific configuration."""
    return {
        "jira_url": settings.jira_url,
        "jira_project_key": settings.jira_project_key,
        "github_org": settings.github_org,
        "max_tickets_per_run": settings.max_tickets_per_run,
        "max_repositories_per_ticket": settings.max_repositories_per_ticket,
        "require_human_review": settings.require_human_review,
        "dry_run": settings.dry_run,
        "branch_prefix": settings.branch_prefix,
        "workspace_dir": settings.workspace_dir,
        "repos_dir": settings.repos_dir,
        "cache_dir": settings.cache_dir,
    }


def create_sample_env_file(file_path: str = ".env.jira-to-pr") -> None:
    """
    Create a sample environment file for Jira to PR automation.
    
    Args:
        file_path: Path to create the sample file
    """
    sample_content = """# Jira to PR Automation Configuration
# Add these variables to your main .env file

# Jira Configuration (Required)
JIRA_URL=https://your-company.atlassian.net
JIRA_EMAIL=your-email@company.com
JIRA_API_TOKEN=your-jira-api-token
JIRA_PROJECT_KEY=DEV
JIRA_BOARD_NAME=Development Board

# GitHub Configuration (Required)
GITHUB_TOKEN=ghp_your-github-token
GITHUB_ORG=your-organization
GITHUB_USER=your-username

# OpenAI Configuration (Required)
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-4o
OPENAI_TEMPERATURE=0.0

# Claude API Configuration (Optional - for enhanced code generation)
ANTHROPIC_API_KEY=your-anthropic-api-key
CLAUDE_MODEL=claude-3-sonnet-20240229

# Workflow Configuration (Optional - these have defaults)
MAX_TICKETS_PER_RUN=5
MAX_REPOS_PER_TICKET=3
REQUIRE_HUMAN_REVIEW=true
DRY_RUN=false
BRANCH_PREFIX=feature/jira-
REQUIRE_TESTS=true

# Security Configuration (Optional - these have defaults)
MAX_FILE_SIZE_MB=10
MAX_FILES_CHANGED=20
MAX_LINES_CHANGED=1000

# Storage Configuration (Optional - these have defaults)
WORKSPACE_DIR=/tmp/jira-to-pr
REPOS_DIR=/tmp/repos
CACHE_DIR=/tmp/cache
"""
    
    with open(file_path, 'w') as f:
        f.write(sample_content)
    
    print(f"Sample environment file created: {file_path}")
    print("Please copy these variables to your main .env file and update with your actual values.")