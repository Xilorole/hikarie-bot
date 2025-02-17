# Hikarie BOT

<div align="center">

[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

[![Ruff](https://github.com/Xilorole/hikarie-bot/actions/workflows/ruff.yml/badge.svg)](https://github.com/Xilorole/hikarie-bot/actions/workflows/ruff.yml)
[![Test](https://github.com/Xilorole/hikarie-bot/actions/workflows/test.yml/badge.svg)](https://github.com/Xilorole/hikarie-bot/actions/workflows/test.yml)
[![Docker](https://github.com/Xilorole/hikarie-bot/actions/workflows/docker.yml/badge.svg)](https://github.com/Xilorole/hikarie-bot/actions/workflows/docker.yml)

</div>

## Getting Started
## Features
## Project Structure

The repository is organized as follows:
### Setting Up the Development Environment

To set up the development environment, use the following command:

```bash
uv sync --dev
```

This will create a virtual environment and install all necessary dependencies for the project.

```
├── .github             # GitHub configuration and workflows
│   ├── workflows       # GitHub Actions workflows
├── .devcontainer       # VSCode Dev Container configuration
├── hikarie_bot         # Source code for the application
│   ├── __init__.py     # Package initialization
│   ├── models.py       # Database models
│   ├── slack_helper.py # Slack integration utilities
│   ├── modals.py       # Slack modal utilities
│   ├── settings.py     # Application settings
│   └── ...             # Other modules
├── tests               # Test cases for the application
│   ├── test_app.py     # Tests for the main application
│   ├── test_badges.py  # Tests for badge-related functionality
│   └── ...             # Other test modules
├── scripts             # Utility scripts
├── Dockerfile          # Docker configuration
├── pyproject.toml      # Project configuration
├── README.md           # Project documentation
└── LICENSE             # License file
```

## Roadmap

- [x] Set up Dev Container for VSCode
- [x] Integrate Ruff for linting and formatting
- [x] Add GitHub Actions for CI/CD
- [ ] Add more test cases
- [ ] Improve documentation

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [uv](https://github.com/astral-sh/uv) for development utilities
- [Ruff](https://github.com/astral-sh/ruff) for linting and formatting
- [VSCode Dev Containers](https://code.visualstudio.com/docs/remote/containers) for seamless development environments

- **Dev Container Support**: Seamless development environment setup using VSCode's Dev Container feature.
- **Code Quality Tools**: Integrated with `uv` and `Ruff` for formatting and linting.
- **Automated Workflows**: Pre-configured GitHub Actions for Docker builds, testing, and linting.

## Prerequisites

Before you begin, ensure you have the following installed:

- [Docker](https://www.docker.com/)
- [VSCode](https://code.visualstudio.com/) with the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)

## Usage

### Running Locally

1. **Start the Development Environment**:
   ```bash
   docker-compose up --build
   ```

2. **Access the Application**:
   Open your browser and navigate to [http://localhost:53138](http://localhost:53138) or [http://localhost:58456](http://localhost:58456).

### Running Tests

To run tests locally, use the following command:
```bash
docker-compose run app pytest
```

## Troubleshooting

### Common Issues

- **Ruff Formatting Not Working**:
  If the Ruff format does not work, try reloading the VS Code window by following these steps:
  ```plaintext
  1. Type `⌘+⇧+P` to open the command palette
  2. Type `Developer: Reload Window` in the command palette to reload the window
  ```

- **Docker Build Fails**:
  Ensure Docker is running and you have sufficient permissions to execute Docker commands.

To get started with the Hikarie BOT, follow these steps:

1. Clone the repository:
   ```bash
   git clone https://github.com/Xilorole/hikarie-bot.git
   ```

2. Navigate to the project directory:
   ```bash
   cd hikarie-bot
   ```

3. Build and run the development environment using Docker:
   ```bash
   docker-compose up --build
   ```

4. Access the application at [http://localhost:53138](http://localhost:53138) or [http://localhost:58456](http://localhost:58456).

## Contributing

Contributions are welcome! Please follow these steps to contribute:

1. Fork the repository.
2. Create a new branch for your feature or bugfix.
3. Commit your changes with clear and descriptive messages.
4. Push your branch and create a pull request.
## Overview
This repository contains configurations to set up a Python development environment using VSCode's Dev Container feature.
The environment includes uv, and Ruff.

If the Ruff format does not work, try reloading the VS Code window.
Specifically, you can solve this problem by following the steps below.

```plaintext
1. Type `⌘+⇧+P` to open the command palette
2. Type `Developer: Reload Window` in the command palette to reload the window
```

## GitHub Actions
- [`docker.yml`](.github/workflows/docker.yml)
  - Workflow to check if you can build with Docker
- [`test.yml`](.github/workflows/test.yml)
  - Workflow to check if all the described tests can be passed with pytest
- [`ruff.yml`](.github/workflows/ruff.yml)
  - Workflow to check if you can go through Formatter and Linter with Ruff

## Running the Bot with Docker

To run the Hikarie Bot using Docker, follow these steps:

1. Build the Docker image:

   ```bash
   docker build -t hikarie-bot .
   ```

2. Run the Docker container:

   ```bash
   docker run -d --name hikarie-bot-container hikarie-bot
   ```

3. Verify that the bot is running:

   ```bash
   docker logs hikarie-bot-container
   ```

Replace `hikarie-bot` and `hikarie-bot-container` with your preferred image and container names if needed.
## Running the Bot with Docker Compose

To run the Hikarie Bot using Docker Compose, follow these steps:

1. Ensure you have Docker and Docker Compose installed on your system.

2. Start the bot using Docker Compose:

   ```bash
   docker-compose up -d
   ```

3. Verify that the bot is running:

   ```bash
   docker logs hikarie-bot-container
   ```

This will build and run the bot in a container named `hikarie-bot-container`.
