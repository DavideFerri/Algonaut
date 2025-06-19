# Jira to PR Automation

A LangGraph-based agent that automates the complete workflow from Jira ticket to GitHub PR creation using AI-powered code generation.

## Owner

**Mister X**

## Overview

This system:
1. 🎫 Connects to Jira and fetches unassigned tickets from the active sprint
2. 🎲 Randomly selects a ticket to work on (no priority-based selection)
3. 🔍 Analyzes all accessible GitHub repositories to determine relevance
4. 🤖 Uses Claude Code SDK to generate appropriate code changes
5. 🔧 Creates feature branches and commits changes
6. 📤 Opens pull requests with proper descriptions and linking
7. 🔄 Continues until max tickets processed or no more tickets available

## Architecture

The system follows the LangGraph pattern with these core components:

- **Graph Structure** (`graph.py`, `builder.py`) - Main workflow orchestration
- **State Management** (`models.py`) - Workflow state and data models
- **Node Functions** (`nodes.py`) - Core workflow operations
- **Conditional Edges** (`edges.py`) - Smart routing and decision making
- **Integrations** (`integrations.py`) - External API clients (Jira, GitHub, Claude)
- **Configuration** (`config.py`) - Settings management following project patterns

## Setup

### 1. Environment Variables

Create a `.env` file in the project root with the following variables:

```bash
# Required: Jira Configuration
JIRA_URL=https://your-company.atlassian.net
JIRA_EMAIL=your-email@company.com
JIRA_API_TOKEN=your-jira-api-token
JIRA_PROJECT_KEY=DEV

# Required: GitHub Configuration
GITHUB_TOKEN=ghp_your-github-token
GITHUB_ORG=your-organization

# Required: OpenAI Configuration
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-4o

# Optional: Claude API (for enhanced code generation)
ANTHROPIC_API_KEY=your-anthropic-api-key

# Optional: Workflow Configuration (defaults shown)
MAX_TICKETS_PER_RUN=5
MAX_REPOS_PER_TICKET=3
REQUIRE_HUMAN_REVIEW=true
DRY_RUN=false
BRANCH_PREFIX=feature/jira-
```

### 2. Install Dependencies

```bash
pip install -r src/lib/jira_to_pr/requirements.txt
```

### 3. Validate Setup

```bash
python -m src.lib.jira_to_pr.main --setup
```

## Usage

### Basic Usage

Run the automation with default settings:

```bash
python -m src.lib.jira_to_pr.main
```

### Advanced Usage

```bash
# Process up to 10 tickets
python -m src.lib.jira_to_pr.main --max-tickets 10

# Run in dry-run mode (no actual changes)
python -m src.lib.jira_to_pr.main --dry-run

# Skip human review requirement
python -m src.lib.jira_to_pr.main --no-review

# Process a specific ticket
python -m src.lib.jira_to_pr.main --ticket DEV-123
```

### Programmatic Usage

```python
import asyncio
from src.lib.jira_to_pr.main import run_jira_to_pr_automation

async def example():
    result = await run_jira_to_pr_automation(
        max_tickets=3,
        dry_run=True,
        require_human_review=True
    )
    
    if result["success"]:
        print(f"Processed {result['tickets_processed']} tickets")
        print(f"Created {result['prs_created']} PRs")
    else:
        print(f"Failed: {result['error']}")

asyncio.run(example())
```

## Docker Integration

The system integrates with the existing Docker setup. Add the Jira to PR variables to your `.env` file and the automation will be available within the container.

```yaml
# In docker-compose.yml, the automation is available in the app service
services:
  app:
    # ... existing configuration
    environment:
      # Add your Jira to PR variables here
```

## Workflow Details

### Ticket Selection
- Fetches all unassigned tickets from the active sprint
- Randomly selects one ticket (no priority-based filtering)
- Skips tickets labeled as 'tbd' or with recent comments from the system

### Repository Analysis
- Analyzes all accessible GitHub repositories
- Uses AI to determine relevance based on ticket description, components, and labels
- Selects top N repositories (configurable, default 3)

### Code Generation
- Uses Claude Code SDK for AI-powered code generation
- Follows existing code patterns and conventions
- Includes appropriate error handling and tests
- Creates feature branches following naming conventions

### Pull Request Creation
- Generates comprehensive PR descriptions
- Links back to Jira ticket
- Updates ticket status to "In Progress"
- Adds appropriate labels and metadata

### Quality Gates
- Automated complexity analysis
- Security pattern detection
- File size and change limits
- Optional human review requirements

## Safety Features

- **Dry Run Mode**: Test the workflow without making actual changes
- **Human Review Gates**: Complex changes can require manual review
- **File Restrictions**: Limits on file types, sizes, and dangerous paths
- **Branch Protection**: Works on feature branches, never directly on main
- **Rollback Capability**: Git-based, easy to revert changes

## Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_TICKETS_PER_RUN` | 5 | Maximum tickets to process per execution |
| `MAX_REPOS_PER_TICKET` | 3 | Maximum repositories to analyze per ticket |
| `REQUIRE_HUMAN_REVIEW` | true | Require human review for complex changes |
| `DRY_RUN` | false | Run without making actual changes |
| `BRANCH_PREFIX` | feature/jira- | Git branch naming prefix |
| `MAX_FILES_CHANGED` | 20 | Maximum files that can be modified |
| `MAX_LINES_CHANGED` | 1000 | Maximum lines of code that can be changed |

## Monitoring and Debugging

The system provides comprehensive logging and error handling:

```bash
# View logs
tail -f /tmp/logs/jira-to-pr.log

# Debug mode
DEBUG=true python -m src.lib.jira_to_pr.main
```

## Integration with Existing Project

This automation system follows the project's existing patterns:

- Uses `dependencies.settings` for configuration
- Follows the same Docker and environment setup
- Integrates with existing LangGraph infrastructure
- Uses the same logging and error handling patterns

## Troubleshooting

### Common Issues

1. **Configuration Errors**: Run `--setup` to validate your configuration
2. **API Rate Limits**: Reduce `MAX_TICKETS_PER_RUN` or add delays
3. **Repository Access**: Ensure GitHub token has appropriate permissions
4. **Jira Permissions**: Verify API token can read tickets and post comments

### Getting Help

1. Check the logs for detailed error messages
2. Run in `--dry-run` mode to test without changes
3. Use `--setup` to validate configuration
4. Review the sample environment file for required variables

## Future Enhancements

- Support for custom ticket filters and queries
- Integration with additional code review tools
- Advanced AI analysis for code quality
- Slack/Teams notifications for PR creation
- Integration with CI/CD pipelines for automated testing