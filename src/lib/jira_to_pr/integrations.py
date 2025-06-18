"""Integration layer for external APIs: Jira, GitHub, and Claude Code SDK."""

import json
import asyncio
import random
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime
from pathlib import Path

import httpx
from atlassian import Jira
from github import Github, Repository
from claude_code_sdk import query, ClaudeCodeOptions

from .models import (
    TicketData, RepositoryInfo, CodeGenerationRequest, CodeGenerationResult,
    PullRequestData, CodeChange, RepositoryAnalysisResult
)
from .constants import (
    TicketStatus, TicketPriority, ProgrammingLanguage, 
    LANGUAGE_PATTERNS, FRAMEWORK_PATTERNS
)


class JiraClient:
    """Jira API client for fetching and managing tickets."""
    
    def __init__(self, url: str, email: str, api_token: str):
        self.client = Jira(url=url, username=email, password=api_token)
        self.base_url = url
    
    async def get_active_sprint_tickets(self, project_key: str) -> List[TicketData]:
        """Fetch all unassigned tickets from the active sprint."""
        # Get active sprint
        boards = self.client.boards()
        project_board = None
        for board in boards:
            if project_key.lower() in board['name'].lower():
                project_board = board
                break
        
        if not project_board:
            raise ValueError(f"No board found for project {project_key}")
        
        # Get active sprint
        sprints = self.client.sprints(project_board['id'])
        active_sprint = None
        for sprint in sprints:
            if sprint['state'] == 'active':
                active_sprint = sprint
                break
        
        if not active_sprint:
            return []
        
        # Get tickets from active sprint that are unassigned and in "To Do" status
        jql = f'sprint = {active_sprint["id"]} AND assignee is EMPTY AND status = "To Do"'
        issues = self.client.jql(jql)['issues']
        
        tickets = []
        for issue in issues:
            ticket = self._parse_jira_issue(issue)
            tickets.append(ticket)
        
        return tickets
    
    def _parse_jira_issue(self, issue: Dict) -> TicketData:
        """Parse Jira issue JSON into TicketData model."""
        fields = issue['fields']
        
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
            summary=fields['summary'],
            description=fields.get('description', ''),
            status=TicketStatus(fields['status']['name']),
            priority=TicketPriority(fields['priority']['name']),
            assignee=fields['assignee']['displayName'] if fields['assignee'] else None,
            reporter=fields['reporter']['displayName'],
            created=datetime.fromisoformat(fields['created'].replace('Z', '+00:00')),
            updated=datetime.fromisoformat(fields['updated'].replace('Z', '+00:00')),
            ticket_type=fields['issuetype']['name'],
            labels=[label for label in fields.get('labels', [])],
            components=[comp['name'] for comp in fields.get('components', [])],
            fix_versions=[ver['name'] for ver in fields.get('fixVersions', [])],
            project_key=fields['project']['key'],
            url=f"{self.base_url}/browse/{issue['key']}",
            acceptance_criteria=acceptance_criteria,
            story_points=story_points
        )
    
    async def update_ticket_status(self, ticket_id: str, status: str) -> bool:
        """Update ticket status and add comment about PR creation."""
        try:
            transitions = self.client.get_issue_transitions(ticket_id)
            target_transition = None
            
            for transition in transitions['transitions']:
                if transition['to']['name'].lower() == status.lower():
                    target_transition = transition
                    break
            
            if target_transition:
                self.client.issue_transition(ticket_id, target_transition['id'])
                return True
            return False
        except Exception as e:
            print(f"Error updating ticket status: {e}")
            return False
    
    async def add_comment(self, ticket_id: str, comment: str) -> bool:
        """Add a comment to a Jira ticket."""
        try:
            self.client.issue_add_comment(ticket_id, comment)
            return True
        except Exception as e:
            print(f"Error adding comment: {e}")
            return False


