"""Main Jira to PR automation workflow graph."""

from lib.jira_to_pr.builder import build_jira_to_pr_graph

# Build and export the graph
graph = build_jira_to_pr_graph()