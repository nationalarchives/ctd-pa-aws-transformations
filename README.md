# CTD AWS Transformations

This repository contains the code for the CTD (Catalogue and Taxonomy Development) AWS-based transformation pipeline. Its purpose is to fetch archival data, apply a series of configurable transformations, and prepare it for ingest.

## Core Features

- **Plugin-Based Architecture**: Transformations are implemented as individual "transformer" plugins that can be chained together in any order. See the [Transformer Architecture documentation](docs/TRANSFORMER_ARCHITECTURE.md) for details.
- **Configurable Pipeline**: The entire transformation process is defined in a YAML configuration file, allowing for flexible and environment-specific setups.
- **Local Development Environment**: A complete, high-fidelity local testing environment is provided using Docker and LocalStack, simulating the production AWS services.
- **Business Logic Preservation**: Includes specialized transformers for complex, domain-specific rules like The National Archives' "Y-naming" conventions.

## Local Development

To get started with local development, please see the **[Local Development Guide](LOCAL_DEVELOPMENT.md)**. This guide provides a complete walkthrough for setting up the Docker/LocalStack environment and running the pipeline on your machine.

## Key Documentation

- **[Local Development Guide](LOCAL_DEVELOPMENT.md)**: Your starting point for running the project locally.
- **[Transformer Architecture](docs/TRANSFORMER_ARCHITECTURE.md)**: An in-depth explanation of the generic and specialized transformer plugins.
- **[Transfer Register and Tarring](docs/TRANSFER_REGISTER_AND_TARRING.md)**: Details on the implementation of the transfer register (for preventing duplicate processing) and the final tarballing process.
- **[Environment Variables](ENV_VARS.md)**: A reference for all environment variables used to configure the pipeline.

## Pre-commit Hooks

This repository uses [pre-commit](https://pre-commit.com/) to enforce code quality and standards. Please ensure you have it installed and initialized:

```bash
pip install pre-commit
pre-commit install
```

