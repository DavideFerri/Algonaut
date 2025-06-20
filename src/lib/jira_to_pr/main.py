"""Main entry point for the Jira to PR automation system."""

import asyncio
import logging
from typing import Optional

from langchain_core.messages import HumanMessage

from lib.jira_to_pr.builder import build_jira_to_pr_graph, create_initial_state
from lib.jira_to_pr.config import validate_jira_to_pr_config, create_sample_env_file
from dependencies.settings import settings


logger = logging.getLogger(__name__)


async def run_jira_to_pr_automation(
    max_tickets: int = 5,
    dry_run: bool = False,
    require_human_review: bool = True
) -> dict:
    """
    Run the Jira to PR automation workflow.
    
    Args:
        max_tickets: Maximum number of tickets to process
        dry_run: Run in dry-run mode (no actual changes)
        require_human_review: Require human review for complex changes
        
    Returns:
        Dictionary with execution results
    """
    logger.info("Starting Jira to PR automation workflow")
    
    # Validate configuration
    config_errors = validate_jira_to_pr_config()
    if config_errors:
        logger.error("Configuration validation failed:")
        for error in config_errors:
            logger.error(f"  - {error}")
        return {
            "success": False, 
            "errors": config_errors,
            "tickets_processed": 0,
            "prs_created": 0
        }
    
    # Create initial state
    initial_state = create_initial_state(
        max_tickets_per_run=max_tickets,
        require_human_review=require_human_review,
        dry_run=dry_run
    )
    
    # Build and compile the workflow graph
    graph = build_jira_to_pr_graph()
    
    try:
        # Run the workflow
        result = await graph.ainvoke(initial_state)
        
        # Extract results
        execution_result = {
            "success": True,
            "tickets_processed": result.get("tickets_processed", 0),
            "prs_created": result.get("prs_created", 0),
            "workflow_result": result.get("workflow_result"),
            "final_stage": result.get("workflow_stage", "unknown"),
            "error": result.get("error")
        }
        
        if execution_result["error"]:
            logger.error(f"Workflow completed with error: {execution_result['error']}")
            execution_result["success"] = False
        else:
            logger.info(f"Workflow completed successfully. "
                       f"Processed {execution_result['tickets_processed']} tickets, "
                       f"created {execution_result['prs_created']} PRs")
        
        return execution_result
        
    except Exception as e:
        logger.error(f"Workflow execution failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "tickets_processed": 0,
            "prs_created": 0
        }


async def run_single_ticket(ticket_key: str, dry_run: bool = True) -> dict:
    """
    Run automation for a specific ticket (useful for testing).
    
    Args:
        ticket_key: Jira ticket key (e.g., "DEV-123")
        dry_run: Run in dry-run mode
        
    Returns:
        Dictionary with execution results
    """
    logger.info(f"Running automation for specific ticket: {ticket_key}")
    
    # Validate ticket format
    if not ticket_key or not isinstance(ticket_key, str):
        return {
            "success": False,
            "error": "Invalid ticket key provided",
            "ticket_key": ticket_key
        }
    
    # Validate configuration
    config_errors = validate_jira_to_pr_config()
    if config_errors:
        logger.error("Configuration validation failed:")
        for error in config_errors:
            logger.error(f"  - {error}")
        return {
            "success": False,
            "errors": config_errors,
            "ticket_key": ticket_key
        }
    
    # Create initial state with specific ticket
    initial_state = create_initial_state(
        max_tickets_per_run=1,
        require_human_review=False,
        dry_run=dry_run,
        specific_ticket=ticket_key
    )
    
    # Build and compile the workflow graph
    graph = build_jira_to_pr_graph()
    
    try:
        # Run the workflow
        result = await graph.ainvoke(initial_state)
        
        return {
            "success": result.get("error") is None,
            "error": result.get("error"),
            "ticket_key": ticket_key,
            "tickets_processed": result.get("tickets_processed", 0),
            "prs_created": result.get("prs_created", 0)
        }
        
    except Exception as e:
        logger.error(f"Single ticket processing failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "ticket_key": ticket_key,
            "tickets_processed": 0,
            "prs_created": 0
        }


def setup_environment():
    """Set up the environment and validate configuration."""
    logger.info("Setting up Jira to PR automation environment")
    
    # Validate configuration
    config_errors = validate_jira_to_pr_config()
    if config_errors:
        logger.error("Configuration validation failed:")
        for error in config_errors:
            logger.error(f"  - {error}")
        
        # Create sample environment file to help user
        create_sample_env_file()
        return False
    
    logger.info("Environment setup completed successfully")
    logger.info(f"Configuration: Jira Project = {settings.jira_project_key}, "
                f"Max Tickets = {settings.max_tickets_per_run}, "
                f"Dry Run = {settings.dry_run}")
    
    return True


