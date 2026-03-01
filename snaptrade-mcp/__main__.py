"""Entry point for the SnapTrade MCP server.

Run with: python snaptrade-mcp/server.py
     or: cd snaptrade-mcp && python server.py
"""
import sys
from pathlib import Path

# Ensure the package directory is importable
sys.path.insert(0, str(Path(__file__).parent))

from server import mcp

mcp.run()
