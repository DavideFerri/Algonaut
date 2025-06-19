"""Data models and state schemas for the Jira to PR automation system."""

from typing import Optional, List, Dict, Any, Annotated
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from lib.jira_to_pr.constants import TicketPriority, TicketStatus, ProgrammingLanguage


class TicketData(BaseModel):
    """Model for Jira ticket information."""
    id: str
    key: str
    summary: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TicketStatus] = None
    priority: Optional[TicketPriority] = None
    assignee: Optional[str] = None
    reporter: Optional[str] = None
    created: Optional[datetime] = None
    updated: Optional[datetime] = None
    ticket_type: Optional[str] = None
    labels: List[str] = []
    components: List[str] = []
    fix_versions: List[str] = []
    project_key: str
    url: str
    acceptance_criteria: Optional[str] = None
    story_points: Optional[float] = None
    
    @property
    def priority_weight(self) -> int:
        """Get numeric weight for priority sorting."""
        from .constants import PRIORITY_WEIGHTS
        return PRIORITY_WEIGHTS.get(self.priority, 0)


class RepositoryInfo(BaseModel):
    """Model for GitHub repository information and analysis."""
    name: str
    full_name: str
    url: str
    clone_url: str
    ssh_url: str
    default_branch: str = "main"
    primary_language: Optional[ProgrammingLanguage] = None
    languages: Dict[str, int] = {}
    frameworks: List[str] = []
    has_package_json: bool = False
    has_requirements_txt: bool = False
    has_dockerfile: bool = False
    has_makefile: bool = False
    has_ci_config: bool = False
    local_path: Optional[str] = None
    relevance_score: float = 0.0
    analysis_notes: Optional[str] = None


class CodeChange(BaseModel):
    """Model for a single code change or file modification."""
    file_path: str
    operation: str  # "create", "modify", "delete"
    old_content: Optional[str] = None
    new_content: Optional[str] = None
    diff: Optional[str] = None
    language: Optional[ProgrammingLanguage] = None
    description: Optional[str] = None
    complexity_score: int = 0
    requires_tests: bool = False


class PullRequestData(BaseModel):
    """Model for pull request information."""
    title: str
    body: str
    head_branch: str
    base_branch: str = "main"
    repository: str
    draft: bool = False
    assignees: List[str] = []
    reviewers: List[str] = []
    labels: List[str] = []
    milestone: Optional[str] = None
    url: Optional[str] = None
    number: Optional[int] = None


class WorkflowResult(BaseModel):
    """Model for workflow execution results."""
    success: bool
    ticket_id: str
    repositories_processed: List[str] = []
    pull_requests_created: List[PullRequestData] = []
    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    execution_time: Optional[float] = None
    error_message: Optional[str] = None
    warnings: List[str] = []
    requires_human_review: bool = False
    review_reasons: List[str] = []


class JiraToPRState(BaseModel):
    """Main state model for the Jira to PR workflow graph."""
    # Message history for LangGraph
    messages: Optional[Annotated[List[AnyMessage], add_messages]] = None
    
    # Current workflow state
    current_ticket: Optional[TicketData] = None
    available_tickets: List[TicketData] = []
    selected_repositories: List[RepositoryInfo] = []
    code_changes: List[CodeChange] = []
    pull_requests: List[PullRequestData] = []
    
    # Processing state
    workflow_stage: str = "initialize"
    processing_repo: Optional[str] = None
    current_branch: Optional[str] = None
    
    # Results and metrics
    workflow_result: Optional[WorkflowResult] = None
    error: Optional[str] = None
    
    # Configuration
    max_tickets_per_run: int = 5
    max_repositories_per_ticket: int = 3
    require_human_review: bool = True
    dry_run: bool = False
    
    # Run statistics
    tickets_processed: int = 0
    prs_created: int = 0
    execution_start_time: Optional[datetime] = None
    
    class Config:
        arbitrary_types_allowed = True


class RepositoryAnalysisResult(BaseModel):
    """Result of repository analysis for ticket relevance."""
    repository: RepositoryInfo
    relevance_score: float
    confidence: float
    reasoning: str
    suggested_changes: List[str] = []
    estimated_complexity: int = 1  # 1-5 scale
    requires_domain_knowledge: bool = False


class CodeGenerationRequest(BaseModel):
    """Request model for code generation."""
    ticket: TicketData
    repository: RepositoryInfo
    context_files: List[str] = []
    existing_code_patterns: Dict[str, Any] = {}
    constraints: List[str] = []
    test_requirements: bool = True


class CodeGenerationResult(BaseModel):
    """Result of code generation process."""
    success: bool
    changes: List[CodeChange] = []
    test_files: List[str] = []
    documentation_updates: List[str] = []
    migration_scripts: List[str] = []
    error_message: Optional[str] = None
    warnings: List[str] = []
    estimated_review_time: Optional[int] = None  # minutes
    complexity_analysis: Dict[str, Any] = {}


class QualityGate(BaseModel):
    """Quality gate check result."""
    name: str
    passed: bool
    score: Optional[float] = None
    message: str
    blocking: bool = False
    details: Dict[str, Any] = {}


class SafetyCheck(BaseModel):
    """Safety check result for generated code."""
    security_scan: QualityGate
    code_complexity: QualityGate
    test_coverage: QualityGate
    style_compliance: QualityGate
    dependency_safety: QualityGate
    overall_passed: bool = False
    requires_human_review: bool = False
    review_reasons: List[str] = []