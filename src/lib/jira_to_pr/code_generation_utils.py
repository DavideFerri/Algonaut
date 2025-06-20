import os
import random
import asyncio
from typing import Dict, Optional, List
from datetime import datetime
from pathlib import Path

from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
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

from lib.jira_to_pr.models import (
    JiraToPRState, TicketData, RepositoryInfo, CodeGenerationRequest,
    CodeGenerationResult, PullRequestData, WorkflowResult, CodeChange
)


async def create_branch(repo, branch_name, github_server_config):
    """Create a new branch in the repository."""
    owner, repo_name = repo.full_name.split('/')

    # Use from_branch parameter instead of getting SHA manually
    branch_creation_prompt = f"""
    Create a new branch named "{branch_name}" for repository {repo.full_name}.

    Use create_branch with:
       - owner: {owner}
       - repo: {repo_name}
       - branch: {branch_name}
       - from_branch: {repo.default_branch or 'main'}

    Return only this JSON:
    {{
        "branch_created": true,
        "branch_name": "{branch_name}"
    }}
    """

    print(f"Step 1: Creating branch {branch_name}")

    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            result_generator = query(
                prompt=branch_creation_prompt,
                options=ClaudeCodeOptions(
                    mcp_servers={"github": github_server_config},
                    mcp_tools=[
                        "mcp__github__create_branch"
                    ],
                    allowed_tools=[
                        "mcp__github__create_branch"
                    ]
                )
            )

            chunk_count = 0
            try:
                async for chunk in result_generator:
                    try:
                        chunk_count += 1
                        print(f"\n--- Branch Creation Chunk #{chunk_count} ---")
                        print(f"Chunk type: {type(chunk).__name__}")

                        # Print full chunk content for debugging
                        print(f"Full chunk content:\n{chunk}")

                        # Log chunk content based on type
                        if hasattr(chunk, 'content') and isinstance(chunk.content, list):
                            print(f"Content items: {len(chunk.content)}")
                            for i, item in enumerate(chunk.content):
                                if isinstance(item, dict):
                                    print(f"  Item {i}: type={item.get('type')}")
                                    if item.get('type') == 'tool_use':
                                        print(f"    Tool: {item.get('name')}")
                                        print(f"    Input: {item.get('input')}")
                                    elif item.get('type') == 'tool_result':
                                        print(f"    Tool result: {item.get('content')}")
                                        print(f"    Is error: {item.get('is_error', False)}")
                                        
                                        # Check for branch already exists error
                                        if item.get('is_error'):
                                            error_content = str(item.get('content', ''))
                                            if 'already exists' in error_content.lower():
                                                print(f"⚠️ Branch {branch_name} already exists, treating as success")
                                                return True

                        if hasattr(chunk, '__class__') and chunk.__class__.__name__ == 'ResultMessage':
                            if hasattr(chunk, 'result'):
                                print(f"ResultMessage content: {chunk.result[:200]}...")
                                import re
                                import json
                                json_match = re.search(r'\{.*?"branch_created".*?\}', chunk.result, re.DOTALL)
                                if json_match:
                                    try:
                                        result = json.loads(json_match.group(0))
                                        print(f"Parsed result: {result}")
                                        if result.get('branch_created'):
                                            print(f"✓ Branch {branch_name} created successfully")
                                            return True
                                    except json.JSONDecodeError as e:
                                        print(f"JSON decode error: {e}")
                                        pass
                    except Exception as chunk_error:
                        print(f"Error processing chunk #{chunk_count}: {chunk_error}")
                        continue
                
                # If we got here without returning, check if branch was created successfully
                if chunk_count > 0:
                    print(f"Processed {chunk_count} chunks, assuming branch creation succeeded")
                    return True
                    
            except ExceptionGroup as eg:
                print(f"Error in branch creation - ExceptionGroup caught (attempt {attempt + 1}/{max_attempts})")
                print(f"ExceptionGroup message: {eg}")
                if attempt < max_attempts - 1:
                    print(f"Retrying after ExceptionGroup... (attempt {attempt + 2}/{max_attempts})")
                    await asyncio.sleep(1)
                    continue
                else:
                    print("Max retry attempts reached for branch creation")
            except Exception as e:
                print(f"Error in branch creation async generator (attempt {attempt + 1}/{max_attempts}): {e}")
                import traceback
                print(traceback.format_exc())
                if attempt < max_attempts - 1:
                    print(f"Retrying... (attempt {attempt + 2}/{max_attempts})")
                    await asyncio.sleep(1)
                    continue

        except Exception as e:
            print(f"Error creating branch (attempt {attempt + 1}/{max_attempts}): {e}")
            if attempt < max_attempts - 1:
                print(f"Retrying... (attempt {attempt + 2}/{max_attempts})")
                await asyncio.sleep(1)
                continue

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

    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            result_generator = query(
                prompt=analysis_prompt,
                options=ClaudeCodeOptions(
                    mcp_servers={"github": github_server_config},
                    mcp_tools=["mcp__github__get_file_contents"],
                    allowed_tools=["mcp__github__get_file_contents"]
                )
            )

            chunk_count = 0
            try:
                async for chunk in result_generator:
                    chunk_count += 1
                    print(f"\n--- Repository Analysis Chunk #{chunk_count} ---")
                    print(f"Chunk type: {type(chunk).__name__}")

                    # Print full chunk content for debugging
                    print(f"Full chunk content:\n{chunk}")

                    # Log chunk content based on type
                    if hasattr(chunk, 'content') and isinstance(chunk.content, list):
                        print(f"Content items: {len(chunk.content)}")
                        for i, item in enumerate(chunk.content):
                            if isinstance(item, dict):
                                print(f"  Item {i}: type={item.get('type')}")
                                if item.get('type') == 'tool_use':
                                    print(f"    Tool: {item.get('name')}")
                                    print(f"    Input: {item.get('input')}")
                                elif item.get('type') == 'tool_result':
                                    print(f"    Tool result preview: {str(item.get('content'))[:100]}...")
                                    print(f"    Is error: {item.get('is_error', False)}")

                    if hasattr(chunk, '__class__') and chunk.__class__.__name__ == 'ResultMessage':
                        if hasattr(chunk, 'result'):
                            print(f"ResultMessage content preview: {chunk.result[:200]}...")
                            import re
                            import json
                            # Look for JSON in code blocks first
                            json_code_match = re.search(r'```json\s*(\{.*?\})\s*```', chunk.result, re.DOTALL)
                            if json_code_match:
                                json_str = json_code_match.group(1)
                            else:
                                # Fall back to raw JSON
                                json_match = re.search(r'(\{.*?"files_to_modify".*?\})', chunk.result, re.DOTALL)
                                json_str = json_match.group(1) if json_match else None

                            if json_str:
                                try:
                                    result = json.loads(json_str)
                                    files_to_modify = result.get('files_to_modify', [])
                                    print(f"Parsed result: {result}")
                                    print(f"✓ Identified {len(files_to_modify)} files to modify")
                                    for f in files_to_modify:
                                        print(f"  - {f.get('path')}: {f.get('reason')}")
                                    return files_to_modify
                                except json.JSONDecodeError as e:
                                    print(f"JSON decode error: {e}")
                                    pass
                                    
                # If we got here without finding files, return empty list
                if chunk_count > 0:
                    print(f"Processed {chunk_count} chunks but no files identified")
                    return []
                    
            except ExceptionGroup as eg:
                print(f"Error in repository analysis - ExceptionGroup caught (attempt {attempt + 1}/{max_attempts})")
                print(f"ExceptionGroup message: {eg}")
                if attempt < max_attempts - 1:
                    print(f"Retrying after ExceptionGroup... (attempt {attempt + 2}/{max_attempts})")
                    await asyncio.sleep(1)
                    continue
                else:
                    print("Max retry attempts reached for repository analysis")
            except Exception as e:
                print(f"Error in async generator (attempt {attempt + 1}/{max_attempts}): {e}")
                import traceback
                print(traceback.format_exc())
                if attempt < max_attempts - 1:
                    print(f"Retrying... (attempt {attempt + 2}/{max_attempts})")
                    await asyncio.sleep(1)
                    continue

        except Exception as e:
            print(f"Error analyzing repository (attempt {attempt + 1}/{max_attempts}): {e}")
            if attempt < max_attempts - 1:
                print(f"Retrying... (attempt {attempt + 2}/{max_attempts})")
                await asyncio.sleep(1)
                continue

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

    max_attempts = 3
    for attempt in range(max_attempts):
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

            chunk_count = 0
            try:
                async for chunk in result_generator:
                    try:
                        chunk_count += 1
                        print(f"\n--- File Modification Chunk #{chunk_count} ---")
                        print(f"Chunk type: {type(chunk).__name__}")

                        # Print full chunk content for debugging
                        print(f"Full chunk content:\n{chunk}")

                        # Log chunk content based on type
                        if hasattr(chunk, 'content') and isinstance(chunk.content, list):
                            print(f"Content items: {len(chunk.content)}")
                            for i, item in enumerate(chunk.content):
                                if isinstance(item, dict):
                                    print(f"  Item {i}: type={item.get('type')}")
                                    if item.get('type') == 'tool_use':
                                        print(f"    Tool: {item.get('name')}")
                                        print(f"    Input: {item.get('input')}")
                                        # For file modification, show more details about the tool inputs
                                        if item.get('name') == 'mcp__github__get_file_contents':
                                            print(f"      Reading file: {item.get('input', {}).get('path')}")
                                        elif item.get('name') == 'mcp__github__create_or_update_file':
                                            input_data = item.get('input', {})
                                            print(f"      Updating file: {input_data.get('path')}")
                                            print(f"      Commit message: {input_data.get('message')}")
                                            content_preview = str(input_data.get('content', ''))[:100]
                                            print(f"      Content preview: {content_preview}...")
                                    elif item.get('type') == 'tool_result':
                                        print(f"    Tool result preview: {str(item.get('content'))[:100]}...")
                                        print(f"    Is error: {item.get('is_error', False)}")
                                        if item.get('is_error'):
                                            print(f"    Error content: {item.get('content')}")

                        if hasattr(chunk, '__class__') and chunk.__class__.__name__ == 'ResultMessage':
                            if hasattr(chunk, 'result'):
                                print(f"ResultMessage content preview: {chunk.result[:200]}...")
                                import re
                                import json
                                json_match = re.search(r'\{.*?"modified".*?\}', chunk.result, re.DOTALL)
                                if json_match:
                                    try:
                                        result = json.loads(json_match.group(0))
                                        print(f"Parsed result: {result}")
                                        if result.get('modified'):
                                            modification_description = result.get('description', 'Updated file')
                                            print(f"✓ Modified {file_path}: {modification_description}")
                                            return {
                                                "path": file_path,
                                                "description": modification_description
                                            }
                                        elif result.get('skipped'):
                                            print(f"⚠️ Skipped {file_path}: {result.get('reason', 'unknown')}")
                                            return None
                                    except json.JSONDecodeError as e:
                                        print(f"JSON decode error: {e}")
                                        pass
                    except Exception as chunk_error:
                        print(f"Error processing chunk #{chunk_count}: {chunk_error}")
                        continue
                        
                # If we got here without returning, check if file was modified
                if chunk_count > 0:
                    print(f"Processed {chunk_count} chunks for file modification")
                    return {
                        "path": file_path,
                        "description": "File modified"
                    }
                    
            except ExceptionGroup as eg:
                print(f"Error in file modification - ExceptionGroup caught (attempt {attempt + 1}/{max_attempts})")
                print(f"ExceptionGroup message: {eg}")
                if attempt < max_attempts - 1:
                    print(f"Retrying after ExceptionGroup... (attempt {attempt + 2}/{max_attempts})")
                    await asyncio.sleep(1)
                    continue
                else:
                    print("Max retry attempts reached for file modification")
            except Exception as e:
                print(f"Error in file modification async generator (attempt {attempt + 1}/{max_attempts}): {e}")
                import traceback
                print(traceback.format_exc())
                if attempt < max_attempts - 1:
                    print(f"Retrying... (attempt {attempt + 2}/{max_attempts})")
                    await asyncio.sleep(1)
                    continue

        except Exception as e:
            print(f"Error modifying {file_path} (attempt {attempt + 1}/{max_attempts}): {e}")
            if attempt < max_attempts - 1:
                print(f"Retrying... (attempt {attempt + 2}/{max_attempts})")
                await asyncio.sleep(1)
                continue

    return None