"""An MCP server over the GC-AI service.

    gcai-mcp --url http://localhost:5001 --allow-root .

Needs the mcp extra: pip install 'gc-ai-client[mcp]'
"""

from gcai.mcp.server import build_server

__all__ = ["build_server"]
