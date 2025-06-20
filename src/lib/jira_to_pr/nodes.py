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
import claude_code_sdk
# Claude SDK with MCP integration
try:
    from claude_code_sdk import query, ClaudeCodeOptions, CLIJSONDecodeError
    from claude_code_sdk.types import McpServerConfig
    CLAUDE_SDK_AVAILABLE = True
except ImportError:
    CLAUDE_SDK_AVAILABLE = False

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
from lib.jira_to_pr.constants import DEFAULT_BRANCH_PREFIX, DEFAULT_PR_TEMPLATE


# Initialize LLM for decision making
llm = ChatOpenAI(model="gpt-4o", temperature=0)


async def fetch_jira_tickets(state: JiraToPRState) -> Dict:
    """
    Fetch unassigned tickets from the active sprint using Claude SDK with MCP.
    """
    # Temporarily return mock data for testing
    from datetime import datetime, timezone, timedelta

    try:
        from dependencies.settings import settings

        if not CLAUDE_SDK_AVAILABLE:
            return {
                "error": "Claude SDK is required for MCP integration",
                "workflow_stage": "error"
            }

        # Configure MCP server for Jira
        jira_server_config = McpServerConfig(
            command="docker",
            args=[
                "run", "-i", "--rm",
                "-e", "JIRA_URL",
                "-e", "JIRA_USERNAME",
                "-e", "JIRA_API_TOKEN",
                "ghcr.io/sooperset/mcp-atlassian:latest"
            ],
            env={
                "JIRA_URL": settings.jira_url,
                "JIRA_USERNAME": settings.jira_email,
                "JIRA_API_TOKEN": settings.jira_api_token
            }
        )

        # Search for tickets
        jql = f'project = {settings.jira_project_key} AND sprint in openSprints() AND assignee is EMPTY AND status = "To Do"'

        prompt = f"""
        Use the Jira MCP server to search for issues with the following JQL:
        {jql}

        Return the issues in JSON format with all relevant fields including:
        - id, key, summary, description
        - status, priority, assignee, reporter
        - created, updated, issuetype
        - labels, components, fixVersions, project
        """

        # Query using Claude SDK with MCP configuration
        result_generator = query(
            prompt=prompt,
            options=ClaudeCodeOptions(
                mcp_servers={"mcp-atlassian": jira_server_config},
                mcp_tools=["mcp__mcp-atlassian__jira_search", "mcp__mcp-atlassian__jira_get_issue"],
                allowed_tools=["mcp__mcp-atlassian__jira_search", "mcp__mcp-atlassian__jira_get_issue"]
            )
        )

        # Process the async generator to get results
        tickets = []
        response_text = ""
        chunk_count = 0

        print("Starting to process Jira MCP response...")

        max_attempts = 3
        for i in range(max_attempts):
            try:
                async for chunk in result_generator:
                    try:
                        chunk_count += 1
                        print(f"\n{'='*80}")
                        print(f"Jira chunk #{chunk_count}: {type(chunk).__name__}")
                        print(f"{'='*80}")

                        # Print full chunk content for debugging
                        print(f"Full chunk content:\n{chunk}")

                        response_text += str(chunk)

                        # Look for JSON data in the response
                        if hasattr(chunk, '__class__') and chunk.__class__.__name__ == 'ResultMessage':
                            if hasattr(chunk, 'result'):
                                result_content = chunk.result

                            # Try to parse JSON from the result
                            import re
                            import json

                            # Look for JSON blocks in code blocks or plain text
                            json_patterns = [
                                r'```json\s*(\{.*?\})\s*```',  # JSON in code blocks
                                r'```\s*(\{.*?\})\s*```',      # JSON in plain code blocks
                                r'(\{.*?"issues".*?\})',       # JSON with issues array
                                r'(\{.*?\})'                   # Any JSON object
                            ]

                            json_matches = []
                            for pattern in json_patterns:
                                matches = re.findall(pattern, result_content, re.DOTALL)
                                json_matches.extend(matches)
                                if matches:
                                    break  # Use first successful pattern

                            for json_match in json_matches:
                                try:
                                    data = json.loads(json_match)

                                    # Handle nested structure with "issues" array
                                    if isinstance(data, dict) and 'issues' in data:
                                        issues = data['issues']
                                    elif isinstance(data, list):
                                        issues = data
                                    else:
                                        issues = [data]

                                    for issue in issues:
                                        if isinstance(issue, dict) and 'key' in issue:
                                            # Create TicketData object with proper validation
                                            # Handle status - ensure it's a valid enum value
                                            raw_status = issue.get('status', {}).get('name', 'To Do') if isinstance(issue.get('status'), dict) else str(issue.get('status', 'To Do'))
                                            if raw_status not in ['To Do', 'In Progress', 'In Review', 'Done']:
                                                raw_status = 'To Do'  # Default to valid status

                                            # Generate URL for the ticket
                                            ticket_key = issue.get('key', '')
                                            ticket_url = f"{settings.jira_url}/browse/{ticket_key}" if ticket_key else ""

                                            ticket = TicketData(
                                                id=str(issue.get('id', '')),
                                                key=ticket_key,
                                                summary=issue.get('summary', ''),
                                                description=issue.get('description', ''),
                                                status=raw_status,
                                                priority=issue.get('priority', {}).get('name', 'Medium') if isinstance(issue.get('priority'), dict) else str(issue.get('priority', 'Medium')),
                                                assignee=issue.get('assignee', {}).get('displayName', None) if isinstance(issue.get('assignee'), dict) else issue.get('assignee'),
                                                reporter=issue.get('reporter', {}).get('displayName', 'Unknown') if isinstance(issue.get('reporter'), dict) else str(issue.get('reporter', 'Unknown')),
                                                created=issue.get('created', datetime.now(timezone.utc).isoformat()),
                                                updated=issue.get('updated', datetime.now(timezone.utc).isoformat()),
                                                ticket_type=issue.get('issuetype', {}).get('name', 'Task') if isinstance(issue.get('issuetype'), dict) else str(issue.get('issuetype', 'Task')),
                                                labels=issue.get('labels', []),
                                                components=[comp.get('name', str(comp)) if isinstance(comp, dict) else str(comp) for comp in issue.get('components', [])],
                                                fix_versions=[ver.get('name', str(ver)) if isinstance(ver, dict) else str(ver) for ver in issue.get('fixVersions', [])],
                                                project_key=issue.get('project', {}).get('key', settings.jira_project_key) if isinstance(issue.get('project'), dict) else str(issue.get('project', settings.jira_project_key)),
                                                url=ticket_url
                                            )
                                            tickets.append(ticket)

                                except json.JSONDecodeError:
                                    continue
                    except CLIJSONDecodeError as e:
                        print(f"  <UNK> Error parsing result summary: {e}")
                        continue
                    except Exception as async_error:
                        print(f"Error processing Jira async generator: {async_error}")
                        import traceback
                        print(traceback.format_exc())
                break
            except ExceptionGroup as eg:
                print(f"Error processing Jira MCP response - ExceptionGroup caught")
                print(f"ExceptionGroup message: {eg}")
                print(f"Number of exceptions in group: {len(eg.exceptions)}")
                for i, exc in enumerate(eg.exceptions):
                    print(f"\nException {i+1}/{len(eg.exceptions)}:")
                    print(f"  Type: {type(exc).__name__}")
                    print(f"  Message: {exc}")
                    import traceback
                    print(f"  Traceback:")
                    print(''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
                continue

        print(f"Finished processing Jira MCP response. Found {len(tickets)} tickets.")
        print(tickets)
        
        return {
            "available_tickets": tickets,
            "workflow_stage": "tickets_fetched",
            "messages": [
                AIMessage(content=f"Fetched {len(tickets)} unassigned tickets from active sprint")
            ]
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
    try:
        if not state.current_ticket:
            return {
                "error": "No ticket selected for repository analysis",
                "workflow_stage": "error"
            }
        
        from dependencies.settings import settings
        
        # Configure GitHub MCP server
        github_server_config = McpServerConfig(
            command="docker",
            args=[
                "run", "-i", "--rm",
                "-e", "GITHUB_PERSONAL_ACCESS_TOKEN",
                "ghcr.io/github/github-mcp-server"
            ],
            env={
                "GITHUB_PERSONAL_ACCESS_TOKEN": settings.github_token
            }
        )
        
        # Step 1: Search all repositories using GitHub MCP
        print("Starting GitHub repository search...")
        
        # Search for user's repositories - minimal to avoid JSON truncation
        github_user = settings.github_user or "davideferri"
        search_repos_prompt = f"""
        You are AI software architect that needs to understand what repositories are relevant to your ticket.
        
        Analyse up to 3 repository of user:{github_user} and understand from its name whether it is relevant or not for your ticket.
        
        For 1 <= i <= 10, do the following:
            Query the search_repositories as follows:
                - query: "user:{github_user}"
                - page: i
                - perPage: 1
                - sort: descending
        
            After getting the results, extract and return ONLY these fields for the repository:
            - name
            - full_name  
            - url
            - default_branch
            - language
        
            Check whether the repository is relevant (assign a 0 to 1 relevance score) for your Jira ticket based on the ticket description and repository name:
            
            Ticket: {state.current_ticket.key} - {state.current_ticket.summary}
            Description: {state.current_ticket.description}
            Components: {', '.join(state.current_ticket.components)}
            Labels: {', '.join(state.current_ticket.labels)}
            
        Return the top 1 most relevant repositories as a JSON list with format:
            [{{
            "name": "repo_name", 
            "full_name": "repo_full_name",
            "url":"repo_url",
            "language":"repo_language",
            "default_branch":"repo_default_branch",
            "relevance_score": "relevance_score between 0 and 1", 
            "reasoning": "why relevant based on ticket description and repo name"}}]
        """
        
        print(f"Creating GitHub MCP query with config: {github_server_config}")

        try:
            github_result_generator = query(
                prompt=search_repos_prompt,
                options=ClaudeCodeOptions(
                    mcp_servers={"github": github_server_config},
                    mcp_tools=["mcp__github__search_repositories", "mcp__github__get_file_contents"],
                    allowed_tools=["mcp__github__search_repositories", "mcp__github__get_file_contents"]
                )
            )
            print("GitHub query created successfully")
        except Exception as e:
            print(f"Error creating GitHub query: {e}")
            raise

        # Collect GitHub response
        github_response_text = ""
        github_tool_result_data = None

        print("Starting to process GitHub async generator...")

        chunk_count = 0
        max_attempts = 3
        for i in range(max_attempts):
            try:
                async for chunk in github_result_generator:
                    try:
                        chunk_count += 1
                        print(f"\nGitHub chunk #{chunk_count}: {type(chunk).__name__}")
                        # Print chunk content for debugging
                        print(f"Chunk content: {chunk}")

                        # Check if this is a UserMessage with tool results
                        if hasattr(chunk, 'content') and isinstance(chunk.content, list):
                            print(f"Chunk has content list with {len(chunk.content)} items")
                            for i, content_item in enumerate(chunk.content):
                                print(f"Content item #{i}: {type(content_item)} - {content_item.get('type') if isinstance(content_item, dict) else 'N/A'}")
                                if isinstance(content_item, dict) and content_item.get('type') == 'tool_result':
                                    # Extract the actual GitHub data from tool result
                                    tool_content = content_item.get('content', [])
                                    if tool_content and isinstance(tool_content, list):
                                        for item in tool_content:
                                            if isinstance(item, dict) and item.get('type') == 'text':
                                                github_tool_result_data = item.get('text', '')
                                                print(f"Found GitHub tool result data!")
                                                break

                        github_response_text += str(chunk)
                        print(f"Successfully processed chunk #{chunk_count}")
                    except CLIJSONDecodeError as e:
                        print(f"  <UNK> Error parsing result summary: {e}")
                        continue
                    except Exception as chunk_error:
                        print(f"Error processing chunk #{chunk_count}: {chunk_error}")
                        continue

                print("Finished processing GitHub async generator")
                break
            except ExceptionGroup as eg:
                print(f"Error processing GitHub async generator - ExceptionGroup caught")
                print(f"ExceptionGroup message: {eg}")
                print(f"Number of exceptions in group: {len(eg.exceptions)}")
                for i, exc in enumerate(eg.exceptions):
                    print(f"\nException {i+1}/{len(eg.exceptions)}:")
                    print(f"  Type: {type(exc).__name__}")
                    print(f"  Message: {exc}")
                    import traceback
                    print(f"  Traceback:")
                    print(''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
                continue
            except Exception as e:
                print(f"Error in GitHub async generator processing: {e}")
                print(f"Error type: {type(e).__name__}")
                print(f"Error args: {e.args}")
                print(f"Processed {chunk_count} chunks before error")

                # Try to get more details about the TaskGroup error
                import traceback
                print("Full traceback:")
                print(traceback.format_exc())

                # Re-raise to stop execution and understand the root cause
                raise

        # Parse the final ResultMessage to get selected repositories
        selected_repos = []

        # Look for ResultMessage in chunks
        print("Looking for repository data in response...")

        # First try to extract from the accumulated response text
        if github_response_text:
            import re
            import json

            # Look for JSON array in the result field
            # First try to find the entire result content
            result_match = re.search(r"result='(.*?)'(?=\))", github_response_text, re.DOTALL)
            if not result_match:
                result_match = re.search(r'result="(.*?)"(?=\))', github_response_text, re.DOTALL)

            if result_match:
                result_content = result_match.group(1)

                # Replace escaped characters
                result_content = result_content.replace("\\'", "'")
                result_content = result_content.replace('\\"', '"')
                result_content = result_content.replace('\\n', '\n')

                # Now look for JSON array within the result content
                # Try different patterns to find the JSON array
                json_array_patterns = [
                    r'```json\s*(\[.*?\])\s*```',  # JSON array in code blocks
                    r'```\s*(\[.*?\])\s*```',      # Array in plain code blocks
                    r'(\[\s*\{.*?\}\s*\])'         # Raw JSON array
                ]
                
                json_data = None
                for pattern in json_array_patterns:
                    array_match = re.search(pattern, result_content, re.DOTALL)
                    if array_match:
                        json_str = array_match.group(1)
                        print(f"Found JSON with pattern: {pattern}")
                        try:
                            json_data = json.loads(json_str)
                            print(f"Successfully parsed JSON array with {len(json_data)} repositories")
                            break
                        except json.JSONDecodeError as e:
                            print(f"Failed to parse with pattern {pattern}: {e}")
                            continue
                
                if json_data:
                    result_data = json_data

                    # Create RepositoryInfo objects
                    for repo_data in result_data:
                        repo_name = repo_data.get("name", "")
                        repo_full_name = repo_data.get("full_name", "")
                        repo_url = repo_data.get("url", "")

                        # Parse relevance score as float
                        relevance_score_str = repo_data.get("relevance_score", "0.0")
                        try:
                            relevance_score = float(relevance_score_str)
                        except ValueError:
                            relevance_score = 0.0

                        repo_info = RepositoryInfo(
                            name=repo_name,
                            full_name=repo_full_name,
                            url=repo_url,
                            clone_url=repo_url + ".git" if repo_url else "",
                            ssh_url=f"git@github.com:{repo_full_name}.git" if repo_full_name else "",
                            default_branch=repo_data.get("default_branch", "main"),
                            path_to_local_repo=repo_data.get("path_to_local_repo", None),
                            primary_language=repo_data.get("language", None),
                            languages={},
                            relevance_score=relevance_score,
                            relevance_reasoning=repo_data.get("reasoning", ""),
                            analysis_notes=repo_data.get("reasoning", "")
                        )
                        selected_repos.append(repo_info)

        print("The selected repositories are:")
        print(selected_repos)
        return {
            "selected_repositories": selected_repos,
            "workflow_stage": "repositories_analyzed",
            "messages": [
                AIMessage(content=f"Selected {len(selected_repos)} repositories for code generation")
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
    1. Creates a new branch for each repository
    2. Uses Claude Code SDK with GitHub MCP to analyze repository structure
    3. Generates and commits code changes directly to the branch
    4. Returns information about branches created and files changed

    Args:
        state: Current workflow state with ticket and selected repositories

    Returns:
        Dict containing:
            - code_changes: List of CodeChange objects with branch info
            - workflow_stage: Updated to "code_generated"
            - messages: Generation results
    """

    async def create_branch(repo, branch_name, github_server_config):
        """Create a new branch in the repository."""
        owner, repo_name = repo.full_name.split('/')

        branch_creation_prompt = f"""
        Create a new branch named "{branch_name}" for repository {repo.full_name}.

        Steps:
        1. Use get_file_contents with owner: {owner}, repo: {repo_name}, path: "" (empty string for root) to get the default branch SHA
        2. Use create_branch with:
           - owner: {owner}
           - repo: {repo_name}
           - branch: {branch_name}
           - sha: (use the SHA from step 1)

        Return only this JSON:
        {{
            "branch_created": true,
            "branch_name": "{branch_name}"
        }}
        """

        print(f"Step 1: Creating branch {branch_name}")

        try:
            result_generator = query(
                prompt=branch_creation_prompt,
                options=ClaudeCodeOptions(
                    mcp_servers={"github": github_server_config},
                    mcp_tools=[
                        "mcp__github__get_file_contents",
                        "mcp__github__create_branch"
                    ],
                    allowed_tools=[
                        "mcp__github__get_file_contents",
                        "mcp__github__create_branch"
                    ]
                )
            )

            async for chunk in result_generator:
                if hasattr(chunk, '__class__') and chunk.__class__.__name__ == 'ResultMessage':
                    if hasattr(chunk, 'result'):
                        import re
                        import json
                        json_match = re.search(r'\{.*?"branch_created".*?\}', chunk.result, re.DOTALL)
                        if json_match:
                            try:
                                result = json.loads(json_match.group(0))
                                if result.get('branch_created'):
                                    print(f"✓ Branch {branch_name} created successfully")
                                    return True
                            except json.JSONDecodeError:
                                pass

        except Exception as e:
            print(f"Error creating branch: {e}")

        return False

    async def analyze_repository(repo, ticket, github_server_config):
        """Analyze repository structure to identify files needing modification."""
        analysis_prompt = f"""
        Analyze the repository structure for {repo.full_name} to identify files that need modification.

        Context:
        - Ticket: {ticket.key} - {ticket.summary}
        - Description: {ticket.description}
        - Primary Language: {repo.primary_language}

        Use get_file_contents to explore the repository structure (directories only, not file contents).
        Focus on finding the most relevant files for the ticket.

        Important: Only identify up to 5 files maximum. Skip large files (>50KB).

        Return only this JSON:
        {{
            "files_to_modify": [
                {{
                    "path": "file/path",
                    "reason": "why this file needs modification"
                }}
            ]
        }}
        """

        print(f"\nStep 2: Analyzing repository structure")

        try:
            result_generator = query(
                prompt=analysis_prompt,
                options=ClaudeCodeOptions(
                    mcp_servers={"github": github_server_config},
                    mcp_tools=["mcp__github__get_file_contents"],
                    allowed_tools=["mcp__github__get_file_contents"]
                )
            )

            async for chunk in result_generator:
                if hasattr(chunk, '__class__') and chunk.__class__.__name__ == 'ResultMessage':
                    if hasattr(chunk, 'result'):
                        import re
                        import json
                        json_match = re.search(r'\{.*?"files_to_modify".*?\}', chunk.result, re.DOTALL)
                        if json_match:
                            try:
                                result = json.loads(json_match.group(0))
                                files_to_modify = result.get('files_to_modify', [])
                                print(f"✓ Identified {len(files_to_modify)} files to modify")
                                return files_to_modify
                            except json.JSONDecodeError:
                                pass

        except Exception as e:
            print(f"Error analyzing repository: {e}")

        return []

    async def modify_file(file_info, repo, branch_name, ticket, github_server_config):
        """Modify a single file in the repository."""
        file_path = file_info.get('path', '')
        reason = file_info.get('reason', '')

        if not file_path:
            return None

        print(f"\nModifying {file_path}")

        file_modification_prompt = f"""
        Modify the file {file_path} in repository {repo.full_name} on branch {branch_name}.

        Context:
        - Ticket: {ticket.key} - {ticket.summary}
        - Reason for modification: {reason}
        - Task: {ticket.description}

        Steps:
        1. Use get_file_contents to read the current file content
        2. Make the necessary changes based on the ticket requirements
        3. Use create_or_update_file to commit the changes with message: "[{ticket.key}] Update {file_path}"

        Important:
        - If the file is larger than 50KB, skip it and return {{"skipped": true, "reason": "file too large"}}
        - Make only the essential changes
        - Preserve existing code style

        Return only this JSON:
        {{
            "file": "{file_path}",
            "modified": true,
            "description": "brief description of changes made"
        }}
        """

        try:
            result_generator = query(
                prompt=file_modification_prompt,
                options=ClaudeCodeOptions(
                    mcp_servers={"github": github_server_config},
                    mcp_tools=[
                        "mcp__github__get_file_contents",
                        "mcp__github__create_or_update_file"
                    ],
                    allowed_tools=[
                        "mcp__github__get_file_contents",
                        "mcp__github__create_or_update_file"
                    ]
                )
            )

            async for chunk in result_generator:
                if hasattr(chunk, '__class__') and chunk.__class__.__name__ == 'ResultMessage':
                    if hasattr(chunk, 'result'):
                        import re
                        import json
                        json_match = re.search(r'\{.*?"modified".*?\}', chunk.result, re.DOTALL)
                        if json_match:
                            try:
                                result = json.loads(json_match.group(0))
                                if result.get('modified'):
                                    modification_description = result.get('description', 'Updated file')
                                    print(f"✓ Modified {file_path}: {modification_description}")
                                    return {
                                        "path": file_path,
                                        "description": modification_description
                                    }
                                elif result.get('skipped'):
                                    print(f"⚠️ Skipped {file_path}: {result.get('reason', 'unknown')}")
                            except json.JSONDecodeError:
                                pass

        except Exception as e:
            print(f"Error modifying {file_path}: {e}")

        return None

    async def process_repository(repo, ticket, github_server_config):
        """Process a single repository: create branch, analyze, and modify files."""
        print(f"\n{'='*60}")
        print(f"Processing repository: {repo.full_name}")
        print(f"{'='*60}")

        # Create feature branch name
        branch_name = f"{DEFAULT_BRANCH_PREFIX}{ticket.key.lower()}"

        # Step 1: Create branch
        branch_created = await create_branch(repo, branch_name, github_server_config)
        if not branch_created:
            print(f"⚠️ Failed to create branch for {repo.full_name}, skipping...")
            return None

        # Step 2: Analyze repository
        files_to_modify = await analyze_repository(repo, ticket, github_server_config)

        # Step 3: Modify files one at a time
        files_modified = []
        for i, file_info in enumerate(files_to_modify[:5]):  # Limit to 5 files max
            print(f"\nStep 3.{i+1}: Processing file {i+1}/{min(len(files_to_modify), 5)}")
            modified_file = await modify_file(file_info, repo, branch_name, ticket, github_server_config)
            if modified_file:
                files_modified.append(modified_file)

        # Return results for this repository
        if branch_created:
            files_description = "\n".join([
                f"- {f['path']}: {f['description']}"
                for f in files_modified
            ])

            print(f"\n✓ Completed {repo.full_name}: {len(files_modified)} files modified on branch {branch_name}")

            return {
                "repository": repo.full_name,
                "branch": branch_name,
                "changes_description": files_description,
                "files_count": len(files_modified),
                "files_modified": files_modified
            }

        return None

    # Main function body
    try:
        if not state.current_ticket or not state.selected_repositories:
            return {
                "error": "Missing ticket or repositories for code generation",
                "workflow_stage": "error"
            }

        from dependencies.settings import settings

        # Configure GitHub MCP server
        github_server_config = McpServerConfig(
            command="docker",
            args=[
                "run", "-i", "--rm",
                "-e", "GITHUB_PERSONAL_ACCESS_TOKEN",
                "ghcr.io/github/github-mcp-server"
            ],
            env={
                "GITHUB_PERSONAL_ACCESS_TOKEN": settings.github_token
            }
        )

        # Process each repository
        branches_created = []
        for repo in state.selected_repositories:
            result = await process_repository(repo, state.current_ticket, github_server_config)
            if result:
                branches_created.append(result)

        if not branches_created:
            return {
                "error": "No branches were created",
                "workflow_stage": "error",
                "messages": [AIMessage(content="Failed to create branches (will retry)")]
            }

        # Create CodeChange objects from the results
        code_changes = []
        total_files_modified = 0

        for branch_info in branches_created:
            for file_info in branch_info.get('files_modified', []):
                code_change = CodeChange(
                    file_path=file_info['path'],
                    operation='modify',
                    description=file_info['description'],
                    complexity_score=1
                )
                code_changes.append(code_change)
                total_files_modified += 1

        # Print summary
        print(f"\n{'='*60}")
        print(f"Summary:")
        print(f"  Branches created: {len(branches_created)}")
        print(f"  Total files modified: {total_files_modified}")
        for branch_info in branches_created:
            print(f"  - {branch_info['repository']}: {branch_info['branch']} ({branch_info.get('files_count', 0)} files)")

        return {
            "code_changes": code_changes,
            "branches_created": branches_created,
            "workflow_stage": "code_generated",
            "messages": [
                AIMessage(content=f"Created {len(branches_created)} branches with {total_files_modified} file changes")
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
    1. Uses branches_created from generate_code to create PRs
    2. Creates pull requests using GitHub MCP create_pull_request
    3. Returns PR information for workflow tracking
    
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
        if not state.branches_created or not state.current_ticket:
            return {
                "error": "Missing branches or ticket for PR creation",
                "workflow_stage": "error"
            }
        
        from dependencies.settings import settings
        
        # Configure GitHub MCP server
        github_server_config = McpServerConfig(
            command="docker",
            args=[
                "run", "-i", "--rm",
                "-e", "GITHUB_PERSONAL_ACCESS_TOKEN",
                "ghcr.io/github/github-mcp-server"
            ],
            env={
                "GITHUB_PERSONAL_ACCESS_TOKEN": settings.github_token
            }
        )
        
        created_prs = []
        
        # Create PRs for each branch that was created
        for branch_info in state.branches_created:
            try:
                repo_full_name = branch_info['repository']
                branch_name = branch_info['branch']
                owner, repo_name = repo_full_name.split('/')
                
                # Generate PR body with changes description from branch info
                changes_description = branch_info.get('changes_description', '')
                pr_body = _generate_pr_body(state.current_ticket, changes_description)
                
                # Create PR using GitHub MCP
                pr_prompt = f"""
                Create a pull request for the changes in branch {branch_name}.
                
                Use the create_pull_request tool with these exact parameters:
                - owner: {owner}
                - repo: {repo_name}
                - title: "[{state.current_ticket.key}] {state.current_ticket.summary}"
                - body: {pr_body}
                - head: {branch_name}
                - base: main
                - draft: false
                - maintainer_can_modify: true
                
                After creating the pull request, return a JSON summary with the PR details:
                {{
                    "success": true,
                    "html_url": "the PR URL from the response",
                    "number": "the PR number from the response",
                    "title": "the PR title"
                }}
                """
                
                print(f"Creating PR for {repo_full_name} from branch {branch_name}")
                
                # Query using Claude SDK with GitHub MCP
                result_generator = query(
                    prompt=pr_prompt,
                    options=ClaudeCodeOptions(
                        mcp_servers={"github": github_server_config},
                        mcp_tools=["mcp__github__create_pull_request"],
                        allowed_tools=["mcp__github__create_pull_request"]
                    )
                )
                
                # Process the async generator
                response_text = ""
                pr_url = None
                pr_number = None
                chunk_count = 0
                
                print(f"Processing PR creation for {repo_full_name}...")
                max_attempts = 3
                for i in range(max_attempts):
                    try:
                        async for chunk in result_generator:
                            try:
                                chunk_count += 1
                                print(f"\n{'='*80}")
                                print(f"PR chunk #{chunk_count}: {type(chunk).__name__}")
                                print(f"{'='*80}")

                                # Print full chunk content for debugging
                                print(f"Full chunk content:\n{chunk}")
                                # Check for tool usage
                                if hasattr(chunk, 'content') and isinstance(chunk.content, list):
                                    for content_item in chunk.content:
                                        if isinstance(content_item, dict):
                                            if content_item.get('type') == 'tool_use' and 'create_pull_request' in content_item.get('name', ''):
                                                print(f"  ✓ Creating pull request")
                                                print(f"    Tool input: {content_item.get('input', {})}")
                                            elif content_item.get('type') == 'tool_result':
                                                print(f"  Tool result received")
                                                # Extract PR info from tool result
                                                tool_content = content_item.get('content', [])
                                                if tool_content and isinstance(tool_content, list):
                                                    for item in tool_content:
                                                        if isinstance(item, dict) and item.get('type') == 'text':
                                                            result_text = item.get('text', '')
                                                            # Try to extract PR URL and number
                                                            import re
                                                            url_match = re.search(r'https://github\.com/[^/]+/[^/]+/pull/(\d+)', result_text)
                                                            if url_match:
                                                                pr_url = url_match.group(0)
                                                                pr_number = int(url_match.group(1))
                                                                print(f"  Found PR: {pr_url}")

                                response_text += str(chunk)

                                # Look for ResultMessage with PR info
                                if hasattr(chunk, '__class__') and chunk.__class__.__name__ == 'ResultMessage':
                                    if hasattr(chunk, 'result'):
                                        result_content = chunk.result

                                        # Try to extract JSON result
                                        import re
                                        import json

                                        json_match = re.search(r'\{[^{}]*"success"[^{}]*\}', result_content, re.DOTALL)
                                        if json_match:
                                            try:
                                                json_str = json_match.group(0)
                                                result_data = json.loads(json_str)
                                                if result_data.get('success'):
                                                    pr_url = result_data.get('html_url', pr_url)
                                                    pr_number = result_data.get('number', pr_number)
                                                    print(f"Successfully parsed PR result")
                                            except json.JSONDecodeError as e:
                                                print(f"Error parsing PR result: {e}")

                                print(f"Successfully processed chunk #{chunk_count}")
                            except CLIJSONDecodeError as e:
                                print(f"  <UNK> Error parsing result summary: {e}")
                                continue
                            except Exception as chunk_error:
                                print(f"Error processing chunk #{chunk_count}: {chunk_error}")
                                continue
                        break
                    except ExceptionGroup as eg:
                        print(f"Error in PR creation - ExceptionGroup caught")
                        print(f"ExceptionGroup message: {eg}")
                        print(f"Number of exceptions in group: {len(eg.exceptions)}")
                        for k, exc in enumerate(eg.exceptions):
                            print(f"\nException {k+1}/{len(eg.exceptions)}:")
                            print(f"  Type: {type(exc).__name__}")
                            print(f"  Message: {exc}")
                            import traceback
                            print(f"  Traceback:")
                            print(''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
                        continue
                print(f"\nFinished PR creation. Total chunks: {chunk_count}")
                
                if pr_url and pr_number:
                    pr_data = PullRequestData(
                        title=f"[{state.current_ticket.key}] {state.current_ticket.summary}",
                        body=pr_body,
                        head_branch=branch_name,
                        base_branch="main",
                        repository=repo_full_name,
                        labels=["automated", "jira-ticket"],
                        draft=False,
                        url=pr_url,
                        number=pr_number
                    )
                    created_prs.append(pr_data)
                    print(f"✓ Created PR #{pr_number} for {repo_full_name}")
                else:
                    print(f"Warning: Could not extract PR URL/number for {repo_full_name}")
            except Exception as e:
                print(f"Error creating PR for {repo_full_name}: {e}")
                import traceback
                print(traceback.format_exc())
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
            "workflow_stage": "retry_create_pull_requests",
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
        "branches_created": [],
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
    """Parse Jira issue JSON into TicketData model - handles both API and MCP formats."""
    
    # Check if this is the standard Jira API format (with fields) or MCP format (flattened)
    if 'fields' in issue:
        # Standard Jira API format
        fields = issue.get('fields', {})
        summary = fields.get('summary', '')
        description = fields.get('description', '')
        status_name = fields.get('status', {}).get('name', 'To Do')
        priority_name = fields.get('priority', {}).get('name', 'Medium')
        assignee_name = fields.get('assignee', {}).get('displayName') if fields.get('assignee') else None
        reporter_name = fields.get('reporter', {}).get('displayName', 'Unknown')
        created_str = fields.get('created', '')
        updated_str = fields.get('updated', '')
        ticket_type = fields.get('issuetype', {}).get('name', 'Task')
        labels = fields.get('labels', [])
        components = [comp['name'] for comp in fields.get('components', [])]
        fix_versions = [ver['name'] for ver in fields.get('fixVersions', [])]
        project_key = fields.get('project', {}).get('key', '')
        
        # Extract acceptance criteria from custom fields
        acceptance_criteria = None
        if 'customfield_10001' in fields and fields['customfield_10001']:
            acceptance_criteria = fields['customfield_10001']
        
        # Extract story points
        story_points = None
        if 'customfield_10002' in fields and fields['customfield_10002']:
            story_points = fields['customfield_10002']
    else:
        # MCP format (flattened structure)
        summary = issue.get('summary', '')
        description = issue.get('description', '')
        status_name = issue.get('status', {}).get('name', 'To Do')
        priority_name = issue.get('priority', {}).get('name', 'Medium')
        assignee_name = issue.get('assignee', {}).get('display_name') if issue.get('assignee') else None
        reporter_name = issue.get('reporter', {}).get('display_name', 'Unknown')
        created_str = issue.get('created', '')
        updated_str = issue.get('updated', '')
        ticket_type = issue.get('issue_type', {}).get('name', 'Task')
        labels = issue.get('labels', [])
        components = [comp['name'] for comp in issue.get('components', [])] if issue.get('components') else []
        fix_versions = [ver['name'] for ver in issue.get('fix_versions', [])] if issue.get('fix_versions') else []
        project_key = issue.get('project', {}).get('key', '')
        
        # Extract acceptance criteria and story points from custom_fields
        # In MCP format, custom_fields is a top-level object in the issue
        custom_fields = issue.get('custom_fields', {})
        acceptance_criteria = None
        story_points = None
        
        # Check if custom_fields exists at top level
        if custom_fields:
            if custom_fields.get('customfield_10001', {}).get('value'):
                acceptance_criteria = custom_fields['customfield_10001']['value']
            
            # Check for story points in customfield_10016
            if custom_fields.get('customfield_10016', {}).get('value') is not None:
                story_points = custom_fields['customfield_10016']['value']
        else:
            if issue.get('customfield_10001'):
                acceptance_criteria = issue['customfield_10001']
            
            if issue.get('customfield_10016') is not None:
                story_points = issue['customfield_10016']
    
    # Parse datetime strings
    try:
        created_dt = datetime.fromisoformat(created_str.replace('Z', '+00:00')) if created_str else datetime.now()
    except:
        created_dt = datetime.now()
    
    try:
        updated_dt = datetime.fromisoformat(updated_str.replace('Z', '+00:00')) if updated_str else datetime.now()
    except:
        updated_dt = datetime.now()
    
    return TicketData(
        id=issue['id'],
        key=issue['key'],
        summary=summary,
        description=description,
        status=status_name,
        priority=priority_name,
        assignee=assignee_name,
        reporter=reporter_name,
        created=created_dt,
        updated=updated_dt,
        ticket_type=ticket_type,
        labels=labels,
        components=components,
        fix_versions=fix_versions,
        project_key=project_key,
        url=f"{jira_url}/browse/{issue['key']}",
        acceptance_criteria=acceptance_criteria,
        story_points=story_points
    )


def _generate_pr_body(ticket: TicketData, changes_description: str) -> str:
    """Generate PR body from ticket information and changes description."""
    # If changes_description is provided, use it; otherwise use ticket description
    if changes_description:
        changes_summary = f"## Changes Made\n{changes_description}"
    else:
        changes_summary = f"Implemented changes for ticket {ticket.key}: {ticket.description}"
    
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