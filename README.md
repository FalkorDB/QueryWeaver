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
   
   **Required Configuration:**
   - `FLASK_SECRET_KEY`: A secure secret key for Flask sessions
   - `GOOGLE_CLIENT_ID` & `GOOGLE_CLIENT_SECRET`: For Google OAuth authentication
   - `GITHUB_CLIENT_ID` & `GITHUB_CLIENT_SECRET`: For GitHub OAuth authentication
   - `FALKORDB_HOST` & `FALKORDB_PORT`: FalkorDB connection settings
   
   **Optional Configuration:**
   - Email settings (for organization invitations): `MAIL_*` variables
   - AI/LLM settings: `AZURE_API_KEY`, `OPENAI_API_KEY`, etc.
   - Analytics: `GOOGLE_TAG_MANAGER_ID`

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

### Email Configuration (Optional)

QueryWeaver supports sending invitation emails when administrators add new users to their organization. This feature is optional but recommended for better user experience.

#### Email Service Setup

QueryWeaver uses Flask-Mail for email functionality. You can configure it with any SMTP provider:

##### SMTP Configuration Examples

**Gmail:**

1. Enable 2-factor authentication on your Gmail account
2. Generate an App Password:
   - Go to Google Account settings → Security → App passwords
   - Generate a new app password for "Mail"
3. Add the following to your `.env` file:

```bash
# Email Configuration
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USE_SSL=False
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password-here
MAIL_DEFAULT_SENDER=your-email@gmail.com
APP_URL=https://your-domain.com
```

**SMTP Providers:**

For other email providers, update the SMTP settings accordingly:

```bash
# Example for Outlook/Hotmail
MAIL_SERVER=smtp.live.com
MAIL_PORT=587

# Example for Yahoo
MAIL_SERVER=smtp.mail.yahoo.com
MAIL_PORT=587

# Example for custom SMTP
MAIL_SERVER=mail.your-domain.com
MAIL_PORT=465
MAIL_USE_SSL=True
MAIL_USE_TLS=False
```

#### Email Features

When email is properly configured:

- **Invitation Emails**: Automatically sent when an admin adds a new user to their organization
- **Approval Notifications**: Sent when a pending user is approved by an admin
- **Professional Templates**: HTML and plain text email templates with organization branding
- **Graceful Fallback**: Application continues to work normally if email is not configured

#### Email Security Notes

- Always use App Passwords instead of your main account password
- Keep your email credentials secure and never commit them to version control
- Consider using environment-specific email settings for development vs. production
- The `APP_URL` should point to your actual application domain for production

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

## Organization Management

QueryWeaver includes comprehensive organization management features that allow teams to collaborate effectively:

### Features

- **Domain-based Organizations**: Users are automatically grouped by their email domain
- **Admin Controls**: Organization admins can manage users and permissions
- **User Invitations**: Admins can invite new users with automatic email notifications
- **Role Management**: Support for different user roles within organizations
- **Approval Workflow**: Pending users can be approved by organization admins

### Email Notifications

When email is configured, QueryWeaver automatically sends:

- **Invitation emails** when admins add new users to their organization
- **Approval notifications** when pending users are approved
- **Professional HTML templates** with organization branding and clear instructions

### Getting Started with Organizations

1. **Create an Organization**: The first user from a domain becomes the admin
2. **Invite Team Members**: Admins can add users by email address
3. **Manage Permissions**: Set roles and approve pending users
4. **Collaborate**: All organization members can access shared databases and queries

For email functionality, make sure to configure the email settings in your `.env` file as described in the Email Configuration section above.

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

