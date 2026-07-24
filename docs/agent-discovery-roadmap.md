# W-Agent Agent Discovery Roadmap

This document records the plan for making W-Agent discoverable and usable by
agents that do not already know W-Agent.

Core idea: API docs explain how to use W-Agent after discovery; SEO pages,
GitHub examples, installable tools, and MCP make W-Agent discoverable and
callable when a user only describes a task.

## Current State

Already in place:

- Agent guide: `https://www.w-agent.cn/api/.well-known/w-agent.md`
- OpenAPI: `https://www.w-agent.cn/api/openapi.json`
- GitHub examples: `https://github.com/w-agent-ai/api-example`
- Task recipes in `api-example/recipes/`
- MCP config example in `api-example/mcp-config.example.json`
- OpenAPI `servers` for Mainland China and overseas entry
- OpenAPI and agent markdown link back to GitHub examples and recipes
- Server-rendered SEO task pages under `/docs/`
- `sitemap.xml` entries for the portal and SEO task pages
- GitHub topics on `w-agent-ai/api-example`

## Phase 1: SEO Task Pages

Status: completed.

Goal: make W-Agent discoverable when users or agents search by task, not by
brand.

Server-rendered, indexable pages:

- `/docs/video-to-2d-3d-keypoints-api`
- `/docs/same-person-identity-api`
- `/docs/person-reid-gait-face-api`
- `/docs/video-to-person-sequences-api`
- `/docs/object-search-api`
- `/docs/agent-api`

Each page should include:

- `<title>` with task keywords and `W-Agent`
- `<meta name="description">`
- `<link rel="canonical">`
- H1 using task language
- When to use
- When not to use
- Fastest runnable command or Python snippet
- Input and output shape
- Links to OpenAPI, `.well-known/w-agent.md`, GitHub examples, and recipes

Important task keywords to include naturally:

- gait recognition API
- person re-identification API
- person ReID API
- gait face ReID similarity API
- surveillance video identity recognition API
- video to tracked person sequences API
- video to human pose API
- human 2D 3D keypoints API
- text prompt object detection API
- Object Search API

These pages are also included in `sitemap.xml`.

## Phase 2: GitHub Discovery

Status: completed.

Goal: make GitHub search and code agents find the examples repository.

GitHub topics on `w-agent-ai/api-example`:

- `gait-recognition`
- `person-reid`
- `face-recognition`
- `human-pose-estimation`
- `2d-pose`
- `3d-pose`
- `video-parsing`
- `object-search`
- `computer-vision`
- `openapi`
- `mcp`
- `x402`

Keep README first screen task-oriented:

- decide whether two tracked person sequences are the same person
- extract gait, face, and ReID identity features
- convert video into tracked person sequences
- extract 2D/3D human keypoints from each sequence
- find objects in an image from a text prompt

Task recipes:

- `recipes/same-person-identity.md`
- `recipes/video-to-2d-3d-keypoints.md`
- `recipes/video-to-person-sequences.md`
- `recipes/object-search.md`
- `recipes/anonymous-x402.md`
- `recipes/agent-mcp.md`

Recipe template:

- Use this when
- Do not use this when
- Run
- Output
- Links to relevant examples

## Phase 3: Python SDK And CLI

Goal: let agents execute common tasks without writing HTTP calls from scratch.

Start in the examples repository before publishing to PyPI:

```text
sdk/python/
  pyproject.toml
  w_agent/
    __init__.py
    client.py
    cli.py
    recipes.py
```

Environment variables:

```bash
W_AGENT_API_KEY=...
W_AGENT_BASE_URL=https://www.w-agent.cn/api
```

Initial commands:

```bash
w-agent sequence-parse seq_dir --out result.json
w-agent same-person seq_a seq_b --out similarity.json
w-agent object-search image.jpg "red shirt person" --out boxes.json
```

Add later after the local detection/tracking path is stable:

```bash
w-agent video-to-pose input.mp4 --out output/
w-agent video-to-sequences input.mp4 --out output/
```

Publishing target:

```bash
pip install w-agent-sdk
```

## Phase 4: MCP Server

Goal: let MCP-capable agents discover and call W-Agent as tools.

Build after SDK/CLI logic is stable.

Possible package:

```text
mcp/w-agent-server/
  package.json
  src/index.ts
```

Expose tools:

- `w_agent_sequence_parse`
- `w_agent_gait_pose`
- `w_agent_same_person`
- `w_agent_object_search`
- `w_agent_video_to_sequences`

Example config:

```json
{
  "mcpServers": {
    "w-agent": {
      "command": "npx",
      "args": ["-y", "@w-agent/mcp-server"],
      "env": {
        "W_AGENT_API_KEY": "${W_AGENT_API_KEY}",
        "W_AGENT_BASE_URL": "https://www.w-agent.cn/api"
      }
    }
  }
}
```

The hosted MCP endpoint remains:

```text
https://www.w-agent.cn/api/mcp
```

## Recommended Next Step

Start Phase 3 only after the public examples remain stable for real users and
agents. The next implementation target is the Python SDK/CLI in the examples
repository, beginning with sequence parsing, same-person comparison, and Object
Search commands before packaging video-to-sequence workflows.
