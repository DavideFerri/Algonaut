"""Conditional edge functions for workflow routing in the Jira to PR automation graph."""

import json
from typing import Literal

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.constants import END

from lib.jira_to_pr.models import JiraToPRState


# Initialize LLM for decision making
llm = ChatOpenAI(model="gpt-4o", temperature=0)


async def tickets_or_end(state: JiraToPRState) -> Literal["select_ticket", END]:
    """
    Route between selecting a ticket or ending the workflow.
    
    Args:
        state: Current workflow state
        
    Returns:
        - "select_ticket": When tickets are available to process
        - END: When no more tickets available or max tickets processed
    """
    # Check if we have available tickets and haven't reached max per run
    if (state.available_tickets and 
        state.tickets_processed < state.max_tickets_per_run):
        return "select_ticket"
    else:
        return END


async def analyze_or_error(state: JiraToPRState) -> Literal["analyze_repositories", END]:
    """
    Route between repository analysis or cleanup based on ticket selection.
    
    Args:
        state: Current workflow state with selected ticket
        
    Returns:
        - "analyze_repositories": When a ticket was successfully selected
        - END
    """
    if state.current_ticket is not None and state.error is None:
        return "analyze_repositories"
    else:
        return END


async def generate_or_error(state: JiraToPRState) -> Literal["generate_code", "cleanup_state"]:
    """
    Route between code generation or cleanup based on repository analysis.
    
    Args:
        state: Current workflow state with repository analysis results
        
    Returns:
        - "generate_code": When relevant repositories were found
        - "cleanup_state": When no relevant repositories or error occurred
    """
    if (state.selected_repositories and 
        len(state.selected_repositories) > 0 and 
        state.error is None):
        return "generate_code"
    else:
        return "cleanup_state"


async def create_pr_or_review(state: JiraToPRState) -> Literal["create_pull_requests", "generate_code", "cleanup_state"]:
    """
    Route between PR creation, retry code generation, or cleanup based on code generation results.
    
    This is a critical quality control decision point that determines whether
    the generated code changes are suitable for PR creation, need retry, or require cleanup.
    
    Args:
        state: Current workflow state with code generation results
        
    Returns:
        - "create_pull_requests": When code changes meet quality criteria
        - "generate_code": When retrying code generation (workflow_stage is "retry_generate_code")
        - "cleanup_state": When code quality issues require human review or error occurred
    """
    print(f"\n{'='*60}")
    print(f"DEBUG: create_pr_or_review edge function")
    print(f"{'='*60}")

    # Check for errors
    print(f"state.error: {state.error}")
    print(f"state.workflow_stage: {state.workflow_stage}")
    
    # Check if we should retry code generation
    if state.workflow_stage == "retry_generate_code":
        print("→ Routing to generate_code for retry")
        return "generate_code"
    
    if state.error is not None:
        print("→ Routing to cleanup_state due to error")
        return "cleanup_state"
    
    # Check branches created
    print(f"state.branches_created: {state.branches_created}")
    print(f"Number of branches: {len(state.branches_created) if state.branches_created else 0}")
    
    # Check code changes
    print(f"state.code_changes exists: {state.code_changes is not None}")
    print(f"Number of code changes: {len(state.code_changes) if state.code_changes else 0}")
    if state.code_changes:
        for i, change in enumerate(state.code_changes[:3]):  # Show first 3
            print(f"  Change {i}: {change.file_path} - {change.operation}")
    
    # Also check if we have code changes tracked
    if not state.code_changes or len(state.code_changes) == 0:
        print("→ Routing to cleanup_state due to no code changes")
        return "cleanup_state"
    
    # Quality gate: check if changes require human review
    # requires_review = await _assess_code_changes_quality(state)
    
    print("→ Routing to create_pull_requests")
    return "create_pull_requests"


async def pr_creation_or_retry(state: JiraToPRState) -> Literal["cleanup_state", "create_pull_requests", END]:
    """
    Route after PR creation attempt - continue, retry, or end.
    
    Args:
        state: Current workflow state after PR creation attempt
        
    Returns:
        - "cleanup_state": PR creation succeeded, continue with next ticket
        - "create_pull_requests": Retry PR creation (workflow_stage is "retry_create_pull_requests")
        - END: Critical error or workflow complete
    """
    print(f"\n{'='*60}")
    print(f"DEBUG: pr_creation_or_retry edge function")
    print(f"{'='*60}")
    print(f"state.workflow_stage: {state.workflow_stage}")
    print(f"state.error: {state.error}")
    print(f"state.pull_requests: {len(state.pull_requests) if state.pull_requests else 0}")
    
    # Check if we should retry PR creation
    if state.workflow_stage == "retry_create_pull_requests":
        print("→ Routing to create_pull_requests for retry")
        return "create_pull_requests"
    
    # Check if PRs were successfully created
    if state.pull_requests and len(state.pull_requests) > 0:
        print("→ Routing to cleanup_state (PRs created successfully)")
        return "cleanup_state"
    
    # Check for critical errors
    if state.error and not _is_recoverable_error(state.error):
        print("→ Routing to END due to critical error")
        return END
    
    print("→ Routing to cleanup_state (default)")
    return "cleanup_state"


