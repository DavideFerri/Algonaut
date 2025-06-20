import unittest
from unittest.mock import Mock, patch, MagicMock
import os
import sys

# Add parent directory to path to import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dependencies.pull_request_creation import create_pull_request


class TestPullRequestCreation(unittest.TestCase):
    """Test cases for pull request creation functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_owner = "test_owner"
        self.test_repo = "test_repo"
        self.test_title = "Test PR Title"
        self.test_body = "Test PR Body"
        self.test_head = "feature/test-branch"
        self.test_base = "main"
    
    @patch('dependencies.pull_request_creation.Github')
    def test_create_pull_request_success(self, mock_github):
        """Test successful pull request creation"""
        # Mock GitHub API
        mock_repo = Mock()
        mock_pr = Mock()
        mock_pr.number = 123
        mock_pr.html_url = "https://github.com/test_owner/test_repo/pull/123"
        
        mock_repo.create_pull.return_value = mock_pr
        mock_github.return_value.get_repo.return_value = mock_repo
        
        # Call function
        result = create_pull_request(
            token="test_token",
            owner=self.test_owner,
            repo=self.test_repo,
            title=self.test_title,
            body=self.test_body,
            head=self.test_head,
            base=self.test_base
        )
        
        # Assertions
        self.assertIsNotNone(result)
        self.assertEqual(result.number, 123)
        mock_repo.create_pull.assert_called_once_with(
            title=self.test_title,
            body=self.test_body,
            head=self.test_head,
            base=self.test_base
        )
    
    @patch('dependencies.pull_request_creation.Github')
    def test_create_pull_request_with_empty_body(self, mock_github):
        """Test pull request creation with empty body"""
        # Mock GitHub API
        mock_repo = Mock()
        mock_pr = Mock()
        mock_pr.number = 124
        mock_pr.html_url = "https://github.com/test_owner/test_repo/pull/124"
        
        mock_repo.create_pull.return_value = mock_pr
        mock_github.return_value.get_repo.return_value = mock_repo
        
        # Call function with empty body
        result = create_pull_request(
            token="test_token",
            owner=self.test_owner,
            repo=self.test_repo,
            title=self.test_title,
            body="",
            head=self.test_head,
            base=self.test_base
        )
        
        # Assertions
        self.assertIsNotNone(result)
        mock_repo.create_pull.assert_called_once()
    
    @patch('dependencies.pull_request_creation.Github')
    def test_create_pull_request_invalid_branch(self, mock_github):
        """Test pull request creation with invalid branch"""
        # Mock GitHub API to raise exception
        mock_repo = Mock()
        mock_repo.create_pull.side_effect = Exception("Branch not found")
        mock_github.return_value.get_repo.return_value = mock_repo
        
        # Call function and expect exception
        with self.assertRaises(Exception) as context:
            create_pull_request(
                token="test_token",
                owner=self.test_owner,
                repo=self.test_repo,
                title=self.test_title,
                body=self.test_body,
                head="non-existent-branch",
                base=self.test_base
            )
        
        self.assertIn("Branch not found", str(context.exception))
    
    @patch('dependencies.pull_request_creation.Github')
    def test_create_pull_request_duplicate(self, mock_github):
        """Test handling of duplicate pull request"""
        # Mock GitHub API to raise specific exception
        mock_repo = Mock()
        mock_repo.create_pull.side_effect = Exception("A pull request already exists")
        mock_github.return_value.get_repo.return_value = mock_repo
        
        # Call function and expect exception
        with self.assertRaises(Exception) as context:
            create_pull_request(
                token="test_token",
                owner=self.test_owner,
                repo=self.test_repo,
                title=self.test_title,
                body=self.test_body,
                head=self.test_head,
                base=self.test_base
            )
        
        self.assertIn("pull request already exists", str(context.exception))


if __name__ == '__main__':
    unittest.main()