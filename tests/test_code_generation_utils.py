"""Unit tests for the code generation utilities module."""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch, Mock
from claude_code_sdk.types import McpServerConfig

from src.lib.jira_to_pr.models import RepositoryInfo, TicketData
from src.lib.jira_to_pr.code_generation_utils import (
    create_branch, analyze_repository, modify_file
)


class TestCreateBranch:
    """Test cases for the create_branch function."""
    
    @pytest.mark.asyncio
    async def test_create_branch_success(self):
        """Test successful branch creation."""
        repo = RepositoryInfo(
            name="test-repo",
            full_name="user/test-repo",
            url="http://github.com/user/test-repo",
            clone_url="http://github.com/user/test-repo.git",
            ssh_url="git@github.com:user/test-repo.git",
            default_branch="main"
        )
        
        github_config = McpServerConfig(
            command="docker",
            args=["run", "-i", "--rm"],
            env={"GITHUB_PERSONAL_ACCESS_TOKEN": "test-token"}
        )
        
        # Mock the query function
        with patch('src.lib.jira_to_pr.code_generation_utils.query') as mock_query:
            # Create a mock async generator
            async def mock_generator():
                # Simulate a successful result
                result = Mock()
                result.__class__.__name__ = 'ResultMessage'
                result.result = '{"branch_created": true, "branch_name": "feature/test-123"}'
                yield result
            
            mock_query.return_value = mock_generator()
            
            result = await create_branch(repo, "feature/test-123", github_config)
            
            assert result is True
            mock_query.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_branch_already_exists(self):
        """Test branch creation when branch already exists."""
        repo = RepositoryInfo(
            name="test-repo",
            full_name="user/test-repo",
            url="http://github.com/user/test-repo",
            clone_url="http://github.com/user/test-repo.git",
            ssh_url="git@github.com:user/test-repo.git",
            default_branch="main"
        )
        
        github_config = McpServerConfig(
            command="docker",
            args=["run", "-i", "--rm"],
            env={"GITHUB_PERSONAL_ACCESS_TOKEN": "test-token"}
        )
        
        with patch('src.lib.jira_to_pr.code_generation_utils.query') as mock_query:
            # Create a mock async generator that simulates branch exists error
            async def mock_generator():
                # Simulate tool result with error
                chunk = Mock()
                chunk.content = [{
                    'type': 'tool_result',
                    'is_error': True,
                    'content': 'Branch already exists'
                }]
                yield chunk
            
            mock_query.return_value = mock_generator()
            
            result = await create_branch(repo, "feature/test-123", github_config)
            
            # Should treat "already exists" as success
            assert result is True
    
    @pytest.mark.asyncio
    async def test_create_branch_with_retry(self):
        """Test branch creation with retry logic on ExceptionGroup."""
        repo = RepositoryInfo(
            name="test-repo",
            full_name="user/test-repo",
            url="http://github.com/user/test-repo",
            clone_url="http://github.com/user/test-repo.git",
            ssh_url="git@github.com:user/test-repo.git",
            default_branch="main"
        )
        
        github_config = McpServerConfig(
            command="docker",
            args=["run", "-i", "--rm"],
            env={"GITHUB_PERSONAL_ACCESS_TOKEN": "test-token"}
        )
        
        with patch('src.lib.jira_to_pr.code_generation_utils.query') as mock_query:
            call_count = 0
            
            # Create a mock async generator that fails first, then succeeds
            async def mock_generator():
                nonlocal call_count
                call_count += 1
                
                if call_count == 1:
                    # First attempt - raise ExceptionGroup
                    raise ExceptionGroup("Test error", [Exception("Nested error")])
                else:
                    # Second attempt - succeed
                    result = Mock()
                    result.__class__.__name__ = 'ResultMessage'
                    result.result = '{"branch_created": true, "branch_name": "feature/test-123"}'
                    yield result
            
            mock_query.side_effect = [mock_generator(), mock_generator()]
            
            # Mock asyncio.sleep to speed up test
            with patch('asyncio.sleep', return_value=None):
                result = await create_branch(repo, "feature/test-123", github_config)
            
            assert result is True
            assert mock_query.call_count == 2  # Should retry once