class GitHubClient:
    """GitHub API client for repository analysis and PR management."""
    
    def __init__(self, token: str):
        self.client = Github(token)
        self.user = self.client.get_user()
    
    async def get_accessible_repositories(self) -> List[RepositoryInfo]:
        """Get all repositories the user has access to."""
        repos = []
        
        # Get user's repositories
        for repo in self.user.get_repos():
            if not repo.fork and not repo.archived:
                repo_info = await self._analyze_repository(repo)
                repos.append(repo_info)
        
        # Get organization repositories
        for org in self.user.get_orgs():
            for repo in org.get_repos():
                if not repo.fork and not repo.archived and repo.permissions.push:
                    repo_info = await self._analyze_repository(repo)
                    repos.append(repo_info)
        
        return repos
    
    async def _analyze_repository(self, repo: Repository) -> RepositoryInfo:
        """Analyze a repository to determine its characteristics."""
        languages = repo.get_languages()
        primary_language = None
        if languages:
            primary_language = max(languages, key=languages.get)
            if primary_language in [lang.value for lang in ProgrammingLanguage]:
                primary_language = ProgrammingLanguage(primary_language)
        
        # Detect frameworks
        frameworks = await self._detect_frameworks(repo)
        
        # Check for various configuration files
        has_package_json = self._has_file(repo, "package.json")
        has_requirements_txt = self._has_file(repo, "requirements.txt")
        has_dockerfile = self._has_file(repo, "Dockerfile")
        has_makefile = self._has_file(repo, "Makefile")
        has_ci_config = (
            self._has_file(repo, ".github/workflows") or
            self._has_file(repo, ".gitlab-ci.yml") or
            self._has_file(repo, "Jenkinsfile")
        )
        
        return RepositoryInfo(
            name=repo.name,
            full_name=repo.full_name,
            url=repo.html_url,
            clone_url=repo.clone_url,
            ssh_url=repo.ssh_url,
            default_branch=repo.default_branch,
            primary_language=primary_language,
            languages=languages,
            frameworks=frameworks,
            has_package_json=has_package_json,
            has_requirements_txt=has_requirements_txt,
            has_dockerfile=has_dockerfile,
            has_makefile=has_makefile,
            has_ci_config=has_ci_config
        )
    
    async def _detect_frameworks(self, repo: Repository) -> List[str]:
        """Detect frameworks used in the repository."""
        frameworks = []
        
        # Check package.json for JS frameworks
        if self._has_file(repo, "package.json"):
            try:
                package_json = repo.get_contents("package.json")
                content = json.loads(package_json.decoded_content)
                dependencies = {**content.get("dependencies", {}), **content.get("devDependencies", {})}
                
                for framework, patterns in FRAMEWORK_PATTERNS.items():
                    if any(pattern in dependencies for pattern in patterns):
                        frameworks.append(framework)
            except:
                pass
        
        # Check requirements.txt for Python frameworks
        if self._has_file(repo, "requirements.txt"):
            try:
                requirements = repo.get_contents("requirements.txt")
                content = requirements.decoded_content.decode()
                
                for framework, patterns in FRAMEWORK_PATTERNS.items():
                    if any(pattern.lower() in content.lower() for pattern in patterns):
                        frameworks.append(framework)
            except:
                pass
        
        return frameworks
    
    def _has_file(self, repo: Repository, file_path: str) -> bool:
        """Check if a file exists in the repository."""
        try:
            repo.get_contents(file_path)
            return True
        except:
            return False
    
    async def create_pull_request(self, repo_name: str, pr_data: PullRequestData) -> Optional[PullRequestData]:
        """Create a pull request in the specified repository."""
        try:
            repo = self.client.get_repo(repo_name)
            
            pr = repo.create_pull(
                title=pr_data.title,
                body=pr_data.body,
                head=pr_data.head_branch,
                base=pr_data.base_branch,
                draft=pr_data.draft
            )
            
            # Add assignees and reviewers
            if pr_data.assignees:
                pr.add_to_assignees(*pr_data.assignees)
            
            if pr_data.reviewers:
                pr.create_review_request(reviewers=pr_data.reviewers)
            
            # Add labels
            if pr_data.labels:
                pr.add_to_labels(*pr_data.labels)
            
            # Update PR data with created PR info
            pr_data.url = pr.html_url
            pr_data.number = pr.number
            
            return pr_data
            
        except Exception as e:
            print(f"Error creating PR: {e}")
            return None
    
    async def create_branch(self, repo_name: str, branch_name: str, base_branch: str = "main") -> bool:
        """Create a new branch in the repository."""
        try:
            repo = self.client.get_repo(repo_name)
            base_sha = repo.get_branch(base_branch).commit.sha
            repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=base_sha)
            return True
        except Exception as e:
            print(f"Error creating branch: {e}")
            return False


