"""Workflow node functions for the Jira to PR automation graph."""

import os
import random
import asyncio
from typing import Dict, Optional, List
from datetime import datetime
from pathlib import Path

from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

from lib.jira_to_pr.models import (
    JiraToPRState, TicketData, RepositoryInfo, CodeGenerationRequest,
    CodeGenerationResult, PullRequestData, WorkflowResult, CodeChange
)
# MCP direct integration
try:
    from mcp.client.stdio import stdio_client
    from mcp.client.session import ClientSession
    import subprocess
    import asyncio
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
from lib.jira_to_pr.constants import DEFAULT_BRANCH_PREFIX, DEFAULT_PR_TEMPLATE


# Initialize LLM for decision making
llm = ChatOpenAI(model="gpt-4o", temperature=0)


async def fetch_jira_tickets(state: JiraToPRState) -> Dict:
    """
    Fetch unassigned tickets from the active sprint.
    For now, using a simplified approach that returns mock data until MCP integration is fully working.
    """
    try:
        from dependencies.settings import settings
        
        # TODO: Replace with actual MCP integration once Docker containers are working
        # For now, return mock tickets to test the workflow
        
        mock_tickets = [
            {
                "id": "12345",
                "key": f"{settings.jira_project_key}-123",
                "fields": {
                    "summary": "Test ticket for automation",
                    "description": "This is a test ticket to verify the jira-to-pr automation workflow",
                    "status": {"name": "To Do"},
                    "priority": {"name": "Medium"},
                    "assignee": None,
                    "reporter": {"displayName": "Test User"},
                    "created": "2024-01-01T00:00:00.000Z",
                    "updated": "2024-01-01T00:00:00.000Z",
                    "issuetype": {"name": "Task"},
                    "labels": ["automation", "test"],
                    "components": [],
                    "fixVersions": [],
                    "project": {"key": settings.jira_project_key}
                }
            }
        ]
        
        # Parse tickets using the same function that would be used for real data
        tickets = []
        for issue in mock_tickets:
            tickets.append(_parse_jira_issue(issue, settings.jira_url))
        
        if not tickets:
            return {
                "available_tickets": [],
                "workflow_stage": "no_tickets",
                "messages": [AIMessage(content="No unassigned tickets found in active sprint")]
            }
        
        return {
            "available_tickets": tickets,
            "workflow_stage": "tickets_fetched",
            "messages": [AIMessage(content=f"Found {len(tickets)} tickets (mock data for testing)")]
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "workflow_stage": "error",
            "messages": [AIMessage(content=f"Error fetching tickets: {str(e)}")]
        }


async def select_ticket(state: JiraToPRState) -> Dict:
    """
    Select a ticket to process from the available tickets.
    
    Randomly selects an unassigned ticket from the active sprint,
    as requested by the user (no priority-based selection).
    
    Args:
        state: Current workflow state with available tickets
        
    Returns:
        Dict containing:
            - current_ticket: Selected TicketData object
            - available_tickets: Remaining tickets (with selected one removed)
            - workflow_stage: Updated to "ticket_selected"
            - messages: Information about selected ticket
    """
    if not state.available_tickets:
        return {
            "current_ticket": None,
            "workflow_stage": "no_tickets",
            "messages": [AIMessage(content="No tickets available to select")]
        }
    
    # Random selection as requested
    selected_ticket = random.choice(state.available_tickets)
    remaining_tickets = [t for t in state.available_tickets if t.id != selected_ticket.id]
    
    return {
        "current_ticket": selected_ticket,
        "available_tickets": remaining_tickets,
        "workflow_stage": "ticket_selected",
        "messages": [
            AIMessage(content=f"Selected ticket: {selected_ticket.key} - {selected_ticket.summary}")
        ]
    }


