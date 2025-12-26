# AI Agents

This folder contains 2 scripts which leverage the [Claude Agents SDK](https://platform.claude.com/docs/en/agent-sdk/overview) to automatically populate the data of the [AI Deadlines web app](https://huggingface.co/spaces/huggingface/ai-deadlines).

## Usage

It can be run like so:

```bash
uv run --env-file keys.env -m agents.agent --conference_name neurips
```

The agent will automatically fetch relevant information from the web using the Exa MCP server to populate the data at `src/data/conferences`.

## Modal deployment

To automatically let the AI agents populate deadlines data, we leverage [Modal](https://modal.com/)'s serverless infrastructure. To run an agent on Modal, use the following command:

```bash
uv run --env-file keys.env -m agents.modal_agent --conference_name neurips
```