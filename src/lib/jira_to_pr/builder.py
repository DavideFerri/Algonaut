"""Builder for the Jira to PR automation workflow graph."""

from datetime import datetime
from langgraph.constants import START
from langgraph.graph import StateGraph

from lib.jira_to_pr.models import JiraToPRState
from lib.jira_to_pr.nodes import (
    fetch_jira_tickets,
    select_ticket,
    analyze_repositories,
    generate_code,
    create_pull_requests,
    cleanup_state,
)
from lib.jira_to_pr.edges import (
    tickets_or_end,
    analyze_or_error,
    generate_or_error,
    create_pr_or_review,
    pr_creation_or_retry,
    continue_or_end,
    retry_or_cleanup,
)


def build_jira_to_pr_graph():
    """
    Build and compile the Jira to PR automation workflow graph.
    
    This function creates a comprehensive workflow that:
    1. Fetches unassigned tickets from active Jira sprint
    2. Randomly selects a ticket to work on
    3. Analyzes available GitHub repositories for relevance
    4. Generates appropriate code changes using Claude Code SDK
    5. Creates pull requests with proper linking
    6. Continues processing until max tickets reached or no more tickets
    
    The workflow includes retry logic for recoverable failures in:
    - Code generation (retries on branch/file creation failures)
    - PR creation (retries on API failures)
    
    Returns:
        Compiled LangGraph instance ready for execution
    """
    # Create the graph builder with state schema
    builder = StateGraph(state_schema=JiraToPRState)

    # Add all workflow nodes
    builder.add_node("fetch_jira_tickets", fetch_jira_tickets)
    builder.add_node("select_ticket", select_ticket)
    builder.add_node("analyze_repositories", analyze_repositories)
    builder.add_node("generate_code", generate_code)
    builder.add_node("create_pull_requests", create_pull_requests)
    builder.add_node("cleanup_state", cleanup_state)

    # Define the workflow flow
    # Start by fetching tickets from Jira
    builder.add_edge(START, "fetch_jira_tickets")
    
    # After fetching tickets, decide whether to select one or end
    builder.add_conditional_edges("fetch_jira_tickets", tickets_or_end)
    
    # After selecting a ticket, analyze repositories or handle errors
    builder.add_conditional_edges("select_ticket", analyze_or_error)
    
    # After repository analysis, generate code or handle errors
    builder.add_conditional_edges("analyze_repositories", generate_or_error)
    
    # After code generation, decide whether to create PRs, retry, or require review
    builder.add_conditional_edges("generate_code", create_pr_or_review)
    
    # After PR creation attempt, decide whether to continue, retry, or end
    builder.add_conditional_edges("create_pull_requests", pr_creation_or_retry)
    
    # After cleanup, go back to selecting tickets if more are available
    builder.add_conditional_edges("cleanup_state", tickets_or_end)

    # Compile the graph
    return builder.compile()


def create_initial_state(
    max_tickets_per_run: int = 5,
    max_repositories_per_ticket: int = 3,
    require_human_review: bool = True,
    dry_run: bool = False
) -> JiraToPRState:
    """
    Create an initial state for the workflow.
    
    Args:
        max_tickets_per_run: Maximum number of tickets to process in one run
        max_repositories_per_ticket: Maximum repositories to analyze per ticket
        require_human_review: Whether to require human review for complex changes
        dry_run: Whether to run in dry-run mode (no actual changes made)
        
    Returns:
        JiraToPRState: Initial state configuration
    """
    return JiraToPRState(
        workflow_stage="initialize",
        max_tickets_per_run=max_tickets_per_run,
        max_repositories_per_ticket=max_repositories_per_ticket,
        require_human_review=require_human_review,
        dry_run=dry_run,
        execution_start_time=datetime.now(),
        tickets_processed=0,
        prs_created=0
    )