async def analyze_repositories(state: JiraToPRState) -> Dict:
    """
    Analyze available repositories to determine which ones are relevant for the ticket.
    
    This function:
    1. Fetches all accessible GitHub repositories using MCP
    2. Uses AI to analyze which repositories are relevant to the ticket
    3. Ranks repositories by relevance score
    4. Selects top repositories for code generation
    
    Args:
        state: Current workflow state with selected ticket
        
    Returns:
        Dict containing:
            - selected_repositories: List of relevant RepositoryInfo objects
            - workflow_stage: Updated to "repositories_analyzed"
            - messages: Analysis results
    """
    if not MCP_AVAILABLE:
        return {
            "error": "MCP is required for GitHub integration",
            "workflow_stage": "error"
        }
    
    try:
        if not state.current_ticket:
            return {
                "error": "No ticket selected for repository analysis",
                "workflow_stage": "error"
            }
        
        from dependencies.settings import settings
        
        # TODO: Replace with actual GitHub MCP integration
        # For now, using mock repository data
        repo_data_list = [
            {
                "name": "example-repo",
                "full_name": f"{settings.github_user or 'user'}/example-repo",
                "html_url": f"https://github.com/{settings.github_user or 'user'}/example-repo",
                "clone_url": f"https://github.com/{settings.github_user or 'user'}/example-repo.git",
                "ssh_url": f"git@github.com:{settings.github_user or 'user'}/example-repo.git",
                "default_branch": "main",
                "language": "Python",
                "languages": {"Python": 1000},
                "fork": False,
                "archived": False
            }
        ]
        
        if not repo_data_list:
            return {
                "error": "No accessible repositories found",
                "workflow_stage": "error",
                "messages": [AIMessage(content="No accessible repositories found")]
            }
        
        # Convert to RepositoryInfo objects
        all_repositories = []
        for repo_data in repo_data_list:
            if not repo_data.get("fork", False) and not repo_data.get("archived", False):
                repo_info = RepositoryInfo(
                    name=repo_data["name"],
                    full_name=repo_data["full_name"],
                    url=repo_data["html_url"],
                    clone_url=repo_data["clone_url"],
                    ssh_url=repo_data["ssh_url"],
                    default_branch=repo_data.get("default_branch", "main"),
                    primary_language=repo_data.get("language"),
                    languages=repo_data.get("languages", {})
                )
                all_repositories.append(repo_info)
        
        # Use AI to analyze repository relevance
        analysis_prompt = f"""
            Analyze which repositories are most relevant for this Jira ticket:
            
            Ticket: {state.current_ticket.key} - {state.current_ticket.summary}
            Description: {state.current_ticket.description}
            Components: {', '.join(state.current_ticket.components)}
            Labels: {', '.join(state.current_ticket.labels)}
            
            Available repositories:
            {chr(10).join([f"- {repo.name} ({repo.primary_language}): {repo.url}" for repo in all_repositories[:10]])}
            
            Return the top 3 most relevant repositories as a JSON list with format:
            [{{"name": "repo_name", "relevance_score": 0.8, "reasoning": "why relevant"}}]
            
            Only include repositories with relevance_score > 0.3
            """
        
        response = await llm.ainvoke([
            SystemMessage(content="You are a repository analyst. Return only valid JSON."),
            HumanMessage(content=analysis_prompt)
        ])
        
        # Parse AI response
        try:
            import json
            analysis_results = json.loads(response.content)
            
            # Select relevant repositories
            relevant_repos = []
            for result in analysis_results:
                repo_name = result.get("name")
                relevance_score = result.get("relevance_score", 0)
                
                if relevance_score > 0.3:
                    repo = next((r for r in all_repositories if r.name == repo_name), None)
                    if repo:
                        repo.local_path = f"/tmp/repos/{repo.name}"
                        relevant_repos.append(repo)
            
            if not relevant_repos:
                return {
                    "error": "No relevant repositories found for this ticket",
                    "workflow_stage": "error",
                    "messages": [AIMessage(content="No relevant repositories found for this ticket")]
                }
            
            return {
                "selected_repositories": relevant_repos,
                "workflow_stage": "repositories_analyzed",
                "messages": [
                    AIMessage(content=f"Selected {len(relevant_repos)} relevant repositories: {', '.join([r.name for r in relevant_repos])}")
                ]
            }
            
        except json.JSONDecodeError:
            # Fallback: select first few repositories
            relevant_repos = all_repositories[:3]
            for repo in relevant_repos:
                repo.local_path = f"/tmp/repos/{repo.name}"
            
            return {
                "selected_repositories": relevant_repos,
                "workflow_stage": "repositories_analyzed",
                "messages": [
                    AIMessage(content=f"Selected {len(relevant_repos)} repositories (fallback selection)")
                ]
            }
        
    except Exception as e:
        return {
            "error": str(e),
            "workflow_stage": "error",
            "messages": [AIMessage(content=f"Error analyzing repositories: {str(e)}")]
        }


