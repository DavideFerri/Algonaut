# Algonaut Tests

This directory contains unit tests for the Algonaut project.

## Running Tests

To run all tests:
```bash
pytest
```

To run tests with coverage:
```bash
pytest --cov=src --cov-report=html
```

To run a specific test file:
```bash
pytest tests/test_nodes.py
```

To run tests in verbose mode:
```bash
pytest -v
```

## Test Structure

- `test_nodes.py` - Tests for the workflow node functions
- `test_code_generation_utils.py` - Tests for code generation utilities

## Key Test Areas

### Error Handling
- Retry logic for ExceptionGroup errors
- Graceful handling of "branch already exists" scenarios
- Proper error propagation and recovery

### PR Creation
- Dynamic test plan generation based on ticket type
- Proper PR body formatting
- URL extraction from API responses

### Code Generation
- Branch creation with proper error handling
- Repository analysis and file selection
- File modification with retry logic

## Writing New Tests

When adding new functionality, please ensure:
1. Add corresponding unit tests
2. Test both success and failure scenarios
3. Mock external dependencies (GitHub API, Jira API, etc.)
4. Verify retry logic where applicable