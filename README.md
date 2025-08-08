[![Try Free](https://img.shields.io/badge/Try%20Free-FalkorDB%20Cloud-FF8101?labelColor=FDE900&link=https://app.falkordb.cloud)](https://app.falkordb.cloud)
[![Dockerhub](https://img.shields.io/docker/pulls/falkordb/queryweaver?label=Docker)](https://hub.docker.com/r/falkordb/queryweaver/)
[![Discord](https://img.shields.io/discord/1146782921294884966?style=flat-square)](https://discord.com/invite/6M4QwDXn2w)
[![Workflow](https://github.com/FalkorDB/QueryWeaver/actions/workflows/pylint.yml/badge.svg?branch=main)](https://github.com/FalkorDB/QueryWeaver/actions/workflows/pylint.yml)

# QueryWeaver

QueryWeaver is an open-source Text2SQL tool that transforms natural language into SQL using graph-powered schema understanding. Ask your database questions in plain English—QueryWeaver handles the weaving.

## Setup

### Prerequisites

- Python 3.12+
- pipenv (for dependency management)
- FalkorDB instance

### Installation

1. Clone the repository
2. Install dependencies with Pipenv:
   ```bash
   pipenv sync
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
pipenv run flask --app api.index run
```

The application will be available at `http://localhost:5000`.

### Running with Docker

You can run QueryWeaver using Docker without installing Python dependencies locally:

```bash
docker run -p 5000:5000 -it falkordb/queryweaver
```

The application will be available at `http://localhost:5000`.

#### Configuring with Environment Variables

You can configure the application by passing environment variables using the `-e` flag. You can copy the variables from `.env.example` and set them as needed:

```bash
docker run -p 5000:5000 -it \
  -e FLASK_SECRET_KEY=your_super_secret_key_here \
  -e GOOGLE_CLIENT_ID=your_google_client_id \
  -e GOOGLE_CLIENT_SECRET=your_google_client_secret \
  -e GITHUB_CLIENT_ID=your_github_client_id \
  -e GITHUB_CLIENT_SECRET=your_github_client_secret \
  -e AZURE_API_KEY=your_azure_api_key \
  falkordb/queryweaver
```

##### Using a .env File

You can also pass a full environment file to Docker using the `--env-file` option. This is the easiest way to provide all required configuration at once:

```bash
docker run -p 5000:5000 --env-file .env falkordb/queryweaver
```

You can use the provided `.env.example` file as a template:

```bash
cp .env.example .env
# Edit .env with your values, then run:
docker run -p 5000:5000 --env-file .env falkordb/queryweaver
```

For a complete list of available configuration options, see the `.env.example` file in the repository.

## Testing

QueryWeaver includes a comprehensive test suite with both unit and End-to-End (E2E) tests.

### Quick Start

```bash
# Set up test environment
./setup_e2e_tests.sh

# Run all tests
make test

# Run only unit tests
make test-unit

# Run E2E tests (headless)
make test-e2e

# Run E2E tests with visible browser
make test-e2e-headed
```

### Test Types

- **Unit Tests**: Test individual components and functions
- **E2E Tests**: Test complete user workflows using Playwright
  - Basic functionality (page loading, UI structure)
  - Authentication flows (OAuth integration)
  - File upload and processing
  - Chat interface and query handling
  - API endpoint testing

See [tests/e2e/README.md](tests/e2e/README.md) for detailed E2E testing documentation.

### CI/CD

Tests run automatically in GitHub Actions:
- Unit tests run on every push/PR
- E2E tests run with FalkorDB service
- Test artifacts and screenshots saved on failure

## Introduction

<img width="1863" height="996" alt="image" src="https://github.com/user-attachments/assets/a0be7bbd-0c99-4399-a302-2b9f7b419dd2" />


## LICENSE

Licensed under the GNU Affero General Public License (AGPL). See [LICENSE](LICENSE.txt).

Copyrights FalkorDB Ltd. 2025