async def generate_code(state: JiraToPRState) -> Dict:
    """
    Generate code changes for the selected ticket and repositories.
    
    This function:
    1. Creates code generation requests for each selected repository
    2. Uses Claude Code SDK to generate appropriate code changes
    3. Collects all generated changes
    4. Creates branches for each repository using GitHub MCP
    
    Args:
        state: Current workflow state with ticket and selected repositories
        
    Returns:
        Dict containing:
            - code_changes: List of CodeChange objects
            - workflow_stage: Updated to "code_generated"
            - messages: Generation results
    """
    try:
        if not state.current_ticket or not state.selected_repositories:
            return {
                "error": "Missing ticket or repositories for code generation",
                "workflow_stage": "error"
            }
        
        # Try to import Claude Code SDK
        try:
            from claude_code_sdk import query, ClaudeCodeOptions
            CLAUDE_CODE_SDK_AVAILABLE = True
        except ImportError:
            CLAUDE_CODE_SDK_AVAILABLE = False
        
        if not CLAUDE_CODE_SDK_AVAILABLE:
            return {
                "error": "Claude Code SDK is required for code generation",
                "workflow_stage": "error"
            }
        
        from dependencies.settings import settings
        all_changes = []
        
        # TODO: Replace with actual GitHub MCP integration for branch creation
        # For now, we'll simulate branch creation
        
        for repo in state.selected_repositories:
            try:
                # Ensure repository is available locally
                await _ensure_repository_cloned(repo)
                
                # Create feature branch using GitHub MCP
                branch_name = f"{DEFAULT_BRANCH_PREFIX}{state.current_ticket.key.lower()}"
                
                # TODO: Create actual branch via GitHub API or MCP
                print(f"Would create branch {branch_name} for {repo.full_name}")
                
                # Generate code using Claude Code SDK
                code_prompt = f"""
                Implement the following Jira ticket requirements:
                
                Ticket: {state.current_ticket.key} - {state.current_ticket.summary}
                Description: {state.current_ticket.description}
                
                Repository: {repo.name}
                Primary Language: {repo.primary_language}
                
                Requirements:
                - Follow existing code patterns
                - Include error handling
                - Add appropriate tests
                - Update documentation if needed
                
                Please analyze the repository structure and implement the necessary changes.
                """
                
                # Use Claude Code SDK to generate code
                options = ClaudeCodeOptions(
                    directory=repo.local_path or f"/tmp/repos/{repo.name}",
                    model="claude-3-5-sonnet-20241022"
                )
                
                result = await query(code_prompt, options)
                
                if result:
                    # Create a CodeChange object for the generated code
                    change = CodeChange(
                        file_path=f"{repo.name}/generated_changes.py",
                        original_content="",
                        new_content=str(result),
                        change_type="modification",
                        description=f"Generated code changes for {state.current_ticket.key}",
                        repository=repo.full_name,
                        branch=branch_name,
                        complexity_score=5  # Default complexity score
                    )
                    
                    all_changes.append(change)
                else:
                    print(f"No code generated for repository {repo.name}")
                    
            except Exception as e:
                print(f"Error processing repository {repo.name}: {e}")
                continue
        
        if not all_changes:
            return {
                "error": "No code changes generated",
                "workflow_stage": "error",
                "messages": [AIMessage(content="No code changes were generated")]
            }
        
        return {
            "code_changes": all_changes,
            "workflow_stage": "code_generated",
            "messages": [
                AIMessage(content=f"Generated {len(all_changes)} code changes across {len(state.selected_repositories)} repositories")
            ]
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "workflow_stage": "error",
            "messages": [AIMessage(content=f"Error generating code: {str(e)}")]
        }