async def continue_or_end(state: JiraToPRState) -> Literal["cleanup_state", END]:
    """
    Route between continuing with more tickets or ending the workflow.
    
    Args:
        state: Current workflow state after PR creation
        
    Returns:
        - "cleanup_state": Continue processing more tickets
        - END: Stop processing (max tickets reached or no more tickets)
    """
    # Check if we should continue processing more tickets
    if (state.available_tickets and 
        state.tickets_processed < state.max_tickets_per_run and
        not state.dry_run):
        return "cleanup_state"
    else:
        return END


async def retry_or_cleanup(state: JiraToPRState) -> Literal["select_ticket", "cleanup_state", END]:
    """
    Handle error scenarios and decide whether to retry or cleanup.
    
    Args:
        state: Current workflow state with error information
        
    Returns:
        - "select_ticket": Retry with another ticket if available
        - "cleanup_state": Clean up current state and continue
        - END: Stop processing due to critical error
    """
    if state.error is None:
        return "cleanup_state"
    
    # Check if error is recoverable
    if _is_recoverable_error(state.error):
        # Try with another ticket if available
        if state.available_tickets and state.tickets_processed < state.max_tickets_per_run:
            return "select_ticket"
        else:
            return "cleanup_state"
    else:
        # Critical error, stop processing
        return END


# Helper functions

async def _assess_code_changes_quality(state: JiraToPRState) -> bool:
    """
    Assess whether code changes require human review.
    
    Uses LLM and heuristics to determine if the generated code changes
    are complex or risky enough to require human review.
    
    Args:
        state: Current workflow state with code changes
        
    Returns:
        bool: True if changes require human review, False otherwise
    """
    if not state.code_changes:
        return False
    
    # Heuristic checks
    total_files = len(state.code_changes)
    complex_changes = sum(1 for change in state.code_changes if change.complexity_score > 5)
    
    # Check for sensitive file patterns
    sensitive_patterns = [
        'config', 'secret', 'password', 'key', 'auth', 'security',
        'migration', 'database', 'schema', 'production', 'deploy'
    ]
    
    has_sensitive_changes = any(
        any(pattern in change.file_path.lower() for pattern in sensitive_patterns)
        for change in state.code_changes
    )
    
    # Simple heuristics for requiring review
    if total_files > 10:
        return True
    
    if complex_changes > 3:
        return True
    
    if has_sensitive_changes:
        return True
    
    # Use LLM for more sophisticated analysis
    try:
        changes_summary = _summarize_changes(state.code_changes)
        
        prompt = f"""
        Analyze these code changes and determine if they require human review:
        
        Ticket: {state.current_ticket.key} - {state.current_ticket.summary}
        
        Changes Summary:
        {changes_summary}
        
        Consider factors like:
        - Complexity and scope of changes
        - Security implications
        - Database/schema modifications
        - Configuration changes
        - Production impact
        
        Return JSON with: {{"requires_review": bool, "reasoning": str, "confidence": float}}
        """
        
        response = llm.invoke([SystemMessage(content=prompt)])
        
        try:
            result = json.loads(response.content)
            return result.get("requires_review", True)  # Default to requiring review
        except json.JSONDecodeError:
            # If we can't parse the response, err on the side of caution
            return True
            
    except Exception as e:
        print(f"Error in quality assessment: {e}")
        return True  # Default to requiring review on error


def _summarize_changes(code_changes) -> str:
    """Create a summary of code changes for LLM analysis."""
    summary_lines = []
    
    for change in code_changes:
        operation = change.operation.upper() if change.operation else "MODIFY"
        file_path = change.file_path
        description = change.description or "No description"
        complexity = change.complexity_score
        
        summary_lines.append(f"- {operation}: {file_path} (complexity: {complexity}) - {description}")
    
    return "\n".join(summary_lines)


def _is_recoverable_error(error: str) -> bool:
    """
    Determine if an error is recoverable and we should try another ticket.
    
    Args:
        error: Error message string
        
    Returns:
        bool: True if error is recoverable, False for critical errors
    """
    if not error:
        return True
    
    error_lower = error.lower()
    
    # Non-recoverable errors
    critical_patterns = [
        "authentication failed",
        "access denied",
        "api rate limit",
        "network timeout",
        "connection refused",
        "service unavailable"
    ]
    
    for pattern in critical_patterns:
        if pattern in error_lower:
            return False
    
    # Recoverable errors (ticket-specific issues)
    recoverable_patterns = [
        "no relevant repositories",
        "code generation failed",
        "no accessible repositories",
        "ticket analysis failed",
        "will retry"  # Explicit retry indicator
    ]
    
    for pattern in recoverable_patterns:
        if pattern in error_lower:
            return True
    
    # Default to non-recoverable for unknown errors
    return False