class TestAnalyzeRepository:
    """Test cases for the analyze_repository function."""
    
    @pytest.mark.asyncio
    async def test_analyze_repository_success(self):
        """Test successful repository analysis."""
        repo = RepositoryInfo(
            name="test-repo",
            full_name="user/test-repo",
            url="http://github.com/user/test-repo",
            clone_url="http://github.com/user/test-repo.git",
            ssh_url="git@github.com:user/test-repo.git",
            default_branch="main",
            primary_language="Python"
        )
        
        ticket = TicketData(
            id="1",
            key="TEST-123",
            summary="Fix bug in auth module",
            description="Authentication fails for special characters",
            status="To Do",
            priority="High",
            reporter="Test User",
            created="2024-01-01T10:00:00Z",
            updated="2024-01-01T10:00:00Z",
            ticket_type="Bug",
            project_key="TEST",
            url="http://test.com/TEST-123"
        )
        
        github_config = McpServerConfig(
            command="docker",
            args=["run", "-i", "--rm"],
            env={"GITHUB_PERSONAL_ACCESS_TOKEN": "test-token"}
        )
        
        with patch('src.lib.jira_to_pr.code_generation_utils.query') as mock_query:
            # Create a mock async generator
            async def mock_generator():
                result = Mock()
                result.__class__.__name__ = 'ResultMessage'
                result.result = '''```json
                {
                    "files_to_modify": [
                        {
                            "path": "src/auth.py",
                            "reason": "Contains authentication logic that needs fixing"
                        },
                        {
                            "path": "tests/test_auth.py",
                            "reason": "Needs new test cases for special characters"
                        }
                    ]
                }
                ```'''
                yield result
            
            mock_query.return_value = mock_generator()
            
            result = await analyze_repository(repo, ticket, github_config)
            
            assert len(result) == 2
            assert result[0]['path'] == "src/auth.py"
            assert result[1]['path'] == "tests/test_auth.py"
            assert "authentication" in result[0]['reason'].lower()
    
    @pytest.mark.asyncio
    async def test_analyze_repository_no_files_found(self):
        """Test repository analysis when no files need modification."""
        repo = RepositoryInfo(
            name="test-repo",
            full_name="user/test-repo",
            url="http://github.com/user/test-repo",
            clone_url="http://github.com/user/test-repo.git",
            ssh_url="git@github.com:user/test-repo.git",
            default_branch="main",
            primary_language="Python"
        )
        
        ticket = TicketData(
            id="1",
            key="TEST-123",
            summary="Update documentation",
            description="Update README",
            status="To Do",
            priority="Low",
            reporter="Test User",
            created="2024-01-01T10:00:00Z",
            updated="2024-01-01T10:00:00Z",
            ticket_type="Task",
            project_key="TEST",
            url="http://test.com/TEST-123"
        )
        
        github_config = McpServerConfig(
            command="docker",
            args=["run", "-i", "--rm"],
            env={"GITHUB_PERSONAL_ACCESS_TOKEN": "test-token"}
        )
        
        with patch('src.lib.jira_to_pr.code_generation_utils.query') as mock_query:
            # Create a mock async generator that returns no files
            async def mock_generator():
                result = Mock()
                result.__class__.__name__ = 'ResultMessage'
                result.result = '{"files_to_modify": []}'
                yield result
            
            mock_query.return_value = mock_generator()
            
            result = await analyze_repository(repo, ticket, github_config)
            
            assert result == []


