# Self-Hosting

Agent OS can be self-hosted locally using Docker Compose, providing both the runtime API and the graphical console.

## Quickstart

1. Ensure Docker is installed and running.
2. Clone the repository and navigate into it.
3. Start the stack:
   ```bash
   docker compose up --build -d
   ```
4. Access the console at [http://127.0.0.1:4100](http://127.0.0.1:4100)

## Architecture

The compose stack consists of two services:
- **backend**: The Agent OS runtime API (`agent-os serve`). It mounts a persistent Docker volume (`agentos_data`) to `/data` for the system databases (checkpoints, runs, schedules). It also mounts your current directory (`.`) to `/workspace` so the agents can access your files.
- **console**: The frontend dashboard. It connects to the backend API via your browser at `http://127.0.0.1:4680`.

## Configuration Matrix

You can configure the stack using an `.env` file in the same directory as `docker-compose.yml`.

| Variable | Default | Description |
|---|---|---|
| `AGENT_OS_LLM_PROVIDER` | (none) | Primary LLM provider (e.g. `anthropic`, `openai`) |
| `ANTHROPIC_API_KEY` | (none) | Required if using Claude models |
| `OPENAI_API_KEY` | (none) | Required if using OpenAI models |
| `AGENT_OS_CORS_ORIGINS` | (none) | Add `http://127.0.0.1:4100` if modifying the API configuration |

## Persistent Data & Backups

The runtime stores stateful data in SQLite databases located in the `/data` directory inside the container. This directory is mapped to the `agentos_data` Docker volume.

To back up your checkpoints and schedules:
1. Stop the backend to prevent writes.
2. Create a backup of the Docker volume (e.g., using `docker run --rm -v agentos_data:/data -v $(pwd):/backup alpine tar czvf /backup/agentos-backup.tar.gz /data`).

## Security

The compose configuration binds the services to `127.0.0.1`. This is intentional and prevents exposing your unauthenticated agent runtime to the local network or internet. Do not change the port bindings to `0.0.0.0` without placing a reverse proxy with authentication in front of the stack.