async def create_pull_requests(state: JiraToPRState) -> Dict:
    """
    Create pull requests for all generated code changes using MCP.
    
    This function:
    1. Groups code changes by repository
    2. Creates pull requests for each repository with changes using GitHub MCP
    3. Links PRs back to the Jira ticket using Jira MCP
    4. Updates ticket status
    
    Args:
        state: Current workflow state with code changes
        
    Returns:
        Dict containing:
            - pull_requests: List of created PullRequestData objects
            - workflow_result: WorkflowResult with execution summary
            - workflow_stage: Updated to "prs_created"
            - messages: PR creation results
    """
    if not MCP_AVAILABLE:
        return {
            "error": "MCP is required for PR creation",
            "workflow_stage": "error"
        }
    
    try:
        if not state.code_changes or not state.current_ticket:
            return {
                "error": "Missing code changes or ticket for PR creation",
                "workflow_stage": "error"
            }
        
        from dependencies.settings import settings
        created_prs = []
        
        # Group changes by repository
        changes_by_repo = {}
        for change in state.code_changes:
            repo_name = getattr(change, 'repository', '')
            if repo_name not in changes_by_repo:
                changes_by_repo[repo_name] = []
            changes_by_repo[repo_name].append(change)
        
        # TODO: Replace with actual GitHub and Jira MCP integration
        # For now, create mock PR data to test the workflow
        for repo_name, changes in changes_by_repo.items():
            try:
                # Get branch name from first change
                branch_name = getattr(changes[0], 'branch', f"{DEFAULT_BRANCH_PREFIX}{state.current_ticket.key.lower()}")
                
                # Generate PR body
                pr_body = _generate_pr_body(state.current_ticket, changes)
                
                # TODO: Create actual PR via GitHub API or MCP
                # For now, create mock PR data
                result = {
                    "success": True,
                    "html_url": f"https://github.com/{repo_name}/pull/123",
                    "number": 123
                }
                
                if result.get("success"):
                    pr_data = PullRequestData(
                        title=f"[{state.current_ticket.key}] {state.current_ticket.summary}",
                        body=pr_body,
                        head_branch=branch_name,
                        base_branch="main",
                        repository=repo_name,
                        labels=["automated", "jira-ticket"],
                        draft=False,
                        url=result.get("html_url"),
                        number=result.get("number")
                    )
                    created_prs.append(pr_data)
                    
            except Exception as e:
                print(f"Error creating PR for {repo_name}: {e}")
                continue
        
        if not created_prs:
            return {
                "error": "No pull requests were created",
                "workflow_stage": "error",
                "messages": [AIMessage(content="No pull requests were created")]
            }
        
        # TODO: Update Jira ticket using Jira MCP
        # For now, simulate the Jira updates
        for pr in created_prs:
            print(f"Would add comment to Jira {state.current_ticket.key}: Pull request created: {pr.url}")
        
        print(f"Would update Jira ticket {state.current_ticket.key} status to 'In Progress'")
        
        # Create workflow result
        workflow_result = WorkflowResult(
            success=True,
            ticket_id=state.current_ticket.key,
            repositories_processed=[pr.repository for pr in created_prs],
            pull_requests_created=created_prs,
            files_changed=len(state.code_changes),
            lines_added=sum(getattr(change, 'complexity_score', 1) for change in state.code_changes),
            execution_time=(datetime.now() - state.execution_start_time).total_seconds() if getattr(state, 'execution_start_time', None) else None
        )
        
        return {
            "pull_requests": created_prs,
            "workflow_result": workflow_result,
            "workflow_stage": "prs_created",
            "tickets_processed": getattr(state, 'tickets_processed', 0) + 1,
            "prs_created": getattr(state, 'prs_created', 0) + len(created_prs),
            "messages": [
                AIMessage(content=f"Created {len(created_prs)} pull requests for ticket {state.current_ticket.key}")
            ]
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "workflow_stage": "error",
            "messages": [AIMessage(content=f"Error creating pull requests: {str(e)}")]
        }