async def main():
    """Main function for running the automation."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Jira to PR Automation")
    parser.add_argument("--max-tickets", type=int, default=5,
                        help="Maximum number of tickets to process")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run in dry-run mode (no actual changes)")
    parser.add_argument("--no-review", action="store_true",
                        help="Skip human review requirement")
    parser.add_argument("--ticket", type=str,
                        help="Process specific ticket only")
    parser.add_argument("--setup", action="store_true",
                        help="Set up environment and validate configuration")
    
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    if args.setup:
        success = setup_environment()
        return 0 if success else 1
    
    if args.ticket:
        result = await run_single_ticket(args.ticket, dry_run=args.dry_run)
    else:
        result = await run_jira_to_pr_automation(
            max_tickets=args.max_tickets,
            dry_run=args.dry_run,
            require_human_review=not args.no_review
        )
    
    if result["success"]:
        print(f"✅ Automation completed successfully!")
        print(f"📊 Results: {result.get('tickets_processed', 0)} tickets processed, "
              f"{result.get('prs_created', 0)} PRs created")
        return 0
    else:
        print(f"❌ Automation failed: {result.get('error', 'Unknown error')}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)


# Unit tests for the main module
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import sys
import os

# Add the src directory to the Python path for tests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))


class TestJiraToPRMain(unittest.TestCase):
    """Unit tests for the Jira to PR automation main module."""
    
    @patch('lib.jira_to_pr.main.validate_jira_to_pr_config')
    @patch('lib.jira_to_pr.main.create_initial_state')
    @patch('lib.jira_to_pr.main.build_jira_to_pr_graph')
    def test_run_automation_config_validation_failure(self, mock_build, mock_create_state, mock_validate):
        """Test that automation fails gracefully when config validation fails."""
        # Setup
        mock_validate.return_value = ["Missing JIRA_URL", "Missing GITHUB_TOKEN"]
        
        # Execute
        result = asyncio.run(run_jira_to_pr_automation())
        
        # Assert
        self.assertFalse(result["success"])
        self.assertEqual(result["errors"], ["Missing JIRA_URL", "Missing GITHUB_TOKEN"])
        self.assertEqual(result["tickets_processed"], 0)
        self.assertEqual(result["prs_created"], 0)
        mock_build.assert_not_called()
        mock_create_state.assert_not_called()
    
    @patch('lib.jira_to_pr.main.validate_jira_to_pr_config')
    @patch('lib.jira_to_pr.main.create_initial_state')
    @patch('lib.jira_to_pr.main.build_jira_to_pr_graph')
    def test_run_automation_success(self, mock_build, mock_create_state, mock_validate):
        """Test successful automation run."""
        # Setup
        mock_validate.return_value = []
        mock_state = {"initial": "state"}
        mock_create_state.return_value = mock_state
        
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "tickets_processed": 3,
            "prs_created": 2,
            "workflow_result": "success",
            "workflow_stage": "completed",
            "error": None
        }
        mock_build.return_value = mock_graph
        
        # Execute
        result = asyncio.run(run_jira_to_pr_automation(max_tickets=10))
        
        # Assert
        self.assertTrue(result["success"])
        self.assertEqual(result["tickets_processed"], 3)
        self.assertEqual(result["prs_created"], 2)
        self.assertIsNone(result["error"])
        mock_create_state.assert_called_once_with(
            max_tickets_per_run=10,
            require_human_review=True,
            dry_run=False
        )
    
    @patch('lib.jira_to_pr.main.validate_jira_to_pr_config')
    @patch('lib.jira_to_pr.main.create_initial_state')
    @patch('lib.jira_to_pr.main.build_jira_to_pr_graph')
    def test_run_automation_workflow_error(self, mock_build, mock_create_state, mock_validate):
        """Test automation handles workflow errors properly."""
        # Setup
        mock_validate.return_value = []
        mock_create_state.return_value = {"initial": "state"}
        
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "tickets_processed": 1,
            "prs_created": 0,
            "error": "Failed to connect to Jira"
        }
        mock_build.return_value = mock_graph
        
        # Execute
        result = asyncio.run(run_jira_to_pr_automation())
        
        # Assert
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Failed to connect to Jira")
    
    @patch('lib.jira_to_pr.main.validate_jira_to_pr_config')
    def test_run_single_ticket_invalid_key(self, mock_validate):
        """Test single ticket processing with invalid ticket key."""
        # Test empty string
        result = asyncio.run(run_single_ticket(""))
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Invalid ticket key provided")
        
        # Test None
        result = asyncio.run(run_single_ticket(None))
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Invalid ticket key provided")
    
    @patch('lib.jira_to_pr.main.validate_jira_to_pr_config')
    @patch('lib.jira_to_pr.main.create_initial_state')
    @patch('lib.jira_to_pr.main.build_jira_to_pr_graph')
    def test_run_single_ticket_success(self, mock_build, mock_create_state, mock_validate):
        """Test successful single ticket processing."""
        # Setup
        mock_validate.return_value = []
        mock_state = {"initial": "state", "specific_ticket": "JIRA-123"}
        mock_create_state.return_value = mock_state
        
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "tickets_processed": 1,
            "prs_created": 1,
            "error": None
        }
        mock_build.return_value = mock_graph
        
        # Execute
        result = asyncio.run(run_single_ticket("JIRA-123", dry_run=False))
        
        # Assert
        self.assertTrue(result["success"])
        self.assertEqual(result["ticket_key"], "JIRA-123")
        self.assertEqual(result["tickets_processed"], 1)
        self.assertEqual(result["prs_created"], 1)
        mock_create_state.assert_called_once_with(
            max_tickets_per_run=1,
            require_human_review=False,
            dry_run=False,
            specific_ticket="JIRA-123"
        )
    
    @patch('lib.jira_to_pr.main.validate_jira_to_pr_config')
    @patch('lib.jira_to_pr.main.create_sample_env_file')
    def test_setup_environment_with_errors(self, mock_create_sample, mock_validate):
        """Test environment setup with configuration errors."""
        # Setup
        mock_validate.return_value = ["Missing API key"]
        
        # Execute
        success = setup_environment()
        
        # Assert
        self.assertFalse(success)
        mock_create_sample.assert_called_once()


if __name__ == '__main__':
    unittest.main()