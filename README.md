[![Try Free](https://img.shields.io/badge/Try%20Free-FalkorDB%20Cloud-FF8101?labelColor=FDE900&link=https://app.falkordb.cloud)](https://app.falkordb.cloud)
[![Dockerhub](https://img.shields.io/docker/pulls/falkordb/falkordb?label=Docker)](https://hub.docker.com/r/falkordb/falkordb/)
[![Discord](https://img.shields.io/discord/1146782921294884966?style=flat-square)](https://discord.com/invite/6M4QwDXn2w)
[![Workflow](https://github.com/FalkorDB/text2sql/actions/workflows/pylint.yml/badge.svg?branch=main)](https://github.com/FalkorDB/text2sql/actions/workflows/pylint.yml)

# Text2SQL

Text2SQL is a web application that allows users to interact with databases using natural language queries, powered by AI and graph database technology.

## Setup

### Prerequisites

- Python 3.8+
- Poetry (for dependency management)
- FalkorDB instance (or Redis with FalkorDB module)

### Installation

1. Clone the repository
2. Install dependencies with Poetry:
   ```bash
   poetry install
   ```

3. Set up environment variables by copying `.env.example` to `.env` and filling in your values:
   ```bash
   cp .env.example .env
   ```

### OAuth Configuration

This application supports authentication via Google and GitHub OAuth. You'll need to set up OAuth applications for both providers:

#### Google OAuth Setup

1. Go to [Google Cloud Console](https://console.developers.google.com/)
2. Create a new project or select an existing one
3. Enable the Google+ API
4. Go to "Credentials" and create an OAuth 2.0 Client ID
5. Add your domain to authorized origins (e.g., `http://localhost:5000`)
6. Add the callback URL: `http://localhost:5000/login/google/authorized`
7. Copy the Client ID and Client Secret to your `.env` file

#### GitHub OAuth Setup

1. Go to GitHub Settings → Developer settings → OAuth Apps
2. Click "New OAuth App"
3. Fill in the application details:
   - Application name: Your app name
   - Homepage URL: `http://localhost:5000`
   - Authorization callback URL: `http://localhost:5000/login/github/authorized`
4. Copy the Client ID and Client Secret to your `.env` file

### Running the Application

```bash
poetry run flask --app api.index run
```

The application will be available at `http://localhost:5000`.

## Introduction

![image](https://github.com/user-attachments/assets/8b1743a8-1d24-4cb7-89a8-a95f626e68d9)


## LICENSE

Copyrights FalkorDB Ltd. 2025

