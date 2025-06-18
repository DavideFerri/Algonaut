"""Utility functions and helper methods for the Jira to PR automation system."""

import os
import re
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import subprocess
import logging

from .models import TicketData, RepositoryInfo, CodeChange
from .constants import ProgrammingLanguage, LANGUAGE_PATTERNS, FRAMEWORK_PATTERNS


# Logging setup
logger = logging.getLogger(__name__)


class GitUtils:
    """Utilities for Git operations."""
    
    @staticmethod
    def clone_repository(repo_url: str, local_path: str, branch: str = "main") -> bool:
        """
        Clone a repository to local path.
        
        Args:
            repo_url: Repository clone URL
            local_path: Local path to clone to
            branch: Branch to checkout (default: main)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if Path(local_path).exists():
                logger.info(f"Repository already exists at {local_path}")
                return True
            
            cmd = ["git", "clone", "-b", branch, repo_url, local_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"Successfully cloned {repo_url} to {local_path}")
                return True
            else:
                logger.error(f"Failed to clone repository: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error cloning repository: {e}")
            return False
    
    @staticmethod
    def create_branch(repo_path: str, branch_name: str, base_branch: str = "main") -> bool:
        """
        Create and switch to a new branch.
        
        Args:
            repo_path: Path to the repository
            branch_name: Name of the new branch
            base_branch: Base branch to create from
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Change to repository directory
            original_cwd = os.getcwd()
            os.chdir(repo_path)
            
            # Fetch latest changes
            subprocess.run(["git", "fetch", "origin"], check=True)
            
            # Switch to base branch and pull
            subprocess.run(["git", "checkout", base_branch], check=True)
            subprocess.run(["git", "pull", "origin", base_branch], check=True)
            
            # Create and switch to new branch
            subprocess.run(["git", "checkout", "-b", branch_name], check=True)
            
            logger.info(f"Created and switched to branch {branch_name}")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Git command failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Error creating branch: {e}")
            return False
        finally:
            os.chdir(original_cwd)
    
    @staticmethod
    def commit_changes(repo_path: str, message: str, files: Optional[List[str]] = None) -> bool:
        """
        Commit changes to the repository.
        
        Args:
            repo_path: Path to the repository
            message: Commit message
            files: Specific files to commit (None for all changes)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            original_cwd = os.getcwd()
            os.chdir(repo_path)
            
            # Add files
            if files:
                for file in files:
                    subprocess.run(["git", "add", file], check=True)
            else:
                subprocess.run(["git", "add", "."], check=True)
            
            # Check if there are changes to commit
            result = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True)
            if result.returncode == 0:
                logger.info("No changes to commit")
                return True
            
            # Commit changes
            subprocess.run(["git", "commit", "-m", message], check=True)
            
            logger.info(f"Successfully committed changes: {message}")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Git commit failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Error committing changes: {e}")
            return False
        finally:
            os.chdir(original_cwd)
    
    @staticmethod
    def push_branch(repo_path: str, branch_name: str) -> bool:
        """
        Push branch to remote repository.
        
        Args:
            repo_path: Path to the repository
            branch_name: Name of the branch to push
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            original_cwd = os.getcwd()
            os.chdir(repo_path)
            
            # Push branch
            subprocess.run(["git", "push", "-u", "origin", branch_name], check=True)
            
            logger.info(f"Successfully pushed branch {branch_name}")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Git push failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Error pushing branch: {e}")
            return False
        finally:
            os.chdir(original_cwd)


