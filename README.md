# 🚀 Algonaut - Jira to PR Automation

[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/LangGraph-powered-orange.svg)](https://github.com/langchain-ai/langgraph)
[![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A powerful LangGraph-based agent that automates the complete workflow from Jira ticket to GitHub PR creation using AI-powered code generation.

## 📋 Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Docker Support](#docker-support)
- [Workflow Details](#workflow-details)
- [Safety Features](#safety-features)
- [Monitoring & Debugging](#monitoring--debugging)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## 🎯 Overview

Algonaut revolutionizes your development workflow by automatically:

1. 🎫 **Fetching** unassigned tickets from your active Jira sprint
2. 🎲 **Selecting** tickets randomly for fair distribution
3. 🔍 **Analyzing** GitHub repositories to find the most relevant codebase
4. 🤖 **Generating** code changes using Claude AI
5. 🌿 **Creating** feature branches with proper naming conventions
6. 📤 **Opening** pull requests with comprehensive descriptions
7. 🔄 **Repeating** until all tickets are processed

## ✨ Key Features

- **AI-Powered Code Generation**: Leverages Claude AI for intelligent code creation
- **Smart Repository Selection**: Automatically identifies the right repositories for each ticket
- **Quality Gates**: Built-in complexity analysis and security checks
- **Human-in-the-Loop**: Optional review requirements for complex changes
- **Comprehensive Logging**: Detailed logging for debugging and monitoring
- **Docker Ready**: Seamless integration with containerized environments
- **Dry Run Mode**: Test workflows without making actual changes

## 🏗️ Architecture

The system is built using LangGraph with these core components:

```
├── graph.py        # Main workflow orchestration
├── builder.py      # Graph construction and configuration
├── models.py       # State management and data models
├── nodes.py        # Core workflow operations
├── edges.py        # Conditional routing logic
├── integrations.py # External API clients
└── config.py       # Configuration management
```

### Component Details

- **Graph Structure**: Orchestrates the entire workflow using LangGraph patterns
- **State Management**: Maintains workflow state throughout the process
- **Node Functions**: Individual operations (fetch tickets, generate code, create PR)
- **Conditional Edges**: Smart routing based on workflow conditions
- **Integrations**: Clean interfaces to Jira, GitHub, and AI services

## 📦 Prerequisites

- Python 3.8 or higher
- Docker (optional, for containerized deployment)
- Access to:
  - Jira instance with API access
  - GitHub account with repository access
  - OpenAI API key
  - Claude API key (optional, for enhanced code generation)

## 🛠️ Installation

### Option 1: Local Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/DavideFerri/Algonaut.git
   cd Algonaut
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r src/lib/jira_to_pr/requirements.txt
   ```

### Option 2: Docker Installation

```bash
docker-compose up -d
```

## ⚙️ Configuration

### 1. Environment Variables

Create a `.env` file in the project root:

```bash
# === REQUIRED CONFIGURATIONS ===

# Jira Configuration
JIRA_URL=https://your-company.atlassian.net
JIRA_EMAIL=your-email@company.com
JIRA_API_TOKEN=your-jira-api-token        # Generate at: https://id.atlassian.com/manage/api-tokens
JIRA_PROJECT_KEY=DEV                      # Your project key (e.g., DEV, PROJ, etc.)

# GitHub Configuration
GITHUB_TOKEN=ghp_your-github-token        # Generate at: https://github.com/settings/tokens
GITHUB_ORG=your-organization              # Your GitHub organization or username

# OpenAI Configuration
OPENAI_API_KEY=sk-your-openai-api-key    # Get from: https://platform.openai.com/api-keys
OPENAI_MODEL=gpt-4o                       # Options: gpt-4o, gpt-4-turbo, gpt-3.5-turbo

# === OPTIONAL CONFIGURATIONS ===

# Claude API (for enhanced code generation)
ANTHROPIC_API_KEY=sk-ant-your-key        # Get from: https://console.anthropic.com/

# Workflow Configuration
MAX_TICKETS_PER_RUN=5                     # Maximum tickets to process per execution
MAX_REPOS_PER_TICKET=3                    # Maximum repositories to analyze per ticket
REQUIRE_HUMAN_REVIEW=true                 # Require human review for complex changes
DRY_RUN=false                            # Run without making actual changes
BRANCH_PREFIX=feature/jira-               # Git branch naming prefix

# Advanced Configuration
MAX_FILES_CHANGED=20                      # Maximum files that can be modified
MAX_LINES_CHANGED=1000                    # Maximum lines of code that can be changed
COMPLEXITY_THRESHOLD=8                    # Code complexity threshold (1-10)
```

### 2. Validate Your Setup

```bash
python -m src.lib.jira_to_pr.main --setup
```

This command will:
- ✅ Verify all required environment variables
- ✅ Test API connections
- ✅ Check permissions
- ✅ Display configuration summary

## 🚀 Usage

### Basic Usage

Run the automation with default settings:

```bash
python -m src.lib.jira_to_pr.main
```

### Command Line Options

```bash
# Process specific number of tickets
python -m src.lib.jira_to_pr.main --max-tickets 10

# Run in dry-run mode (no actual changes)
python -m src.lib.jira_to_pr.main --dry-run

# Skip human review requirement
python -m src.lib.jira_to_pr.main --no-review

# Process a specific ticket
python -m src.lib.jira_to_pr.main --ticket DEV-123

# Verbose output for debugging
python -m src.lib.jira_to_pr.main --verbose

# Combine options
python -m src.lib.jira_to_pr.main --max-tickets 3 --dry-run --verbose
```

### Programmatic Usage

```python
import asyncio
from src.lib.jira_to_pr.main import run_jira_to_pr_automation

async def example():
    # Basic usage
    result = await run_jira_to_pr_automation()
    
    # With options
    result = await run_jira_to_pr_automation(
        max_tickets=3,
        dry_run=True,
        require_human_review=True,
        specific_ticket="DEV-123"
    )
    
    # Process results
    if result["success"]:
        print(f"✅ Processed {result['tickets_processed']} tickets")
        print(f"📤 Created {result['prs_created']} PRs")
        
        for pr in result["pull_requests"]:
            print(f"  - {pr['title']} ({pr['url']})")
    else:
        print(f"❌ Failed: {result['error']}")
        print(f"📋 Details: {result.get('details', 'No additional details')}")

# Run the example
asyncio.run(example())
```

### Integration Example

```python
from src.lib.jira_to_pr import JiraToPRAutomation

# Create automation instance
automation = JiraToPRAutomation(
    jira_url="https://company.atlassian.net",
    github_org="my-org",
    max_tickets=5
)

# Run with custom filters
results = await automation.run(
    jira_filter="project = DEV AND sprint in openSprints()",
    repository_filter=lambda repo: "backend" in repo.name,
    code_review_enabled=True
)
```

## 🐳 Docker Support

### Using Docker Compose

1. **Update your `.env` file** with all required variables

2. **Build and run**:
   ```bash
   docker-compose up --build
   ```

3. **Run automation inside container**:
   ```bash
   docker-compose exec app python -m src.lib.jira_to_pr.main
   ```

### Custom Dockerfile

```dockerfile
FROM python:3.9-slim

WORKDIR /app

# Copy requirements
COPY src/lib/jira_to_pr/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Run automation
CMD ["python", "-m", "src.lib.jira_to_pr.main"]
```

## 📊 Workflow Details

### 1. Ticket Selection Process
- Fetches all unassigned tickets from the active sprint
- Filters out tickets with 'tbd' labels
- Skips tickets with recent bot comments
- Randomly selects from eligible tickets

### 2. Repository Analysis
- Scans all accessible GitHub repositories
- Uses AI to analyze relevance based on:
  - Ticket description and components
  - Repository languages and topics
  - Recent commit activity
  - File structure patterns

### 3. Code Generation
- Leverages Claude AI for intelligent code generation
- Follows existing code patterns and conventions
- Includes appropriate error handling
- Generates relevant tests when applicable
- Respects project-specific guidelines

### 4. Pull Request Creation
- Creates feature branches with consistent naming
- Generates comprehensive PR descriptions including:
  - Summary of changes
  - Link to Jira ticket
  - Test plan
  - Screenshots (if applicable)
- Applies appropriate labels
- Updates Jira ticket status

## 🛡️ Safety Features

### Built-in Protections

- **Dry Run Mode**: Test workflows without making changes
- **File Restrictions**: Prevents modification of sensitive files
- **Size Limits**: Restricts large changes that need human review
- **Branch Protection**: Never modifies main/master directly
- **Rollback Capability**: All changes are in Git, easy to revert

### Security Patterns Detection

The system automatically detects and flags:
- Hardcoded credentials
- SQL injection vulnerabilities
- Cross-site scripting (XSS) risks
- Sensitive data exposure
- Insecure dependencies

## 📈 Monitoring & Debugging

### Logging

Comprehensive logging is available at multiple levels:

```bash
# View real-time logs
tail -f /tmp/logs/jira-to-pr.log

# Filter by severity
grep ERROR /tmp/logs/jira-to-pr.log

# Debug mode for verbose output
DEBUG=true python -m src.lib.jira_to_pr.main
```

### Metrics

The system tracks:
- Tickets processed per run
- Success/failure rates
- Average processing time
- Code complexity scores
- API usage statistics

### Health Checks

```bash
# Check system health
python -m src.lib.jira_to_pr.main --health-check

# Verify external connections
python -m src.lib.jira_to_pr.main --test-connections
```

## 🔧 Troubleshooting

### Common Issues and Solutions

#### 1. Configuration Errors
```bash
Error: Missing required environment variable: JIRA_URL
```
**Solution**: Ensure all required variables are set in your `.env` file

#### 2. API Rate Limits
```bash
Error: GitHub API rate limit exceeded
```
**Solution**: 
- Reduce `MAX_TICKETS_PER_RUN`
- Add delays between operations
- Use a GitHub App for higher limits

#### 3. Repository Access Issues
```bash
Error: Repository not found or access denied
```
**Solution**: 
- Verify GitHub token permissions
- Ensure token has `repo` scope
- Check organization membership

#### 4. Jira Permission Errors
```bash
Error: Unauthorized access to Jira
```
**Solution**:
- Regenerate Jira API token
- Verify email matches Jira account
- Check project permissions

### Debug Commands

```bash
# Test Jira connection
python -m src.lib.jira_to_pr.main --test-jira

# Test GitHub connection
python -m src.lib.jira_to_pr.main --test-github

# List available tickets
python -m src.lib.jira_to_pr.main --list-tickets

# Analyze specific repository
python -m src.lib.jira_to_pr.main --analyze-repo owner/repo
```

### Getting Help

1. 📖 Check the [documentation](docs/)
2. 🐛 Search [existing issues](https://github.com/DavideFerri/Algonaut/issues)
3. 💬 Join our [Discord community](https://discord.gg/algonaut)
4. 📧 Contact support: support@algonaut.dev

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

```bash
# Clone the repository
git clone https://github.com/DavideFerri/Algonaut.git
cd Algonaut

# Install development dependencies
pip install -r requirements-dev.txt

# Run tests
pytest tests/

# Run linting
flake8 src/
black src/ --check
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

<p align="center">
  Made with ❤️ by the Algonaut Team
</p>

<p align="center">
  <a href="https://github.com/DavideFerri/Algonaut">GitHub</a> •
  <a href="https://algonaut.dev">Website</a> •
  <a href="https://docs.algonaut.dev">Documentation</a>
</p>