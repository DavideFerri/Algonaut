"""Settings and configuration for the Jira to PR automation system."""

import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings following the existing project pattern."""
    
    # Environment
    public_env: str = Field(default="dev", env="PUBLIC_ENV")
    
    # API Keys
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    github_token: str = Field(..., env="GITHUB_TOKEN")
    jira_url: str = Field(..., env="JIRA_URL") 
    jira_email: str = Field(..., env="JIRA_EMAIL")
    jira_api_token: str = Field(..., env="JIRA_API_TOKEN")
    
    # Optional Claude/Anthropic API
    anthropic_api_key: Optional[str] = Field(None, env="ANTHROPIC_API_KEY")
    
    # Jira Configuration
    jira_project_key: str = Field(default="DEV", env="JIRA_PROJECT_KEY")
    jira_board_name: Optional[str] = Field(None, env="JIRA_BOARD_NAME")
    
    # GitHub Configuration  
    github_org: Optional[str] = Field(None, env="GITHUB_ORG")
    github_user: Optional[str] = Field(None, env="GITHUB_USER")
    
    # Git Configuration for automated commits
    git_user_name: str = Field(default="Jira-to-PR Automation", env="GIT_USER_NAME")
    git_user_email: str = Field(default="automation@company.com", env="GIT_USER_EMAIL")
    
    # Workflow Settings
    max_tickets_per_run: int = Field(default=5, env="MAX_TICKETS_PER_RUN")
    max_repositories_per_ticket: int = Field(default=3, env="MAX_REPOS_PER_TICKET") 
    require_human_review: bool = Field(default=True, env="REQUIRE_HUMAN_REVIEW")
    dry_run: bool = Field(default=False, env="DRY_RUN")
    branch_prefix: str = Field(default="feature/jira-", env="BRANCH_PREFIX")
    
    # Security Settings
    max_file_size_mb: int = Field(default=10, env="MAX_FILE_SIZE_MB")
    max_files_changed: int = Field(default=20, env="MAX_FILES_CHANGED")
    max_lines_changed: int = Field(default=1000, env="MAX_LINES_CHANGED")
    require_tests: bool = Field(default=True, env="REQUIRE_TESTS")
    
    # Storage Settings (following Docker patterns)
    workspace_dir: str = Field(default="/tmp/jira-to-pr", env="WORKSPACE_DIR")
    repos_dir: str = Field(default="/tmp/repos", env="REPOS_DIR")
    cache_dir: str = Field(default="/tmp/cache", env="CACHE_DIR")
    
    # Model Configuration
    openai_model: str = Field(default="gpt-4o", env="OPENAI_MODEL")
    openai_temperature: float = Field(default=0.0, env="OPENAI_TEMPERATURE")
    claude_model: str = Field(default="claude-3-sonnet-20240229", env="CLAUDE_MODEL")
    
    # Application Configuration
    debug: bool = Field(default=False, env="DEBUG")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_dir: str = Field(default="/tmp/logs", env="LOG_DIR")
    pythonpath: str = Field(default="/usr/app", env="PYTHONPATH")
    
    # Extended Workflow Configuration
    max_repos_per_ticket: int = Field(default=3, env="MAX_REPOS_PER_TICKET")
    auto_assign_pr: bool = Field(default=False, env="AUTO_ASSIGN_PR")
    
    # Extended Security Configuration
    allowed_file_extensions: str = Field(default=".py,.js,.ts,.java,.go,.rs,.cpp,.h,.hpp,.cs", env="ALLOWED_FILE_EXTENSIONS")
    forbidden_paths: str = Field(default="/etc/,/usr/,/bin/,/sbin/,/root/,.env,.secret", env="FORBIDDEN_PATHS")
    
    # Extended Storage Configuration
    cache_ttl_hours: int = Field(default=24, env="CACHE_TTL_HOURS")
    cleanup_on_exit: bool = Field(default=True, env="CLEANUP_ON_EXIT")

    path_to_local_repos: str = Field(env="PATH_TO_LOCAL_REPOS")
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance (following the pattern from the example)
settings = Settings()