class ClaudeCodeClient:
    """Claude Code SDK client for AI-powered code generation."""
    
    def __init__(self):
        self.default_options = ClaudeCodeOptions(
            system_prompt="You are a senior software engineer implementing Jira tickets.",
            max_turns=5,
            allowed_tools=["Read", "Write", "Edit", "MultiEdit", "Bash", "Glob", "Grep"],
            permission_mode="requestEdits"
        )
    
    async def generate_code(self, request: CodeGenerationRequest) -> CodeGenerationResult:
        """Generate code implementation for a ticket."""
        try:
            # Prepare the prompt
            prompt = self._build_generation_prompt(request)
            
            # Configure options for this specific request
            options = ClaudeCodeOptions(
                system_prompt=f"You are implementing code in {request.repository.primary_language}",
                cwd=request.repository.local_path,
                allowed_tools=self.default_options.allowed_tools,
                permission_mode=self.default_options.permission_mode,
                max_turns=self.default_options.max_turns
            )
            
            # Generate code
            changes = []
            async for message in query(prompt=prompt, options=options):
                # Process Claude's responses and extract file changes
                if hasattr(message, 'tool_calls') and message.tool_calls:
                    for tool_call in message.tool_calls:
                        if tool_call.name in ["Write", "Edit", "MultiEdit"]:
                            change = self._extract_code_change(tool_call)
                            if change:
                                changes.append(change)
            
            return CodeGenerationResult(
                success=True,
                changes=changes,
                estimated_review_time=self._estimate_review_time(changes)
            )
            
        except Exception as e:
            return CodeGenerationResult(
                success=False,
                error_message=str(e)
            )
    
    def _build_generation_prompt(self, request: CodeGenerationRequest) -> str:
        """Build the prompt for code generation."""
        prompt = f"""
        Implement the following Jira ticket:
        
        **Ticket ID**: {request.ticket.key}
        **Title**: {request.ticket.summary}
        **Description**: {request.ticket.description}
        
        **Repository**: {request.repository.name}
        **Language**: {request.repository.primary_language}
        **Frameworks**: {', '.join(request.repository.frameworks)}
        
        **Requirements**:
        - Follow existing code patterns and conventions
        - Write tests if test_requirements is True: {request.test_requirements}
        - Ensure code is production-ready
        - Add appropriate error handling
        - Include documentation for new features
        
        **Constraints**:
        {chr(10).join(f'- {constraint}' for constraint in request.constraints)}
        
        **Acceptance Criteria**:
        {request.ticket.acceptance_criteria or 'No specific acceptance criteria provided'}
        
        Please implement the required changes step by step.
        """
        
        return prompt
    
    def _extract_code_change(self, tool_call) -> Optional[CodeChange]:
        """Extract code change information from a tool call."""
        if tool_call.name == "Write":
            return CodeChange(
                file_path=tool_call.args.get("file_path", ""),
                operation="create",
                new_content=tool_call.args.get("content", ""),
                description=f"Created new file: {tool_call.args.get('file_path', '')}"
            )
        elif tool_call.name == "Edit":
            return CodeChange(
                file_path=tool_call.args.get("file_path", ""),
                operation="modify",
                old_content=tool_call.args.get("old_string", ""),
                new_content=tool_call.args.get("new_string", ""),
                description=f"Modified file: {tool_call.args.get('file_path', '')}"
            )
        elif tool_call.name == "MultiEdit":
            # For MultiEdit, we create a single change representing all edits
            return CodeChange(
                file_path=tool_call.args.get("file_path", ""),
                operation="modify",
                description=f"Multiple edits to: {tool_call.args.get('file_path', '')}"
            )
        
        return None
    
    def _estimate_review_time(self, changes: List[CodeChange]) -> int:
        """Estimate review time in minutes based on changes."""
        base_time = 10  # 10 minutes base
        time_per_file = 5  # 5 minutes per file
        
        total_time = base_time + (len(changes) * time_per_file)
        
        # Add complexity factors
        for change in changes:
            if change.complexity_score > 5:
                total_time += 10
            if change.requires_tests:
                total_time += 5
        
        return total_time


