# AI Agents

This folder contains 2 scripts which leverage the [Claude Agents SDK](https://platform.claude.com/docs/en/agent-sdk/overview) to automatically populate the data of the [AI Deadlines web app](https://huggingface.co/spaces/huggingface/ai-deadlines).

## Usage

First create a `keys.env` file at the root of the repository which contains the following environment variables:

```bash
ANTHROPIC_API_KEY=
GITHUB_PAT=
EXA_API_KEY=
```

In case you want to leverage MiniMax 2.1 instead of Claude, get your API key from https://platform.minimax.io/ and add the following:

```bash
ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic
```

Next, the agent can be run like so on a conference of choice:

```bash
uv run --env-file keys.env -m agents.agent --conference_name neurips
```

The agent will automatically fetch relevant information from the web using the [Exa MCP server](https://docs.exa.ai/reference/exa-mcp) to populate the data at `src/data/conferences`.

## Modal deployment

To automatically let the AI agents populate deadlines data, we leverage [Modal](https://modal.com/)'s serverless infrastructure. To run an agent on Modal, use the following command:

```bash
uv run --env-file keys.env -m agents.modal_agent --conference_name neurips
```