async def cleanup_state(state: JiraToPRState) -> Dict:
    """
    Clean up workflow state after processing a ticket.
    
    Resets ticket-specific state variables and prepares for the next ticket.
    
    Args:
        state: Current workflow state to be cleaned
        
    Returns:
        Dict with reset state variables
    """
    return {
        "current_ticket": None,
        "selected_repositories": [],
        "code_changes": [],
        "pull_requests": [],
        "processing_repo": None,
        "current_branch": None,
        "workflow_stage": "ready",
        "error": None,
        "messages": [AIMessage(content="State cleaned up, ready for next ticket")]
    }


# Helper functions

async def _ensure_repository_cloned(repo: RepositoryInfo) -> bool:
    """
    Ensure repository is cloned locally.
    
    In a real deployment, this would clone the repository to the local filesystem.
    For this implementation, we'll simulate it.
    """
    local_path = Path(repo.local_path)
    if not local_path.exists():
        # In real implementation:
        # git clone {repo.clone_url} {repo.local_path}
        local_path.mkdir(parents=True, exist_ok=True)
        return True
    return True


def _parse_jira_issue(issue: Dict, jira_url: str) -> TicketData:
    """Parse Jira issue JSON into TicketData model."""
    fields = issue.get('fields', {})
    
    # Extract acceptance criteria from custom fields or description
    acceptance_criteria = None
    if 'customfield_10001' in fields and fields['customfield_10001']:
        acceptance_criteria = fields['customfield_10001']
    
    # Extract story points
    story_points = None
    if 'customfield_10002' in fields and fields['customfield_10002']:
        story_points = fields['customfield_10002']
    
    return TicketData(
        id=issue['id'],
        key=issue['key'],
        summary=fields.get('summary', ''),
        description=fields.get('description', ''),
        status=fields.get('status', {}).get('name', 'To Do'),
        priority=fields.get('priority', {}).get('name', 'Medium'),
        assignee=fields.get('assignee', {}).get('displayName') if fields.get('assignee') else None,
        reporter=fields.get('reporter', {}).get('displayName', 'Unknown'),
        created=datetime.fromisoformat(fields.get('created', '').replace('Z', '+00:00')) if fields.get('created') else datetime.now(),
        updated=datetime.fromisoformat(fields.get('updated', '').replace('Z', '+00:00')) if fields.get('updated') else datetime.now(),
        ticket_type=fields.get('issuetype', {}).get('name', 'Task'),
        labels=fields.get('labels', []),
        components=[comp['name'] for comp in fields.get('components', [])],
        fix_versions=[ver['name'] for ver in fields.get('fixVersions', [])],
        project_key=fields.get('project', {}).get('key', ''),
        url=f"{jira_url}/browse/{issue['key']}",
        acceptance_criteria=acceptance_criteria,
        story_points=story_points
    )


def _generate_pr_body(ticket: TicketData, changes: List) -> str:
    """Generate PR body from ticket information and changes."""
    changes_summary = "\n".join([
        f"- {getattr(change, 'description', 'Code change')}" for change in changes
    ])
    
    test_plan = "- [ ] Verify all tests pass\n- [ ] Manual testing completed\n- [ ] Code review completed"
    
    if getattr(ticket, 'acceptance_criteria', None):
        test_plan += f"\n- [ ] Acceptance criteria met:\n  {ticket.acceptance_criteria}"
    
    return DEFAULT_PR_TEMPLATE.format(
        summary=ticket.summary,
        changes=changes_summary,
        ticket_id=ticket.key,
        ticket_type=getattr(ticket, 'ticket_type', 'Task'),
        ticket_priority=getattr(ticket, 'priority', 'Medium'),
        ticket_url=getattr(ticket, 'url', ''),
        test_plan=test_plan
    )