class TestModifyFile:
    """Test cases for the modify_file function."""
    
    @pytest.mark.asyncio
    async def test_modify_file_success(self):
        """Test successful file modification."""
        file_info = {
            "path": "src/auth.py",
            "reason": "Fix authentication bug"
        }
        
        repo = RepositoryInfo(
            name="test-repo",
            full_name="user/test-repo",
            url="http://github.com/user/test-repo",
            clone_url="http://github.com/user/test-repo.git",
            ssh_url="git@github.com:user/test-repo.git",
            default_branch="main"
        )
        
        ticket = TicketData(
            id="1",
            key="TEST-123",
            summary="Fix auth bug",
            description="Fix authentication",
            status="To Do",
            priority="High",
            reporter="Test User",
            created="2024-01-01T10:00:00Z",
            updated="2024-01-01T10:00:00Z",
            ticket_type="Bug",
            project_key="TEST",
            url="http://test.com/TEST-123"
        )
        
        github_config = McpServerConfig(
            command="docker",
            args=["run", "-i", "--rm"],
            env={"GITHUB_PERSONAL_ACCESS_TOKEN": "test-token"}
        )
        
        with patch('src.lib.jira_to_pr.code_generation_utils.query') as mock_query:
            # Create a mock async generator
            async def mock_generator():
                # First chunk - tool use (reading file)
                chunk1 = Mock()
                chunk1.content = [{
                    'type': 'tool_use',
                    'name': 'mcp__github__get_file_contents',
                    'input': {'path': 'src/auth.py'}
                }]
                yield chunk1
                
                # Second chunk - tool result (file content)
                chunk2 = Mock()
                chunk2.content = [{
                    'type': 'tool_result',
                    'content': [{'type': 'text', 'text': 'file content here'}]
                }]
                yield chunk2
                
                # Third chunk - tool use (updating file)
                chunk3 = Mock()
                chunk3.content = [{
                    'type': 'tool_use',
                    'name': 'mcp__github__create_or_update_file',
                    'input': {
                        'path': 'src/auth.py',
                        'message': '[TEST-123] Update src/auth.py',
                        'content': 'updated content'
                    }
                }]
                yield chunk3
                
                # Final chunk - result
                result = Mock()
                result.__class__.__name__ = 'ResultMessage'
                result.result = '{"file": "src/auth.py", "modified": true, "description": "Fixed authentication bug"}'
                yield result
            
            mock_query.return_value = mock_generator()
            
            result = await modify_file(file_info, repo, "feature/test-123", ticket, github_config)
            
            assert result is not None
            assert result['path'] == "src/auth.py"
            assert result['description'] == "Fixed authentication bug"
    
    @pytest.mark.asyncio
    async def test_modify_file_skip_large_file(self):
        """Test that large files are skipped."""
        file_info = {
            "path": "large_file.bin",
            "reason": "Update large file"
        }
        
        repo = RepositoryInfo(
            name="test-repo",
            full_name="user/test-repo",
            url="http://github.com/user/test-repo",
            clone_url="http://github.com/user/test-repo.git",
            ssh_url="git@github.com:user/test-repo.git",
            default_branch="main"
        )
        
        ticket = TicketData(
            id="1",
            key="TEST-123",
            summary="Update file",
            description="Update large file",
            status="To Do",
            priority="Low",
            reporter="Test User",
            created="2024-01-01T10:00:00Z",
            updated="2024-01-01T10:00:00Z",
            ticket_type="Task",
            project_key="TEST",
            url="http://test.com/TEST-123"
        )
        
        github_config = McpServerConfig(
            command="docker",
            args=["run", "-i", "--rm"],
            env={"GITHUB_PERSONAL_ACCESS_TOKEN": "test-token"}
        )
        
        with patch('src.lib.jira_to_pr.code_generation_utils.query') as mock_query:
            # Create a mock async generator that skips the file
            async def mock_generator():
                result = Mock()
                result.__class__.__name__ = 'ResultMessage'
                result.result = '{"skipped": true, "reason": "file too large"}'
                yield result
            
            mock_query.return_value = mock_generator()
            
            result = await modify_file(file_info, repo, "feature/test-123", ticket, github_config)
            
            assert result is None  # Skipped files return None


class TestRetryLogic:
    """Test retry logic implementation across functions."""
    
    def test_all_functions_have_retry_logic(self):
        """Verify that all main functions implement retry logic."""
        import inspect
        
        # Check create_branch
        source = inspect.getsource(create_branch)
        assert "max_attempts" in source
        assert "for attempt in range(max_attempts)" in source
        
        # Check analyze_repository
        source = inspect.getsource(analyze_repository)
        assert "max_attempts" in source
        assert "for attempt in range(max_attempts)" in source
        
        # Check modify_file
        source = inspect.getsource(modify_file)
        assert "max_attempts" in source
        assert "for attempt in range(max_attempts)" in source
    
    def test_exception_group_handling(self):
        """Verify ExceptionGroup is properly handled."""
        import inspect
        
        for func in [create_branch, analyze_repository, modify_file]:
            source = inspect.getsource(func)
            assert "except ExceptionGroup" in source
            assert "Retrying after ExceptionGroup" in source