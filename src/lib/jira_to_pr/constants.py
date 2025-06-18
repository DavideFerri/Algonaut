"""Constants and configuration for the Jira to PR automation system."""

from typing import List, Dict
from enum import Enum

class TicketPriority(str, Enum):
    """Jira ticket priority levels."""
    HIGHEST = "Highest"
    HIGH = "High"
    MEDIUM = "Medium"  
    LOW = "Low"
    LOWEST = "Lowest"

class TicketStatus(str, Enum):
    """Jira ticket status values."""
    TODO = "To Do"
    IN_PROGRESS = "In Progress"
    IN_REVIEW = "In Review"
    DONE = "Done"

class ProgrammingLanguage(str, Enum):
    """Supported programming languages for code generation."""
    PYTHON = "Python"
    JAVASCRIPT = "JavaScript"
    TYPESCRIPT = "TypeScript"
    JAVA = "Java"
    GO = "Go"
    RUST = "Rust"
    CPP = "C++"
    CSHARP = "C#"

# Priority mapping for ticket selection
PRIORITY_WEIGHTS: Dict[str, int] = {
    TicketPriority.HIGHEST: 5,
    TicketPriority.HIGH: 4,
    TicketPriority.MEDIUM: 3,
    TicketPriority.LOW: 2,
    TicketPriority.LOWEST: 1,
}

# Language detection patterns
LANGUAGE_PATTERNS: Dict[str, List[str]] = {
    ProgrammingLanguage.PYTHON: ["*.py", "requirements.txt", "pyproject.toml", "setup.py"],
    ProgrammingLanguage.JAVASCRIPT: ["*.js", "package.json", "*.jsx"],
    ProgrammingLanguage.TYPESCRIPT: ["*.ts", "*.tsx", "tsconfig.json"],
    ProgrammingLanguage.JAVA: ["*.java", "pom.xml", "build.gradle"],
    ProgrammingLanguage.GO: ["*.go", "go.mod", "go.sum"],
    ProgrammingLanguage.RUST: ["*.rs", "Cargo.toml", "Cargo.lock"],
    ProgrammingLanguage.CPP: ["*.cpp", "*.hpp", "*.h", "CMakeLists.txt"],
    ProgrammingLanguage.CSHARP: ["*.cs", "*.csproj", "*.sln"],
}

# Framework detection patterns
FRAMEWORK_PATTERNS: Dict[str, List[str]] = {
    "React": ["react", "@types/react"],
    "Vue": ["vue", "@vue/"],
    "Angular": ["@angular/", "angular"],
    "Django": ["django", "Django"],
    "Flask": ["flask", "Flask"],
    "Spring": ["spring-boot", "springframework"],
    "Express": ["express"],
    "FastAPI": ["fastapi"],
    "Next.js": ["next", "@next/"],
}

# Default settings
DEFAULT_MAX_TICKETS_PER_RUN = 5
DEFAULT_MAX_FILES_CHANGED = 10
DEFAULT_BRANCH_PREFIX = "feature/jira-"
DEFAULT_PR_TEMPLATE = """## Summary
{summary}

## Changes Made
{changes}

## Jira Ticket
- **ID**: {ticket_id}
- **Type**: {ticket_type}
- **Priority**: {ticket_priority}
- **Link**: {ticket_url}

## Test Plan
{test_plan}

🤖 Generated with Claude Code AI Assistant

Co-Authored-By: Claude AI <noreply@anthropic.com>
"""

# Safety limits
MAX_COMPLEXITY_THRESHOLD = 100
MAX_LINES_CHANGED = 1000
REQUIRE_HUMAN_REVIEW_KEYWORDS = [
    "database", "migration", "security", "authentication", "authorization",
    "payment", "billing", "admin", "sudo", "root", "production"
]