class RepositoryAnalyzer:
    """Utilities for analyzing repository characteristics."""
    
    @staticmethod
    def detect_primary_language(repo_path: str) -> Optional[ProgrammingLanguage]:
        """
        Detect the primary programming language of a repository.
        
        Args:
            repo_path: Path to the repository
            
        Returns:
            ProgrammingLanguage or None if not detected
        """
        if not Path(repo_path).exists():
            return None
        
        language_scores = {}
        
        # Count files for each language
        for lang, patterns in LANGUAGE_PATTERNS.items():
            score = 0
            for pattern in patterns:
                matching_files = list(Path(repo_path).rglob(pattern))
                score += len(matching_files)
            
            if score > 0:
                language_scores[lang] = score
        
        if not language_scores:
            return None
        
        # Return the language with the highest score
        primary_lang = max(language_scores, key=language_scores.get)
        return ProgrammingLanguage(primary_lang)
    
    @staticmethod
    def detect_frameworks(repo_path: str) -> List[str]:
        """
        Detect frameworks used in the repository.
        
        Args:
            repo_path: Path to the repository
            
        Returns:
            List of detected framework names
        """
        frameworks = []
        repo_path = Path(repo_path)
        
        # Check package.json for JavaScript frameworks
        package_json = repo_path / "package.json"
        if package_json.exists():
            try:
                with open(package_json, 'r') as f:
                    data = json.load(f)
                    dependencies = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                    
                    for framework, patterns in FRAMEWORK_PATTERNS.items():
                        if any(pattern in dependencies for pattern in patterns):
                            frameworks.append(framework)
            except Exception as e:
                logger.warning(f"Error reading package.json: {e}")
        
        # Check requirements.txt for Python frameworks
        requirements_txt = repo_path / "requirements.txt"
        if requirements_txt.exists():
            try:
                with open(requirements_txt, 'r') as f:
                    content = f.read().lower()
                    
                    for framework, patterns in FRAMEWORK_PATTERNS.items():
                        if any(pattern.lower() in content for pattern in patterns):
                            frameworks.append(framework)
            except Exception as e:
                logger.warning(f"Error reading requirements.txt: {e}")
        
        # Check for other framework indicators
        if (repo_path / "Dockerfile").exists():
            frameworks.append("Docker")
        
        if (repo_path / "docker-compose.yml").exists() or (repo_path / "docker-compose.yaml").exists():
            frameworks.append("Docker Compose")
        
        return list(set(frameworks))  # Remove duplicates
    
    @staticmethod
    def get_repository_stats(repo_path: str) -> Dict[str, Any]:
        """
        Get various statistics about the repository.
        
        Args:
            repo_path: Path to the repository
            
        Returns:
            Dictionary containing repository statistics
        """
        stats = {
            "total_files": 0,
            "total_lines": 0,
            "languages": {},
            "has_tests": False,
            "has_ci": False,
            "has_docs": False,
            "complexity_score": 0
        }
        
        repo_path = Path(repo_path)
        if not repo_path.exists():
            return stats
        
        # Count files and lines
        code_extensions = {'.py', '.js', '.ts', '.java', '.go', '.rs', '.cpp', '.hpp', '.h', '.cs'}
        
        for file_path in repo_path.rglob("*"):
            if file_path.is_file() and not any(part.startswith('.') for part in file_path.parts):
                stats["total_files"] += 1
                
                if file_path.suffix in code_extensions:
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            lines = len(f.readlines())
                            stats["total_lines"] += lines
                            
                            # Count by language
                            lang = file_path.suffix
                            stats["languages"][lang] = stats["languages"].get(lang, 0) + lines
                    except Exception:
                        pass
        
        # Check for tests
        test_indicators = ["test", "tests", "spec", "__tests__"]
        stats["has_tests"] = any(
            any(indicator in part.lower() for indicator in test_indicators)
            for file_path in repo_path.rglob("*")
            for part in file_path.parts
        )
        
        # Check for CI
        ci_files = [".github/workflows", ".gitlab-ci.yml", "Jenkinsfile", ".travis.yml"]
        stats["has_ci"] = any((repo_path / ci_file).exists() for ci_file in ci_files)
        
        # Check for documentation
        doc_files = ["README.md", "README.rst", "docs", "documentation"]
        stats["has_docs"] = any((repo_path / doc_file).exists() for doc_file in doc_files)
        
        # Calculate complexity score (simple heuristic)
        stats["complexity_score"] = min(stats["total_lines"] // 1000, 10)
        
        return stats


class TextUtils:
    """Utilities for text processing and formatting."""
    
    @staticmethod
    def sanitize_branch_name(name: str) -> str:
        """
        Sanitize a string to be a valid Git branch name.
        
        Args:
            name: Input string
            
        Returns:
            Sanitized branch name
        """
        # Replace invalid characters with hyphens
        sanitized = re.sub(r'[^a-zA-Z0-9\-_]', '-', name)
        
        # Remove multiple consecutive hyphens
        sanitized = re.sub(r'-+', '-', sanitized)
        
        # Remove leading/trailing hyphens
        sanitized = sanitized.strip('-')
        
        # Ensure it's not empty and not too long
        if not sanitized:
            sanitized = "feature"
        
        return sanitized[:50].lower()  # Limit length
    
    @staticmethod
    def extract_ticket_id_from_text(text: str) -> Optional[str]:
        """
        Extract Jira ticket ID from text using common patterns.
        
        Args:
            text: Input text
            
        Returns:
            Extracted ticket ID or None
        """
        # Common Jira ticket patterns
        patterns = [
            r'\b([A-Z]{2,10}-\d+)\b',  # Standard format: PROJ-123
            r'\b([A-Z]+\d+)\b',        # Alternative format: PROJ123
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        
        return None
    
    @staticmethod
    def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
        """
        Truncate text to maximum length with suffix.
        
        Args:
            text: Input text
            max_length: Maximum length
            suffix: Suffix to add when truncated
            
        Returns:
            Truncated text
        """
        if len(text) <= max_length:
            return text
        
        return text[:max_length - len(suffix)] + suffix
    
    @staticmethod
    def format_duration(seconds: float) -> str:
        """
        Format duration in seconds to human-readable string.
        
        Args:
            seconds: Duration in seconds
            
        Returns:
            Formatted duration string
        """
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}m"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}h"


class ValidationUtils:
    """Utilities for validation and safety checks."""
    
    @staticmethod
    def validate_ticket_data(ticket: TicketData) -> List[str]:
        """
        Validate ticket data for completeness and correctness.
        
        Args:
            ticket: TicketData object to validate
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        if not ticket.key:
            errors.append("Ticket key is required")
        
        if not ticket.summary:
            errors.append("Ticket summary is required")
        
        if not ticket.project_key:
            errors.append("Project key is required")
        
        if not ticket.reporter:
            errors.append("Reporter is required")
        
        # Validate ticket key format
        if ticket.key and not re.match(r'^[A-Z]{2,10}-\d+$', ticket.key):
            errors.append("Invalid ticket key format")
        
        return errors
    
    @staticmethod
    def validate_repository_info(repo: RepositoryInfo) -> List[str]:
        """
        Validate repository information.
        
        Args:
            repo: RepositoryInfo object to validate
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        if not repo.name:
            errors.append("Repository name is required")
        
        if not repo.full_name:
            errors.append("Repository full name is required")
        
        if not repo.url:
            errors.append("Repository URL is required")
        
        if not repo.clone_url:
            errors.append("Repository clone URL is required")
        
        return errors
    
    @staticmethod
    def is_safe_file_path(file_path: str) -> bool:
        """
        Check if a file path is safe for operations.
        
        Args:
            file_path: File path to check
            
        Returns:
            bool: True if safe, False otherwise
        """
        # Check for path traversal attempts
        if ".." in file_path:
            return False
        
        # Check for absolute paths (should be relative)
        if os.path.isabs(file_path):
            return False
        
        # Check for dangerous patterns
        dangerous_patterns = [
            "/etc/", "/usr/", "/bin/", "/sbin/", "/root/",
            "~", "$HOME", "%USERPROFILE%"
        ]
        
        for pattern in dangerous_patterns:
            if pattern in file_path:
                return False
        
        return True
    
    @staticmethod
    def check_file_size_limit(file_path: str, max_size_mb: int = 10) -> bool:
        """
        Check if file size is within limits.
        
        Args:
            file_path: Path to file
            max_size_mb: Maximum size in MB
            
        Returns:
            bool: True if within limit, False otherwise
        """
        try:
            if Path(file_path).exists():
                size_mb = Path(file_path).stat().st_size / (1024 * 1024)
                return size_mb <= max_size_mb
            return True  # Non-existent files are okay
        except Exception:
            return False


class CacheUtils:
    """Utilities for caching and memoization."""
    
    @staticmethod
    def generate_cache_key(*args) -> str:
        """
        Generate a cache key from arguments.
        
        Args:
            *args: Arguments to generate key from
            
        Returns:
            Cache key string
        """
        key_string = "|".join(str(arg) for arg in args)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    @staticmethod
    def is_cache_valid(cache_file: str, max_age_hours: int = 24) -> bool:
        """
        Check if cache file is still valid.
        
        Args:
            cache_file: Path to cache file
            max_age_hours: Maximum age in hours
            
        Returns:
            bool: True if valid, False otherwise
        """
        cache_path = Path(cache_file)
        if not cache_path.exists():
            return False
        
        age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
        return age < timedelta(hours=max_age_hours)


def setup_logging(level: str = "INFO", log_file: Optional[str] = None) -> None:
    """
    Set up logging configuration.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional log file path
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    
    handlers = [console_handler]
    
    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        handlers=handlers,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )