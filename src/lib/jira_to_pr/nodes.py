"""Workflow node functions for the Jira to PR automation graph."""

import os
import random
import asyncio
from typing import Dict, Optional, List
from datetime import datetime
from pathlib import Path

from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

from .models import (
    JiraToPRState, TicketData, RepositoryInfo, CodeGenerationRequest,
    CodeGenerationResult, PullRequestData, WorkflowResult
)
from .integrations import (
    create_jira_client, create_github_client, create_claude_code_client,
    RepositoryAnalyzer
)
from .constants import DEFAULT_BRANCH_PREFIX, DEFAULT_PR_TEMPLATE


# Initialize LLM for decision making
llm = ChatOpenAI(model="gpt-4o", temperature=0)


async def fetch_jira_tickets(state: JiraToPRState) -> Dict:
    """
    Fetch unassigned tickets from the active sprint.
    
    This function connects to Jira and retrieves all tickets that are:
    - In the active sprint
    - Unassigned (assignee is empty)
    - In "To Do" status
    
    Args:
        state: Current workflow state
        
    Returns:
        Dict containing:
            - available_tickets: List of TicketData objects
            - workflow_stage: Updated to "tickets_fetched"
            - messages: Status information
    """
    try:
        from dependencies.settings import settings
        
        jira_client = create_jira_client()
        project_key = settings.jira_project_key
        
        tickets = await jira_client.get_active_sprint_tickets(project_key)
        
        if not tickets:
            return {
                "available_tickets": [],
                "workflow_stage": "no_tickets",
                "messages": [AIMessage(content="No unassigned tickets found in active sprint")]
            }
        
        return {
            "available_tickets": tickets,
            "workflow_stage": "tickets_fetched",
            "messages": [AIMessage(content=f"Found {len(tickets)} unassigned tickets in active sprint")]
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
    1. Fetches all accessible GitHub repositories
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
    try:
        if not state.current_ticket:
            return {
                "error": "No ticket selected for repository analysis",
                "workflow_stage": "error"
            }
        
        # Get all accessible repositories
        github_client = create_github_client()
        all_repositories = await github_client.get_accessible_repositories()
        
        if not all_repositories:
            return {
                "error": "No accessible repositories found",
                "workflow_stage": "error",
                "messages": [AIMessage(content="No accessible repositories found")]
            }
        
        # Analyze repository relevance
        analyzer = RepositoryAnalyzer(llm)
        analysis_results = await analyzer.analyze_ticket_repository_relevance(
            state.current_ticket, all_repositories
        )
        
        # Select top repositories (limit to max_repositories_per_ticket)
        max_repos = getattr(state, 'max_repositories_per_ticket', 3)
        relevant_repos = [
            result.repository for result in analysis_results[:max_repos]
            if result.relevance_score > 0.3  # Only include repositories with decent relevance
        ]
        
        if not relevant_repos:
            return {
                "error": "No relevant repositories found for this ticket",
                "workflow_stage": "error",
                "messages": [AIMessage(content="No relevant repositories found for this ticket")]
            }
        
        # Set local paths for repositories (would be configured in real deployment)
        for repo in relevant_repos:
            repo.local_path = f"/tmp/repos/{repo.name}"
        
        return {
            "selected_repositories": relevant_repos,
            "workflow_stage": "repositories_analyzed",
            "messages": [
                AIMessage(content=f"Selected {len(relevant_repos)} relevant repositories: {', '.join([r.name for r in relevant_repos])}")
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
    4. Creates branches for each repository
    
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
        
        claude_client = create_claude_code_client()
        github_client = create_github_client()
        all_changes = []
        
        for repo in state.selected_repositories:
            try:
                # Clone repository locally (in real deployment)
                # For now, we'll simulate this
                await _ensure_repository_cloned(repo)
                
                # Create feature branch
                branch_name = f"{DEFAULT_BRANCH_PREFIX}{state.current_ticket.key.lower()}"
                await github_client.create_branch(repo.full_name, branch_name)
                
                # Generate code for this repository
                request = CodeGenerationRequest(
                    ticket=state.current_ticket,
                    repository=repo,
                    test_requirements=True,
                    constraints=[
                        "Follow existing code patterns",
                        "Include error handling",
                        "Add appropriate tests",
                        "Update documentation if needed"
                    ]
                )
                
                result = await claude_client.generate_code(request)
                
                if result.success:
                    all_changes.extend(result.changes)
                    
                    # Update each change with repository info
                    for change in result.changes:
                        change.repository = repo.full_name
                        change.branch = branch_name
                else:
                    return {
                        "error": f"Code generation failed for {repo.name}: {result.error_message}",
                        "workflow_stage": "error"
                    }
                    
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
    Create pull requests for all generated code changes.
    
    This function:
    1. Groups code changes by repository
    2. Creates pull requests for each repository with changes
    3. Links PRs back to the Jira ticket
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
    try:
        if not state.code_changes or not state.current_ticket:
            return {
                "error": "Missing code changes or ticket for PR creation",
                "workflow_stage": "error"
            }
        
        github_client = create_github_client()
        jira_client = create_jira_client()
        created_prs = []
        
        # Group changes by repository
        changes_by_repo = {}
        for change in state.code_changes:
            repo_name = getattr(change, 'repository', '')
            if repo_name not in changes_by_repo:
                changes_by_repo[repo_name] = []
            changes_by_repo[repo_name].append(change)
        
        # Create PR for each repository
        for repo_name, changes in changes_by_repo.items():
            try:
                # Get branch name from first change
                branch_name = getattr(changes[0], 'branch', f"{DEFAULT_BRANCH_PREFIX}{state.current_ticket.key.lower()}")
                
                # Create PR data
                pr_data = PullRequestData(
                    title=f"[{state.current_ticket.key}] {state.current_ticket.summary}",
                    body=_generate_pr_body(state.current_ticket, changes),
                    head_branch=branch_name,
                    base_branch="main",
                    repository=repo_name,
                    labels=["automated", "jira-ticket"],
                    draft=False  # Set to True if you want draft PRs initially
                )
                
                # Create the PR
                created_pr = await github_client.create_pull_request(repo_name, pr_data)
                
                if created_pr:
                    created_prs.append(created_pr)
                    
                    # Add comment to Jira ticket
                    comment = f"Pull request created: {created_pr.url}"
                    await jira_client.add_comment(state.current_ticket.id, comment)
                
            except Exception as e:
                print(f"Error creating PR for {repo_name}: {e}")
                continue
        
        if not created_prs:
            return {
                "error": "No pull requests were created",
                "workflow_stage": "error",
                "messages": [AIMessage(content="No pull requests were created")]
            }
        
        # Update Jira ticket status
        await jira_client.update_ticket_status(state.current_ticket.id, "In Progress")
        
        # Create workflow result
        workflow_result = WorkflowResult(
            success=True,
            ticket_id=state.current_ticket.key,
            repositories_processed=[pr.repository for pr in created_prs],
            pull_requests_created=created_prs,
            files_changed=len(state.code_changes),
            lines_added=sum(change.complexity_score for change in state.code_changes),
            execution_time=(datetime.now() - state.execution_start_time).total_seconds() if state.execution_start_time else None
        )
        
        return {
            "pull_requests": created_prs,
            "workflow_result": workflow_result,
            "workflow_stage": "prs_created",
            "tickets_processed": state.tickets_processed + 1,
            "prs_created": state.prs_created + len(created_prs),
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


def _generate_pr_body(ticket: TicketData, changes: List) -> str:
    """Generate PR body from ticket information and changes."""
    changes_summary = "\n".join([
        f"- {change.description}" for change in changes if change.description
    ])
    
    test_plan = "- [ ] Verify all tests pass\n- [ ] Manual testing completed\n- [ ] Code review completed"
    
    if ticket.acceptance_criteria:
        test_plan += f"\n- [ ] Acceptance criteria met:\n  {ticket.acceptance_criteria}"
    
    return DEFAULT_PR_TEMPLATE.format(
        summary=ticket.summary,
        changes=changes_summary,
        ticket_id=ticket.key,
        ticket_type=ticket.ticket_type,
        ticket_priority=ticket.priority.value,
        ticket_url=ticket.url,
        test_plan=test_plan
    )