class RepositoryAnalyzer:
    """Analyzes repositories to determine relevance to Jira tickets."""
    
    def __init__(self, llm_client):
        self.llm_client = llm_client
    
    async def analyze_ticket_repository_relevance(
        self, 
        ticket: TicketData, 
        repositories: List[RepositoryInfo]
    ) -> List[RepositoryAnalysisResult]:
        """Analyze which repositories are relevant for a given ticket."""
        results = []
        
        for repo in repositories:
            try:
                # Use LLM to analyze relevance
                prompt = f"""
                Analyze if this repository is relevant for implementing the following Jira ticket:
                
                Ticket: {ticket.key} - {ticket.summary}
                Description: {ticket.description}
                Components: {', '.join(ticket.components)}
                Labels: {', '.join(ticket.labels)}
                
                Repository: {repo.name}
                Language: {repo.primary_language}
                Frameworks: {', '.join(repo.frameworks)}
                
                Rate relevance from 0-1 and provide reasoning.
                Return JSON with: {{"relevance_score": float, "reasoning": str, "confidence": float}}
                """
                
                # This would use your LLM client to analyze
                # For now, using simple heuristics
                relevance_score = self._calculate_heuristic_relevance(ticket, repo)
                
                result = RepositoryAnalysisResult(
                    repository=repo,
                    relevance_score=relevance_score,
                    confidence=0.8,
                    reasoning=f"Based on ticket components and repository characteristics"
                )
                
                results.append(result)
                
            except Exception as e:
                print(f"Error analyzing repository {repo.name}: {e}")
                continue
        
        # Sort by relevance score
        results.sort(key=lambda x: x.relevance_score, reverse=True)
        return results
    
    def _calculate_heuristic_relevance(self, ticket: TicketData, repo: RepositoryInfo) -> float:
        """Calculate relevance using simple heuristics."""
        score = 0.0
        
        # Check if ticket components match repository name/description
        for component in ticket.components:
            if component.lower() in repo.name.lower():
                score += 0.3
        
        # Check labels
        for label in ticket.labels:
            if label.lower() in repo.name.lower():
                score += 0.2
        
        # Check if ticket mentions specific technologies
        if ticket.description:
            desc_lower = ticket.description.lower()
            if repo.primary_language and repo.primary_language.value.lower() in desc_lower:
                score += 0.3
            
            for framework in repo.frameworks:
                if framework.lower() in desc_lower:
                    score += 0.2
        
        return min(score, 1.0)


# Factory functions for creating clients
def create_jira_client() -> JiraClient:
    """Create Jira client from settings."""
    from dependencies.settings import settings
    return JiraClient(
        url=settings.jira_url,
        email=settings.jira_email,
        api_token=settings.jira_api_token
    )

def create_github_client() -> GitHubClient:
    """Create GitHub client from settings."""
    from dependencies.settings import settings
    return GitHubClient(token=settings.github_token)

def create_claude_code_client() -> ClaudeCodeClient:
    """Create Claude Code client."""
    return ClaudeCodeClient()