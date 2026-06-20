# Agent MCP

Use this recipe when an MCP-capable agent should call W-Agent through tools
instead of writing HTTP calls from scratch.

## Use

- MCP endpoint: `https://www.w-agent.cn/api/mcp`
- Auth: `Authorization: Bearer <api_key>`
- Call `tools/list` first.
- MCP task tools are for registered API Key users.

## Do Not Use

- Do not use MCP JSON-RPC for anonymous x402 payment. Anonymous x402 payment is
  handled by public HTTP APIs.
- Do not send wallet private keys to hosted MCP tools.

## Config

Use `mcp-config.example.json`:

```json
{
  "mcpServers": {
    "w-agent": {
      "url": "https://www.w-agent.cn/api/mcp",
      "headers": {
        "Authorization": "Bearer ${W_AGENT_API_KEY}"
      }
    }
  }
}
```

## Typical Tool Choices

- Same-person identity: use sequence parsing tools and compare same-type
  features.
- 2D/3D keypoints: use gait-pose tools on uploaded sequence frames.
- Object Search: use the object-search HTTP API or a future MCP wrapper when
  available.
