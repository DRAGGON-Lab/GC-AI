# GC-AI 

![logo-GC-AI](docs/logo/GC-AI-FullLogo.svg)

**GC-AI** is a web application designed for symbol detection and SBOL3 file generation.

## 📖 Table of Contents

-  [Features](#features)
-  [Supported Glyphs](#supported-glyphs)
-  [Requirements](#requirements)
-  [Installation](#installation)
-  [Usage](#usage)
-  [API Endpoints](#api-endpoints)
-  [Project Structure](#project-structure)
-  [Documentation](#documentation)
-  [License](#license)

---

## 🖥️ Features

- **Symbol Detection**: Leverages a trained ML model to identify and classify symbols in input images.
- **SBOL3 File Generation**: Creates SBOL3 files based on user input and system rules.
- **File Conversion**: Converts SBOL3 files to GenBank and/or FASTA formats.
- **Health Check**: Provides an endpoint to verify the application's health.
- **Database Integration**: Reads registry part metadata and sequences from MySQL.

## Supported Glyphs

GC-AI detects 14 SBOL Visual glyph classes: promoter, ribosome entry site (RBS),
CDS (`cds`), terminator, aptamer, CDS (arrow) (`cds-arrow`), engineered region,
inert DNA spacer, non-coding RNA (`ncrna`), operator, origin of replication,
origin of transfer, poly(A) site, and primer binding site.

<p>
  <img src="frontend/src/assets/symbols/promoter.svg#gh-light-mode-only" alt="Promoter" title="Promoter" width="64" height="64">
  <img src="frontend/src/assets/symbols/dark/promoter.svg#gh-dark-mode-only" alt="Promoter" title="Promoter" width="64" height="64">
  <img src="frontend/src/assets/symbols/ribosome-entry-site.svg#gh-light-mode-only" alt="Ribosome entry site (RBS)" title="Ribosome entry site (RBS)" width="64" height="64">
  <img src="frontend/src/assets/symbols/dark/ribosome-entry-site.svg#gh-dark-mode-only" alt="Ribosome entry site (RBS)" title="Ribosome entry site (RBS)" width="64" height="64">
  <img src="frontend/src/assets/symbols/cds.svg#gh-light-mode-only" alt="CDS" title="CDS" width="64" height="64">
  <img src="frontend/src/assets/symbols/dark/cds.svg#gh-dark-mode-only" alt="CDS" title="CDS" width="64" height="64">
  <img src="frontend/src/assets/symbols/terminator.svg#gh-light-mode-only" alt="Terminator" title="Terminator" width="64" height="64">
  <img src="frontend/src/assets/symbols/dark/terminator.svg#gh-dark-mode-only" alt="Terminator" title="Terminator" width="64" height="64">
  <img src="frontend/src/assets/symbols/aptamer.svg#gh-light-mode-only" alt="Aptamer" title="Aptamer" width="64" height="64">
  <img src="frontend/src/assets/symbols/dark/aptamer.svg#gh-dark-mode-only" alt="Aptamer" title="Aptamer" width="64" height="64">
  <img src="frontend/src/assets/symbols/cds-arrow.svg#gh-light-mode-only" alt="CDS (arrow)" title="CDS (arrow)" width="64" height="64">
  <img src="frontend/src/assets/symbols/dark/cds-arrow.svg#gh-dark-mode-only" alt="CDS (arrow)" title="CDS (arrow)" width="64" height="64">
  <img src="frontend/src/assets/symbols/engineered-region.svg#gh-light-mode-only" alt="Engineered region" title="Engineered region" width="64" height="64">
  <img src="frontend/src/assets/symbols/dark/engineered-region.svg#gh-dark-mode-only" alt="Engineered region" title="Engineered region" width="64" height="64">
  <img src="frontend/src/assets/symbols/inert-dna-spacer.svg#gh-light-mode-only" alt="Inert DNA spacer" title="Inert DNA spacer" width="64" height="64">
  <img src="frontend/src/assets/symbols/dark/inert-dna-spacer.svg#gh-dark-mode-only" alt="Inert DNA spacer" title="Inert DNA spacer" width="64" height="64">
  <img src="frontend/src/assets/symbols/ncrna.svg#gh-light-mode-only" alt="Non-coding RNA" title="Non-coding RNA" width="64" height="64">
  <img src="frontend/src/assets/symbols/dark/ncrna.svg#gh-dark-mode-only" alt="Non-coding RNA" title="Non-coding RNA" width="64" height="64">
  <img src="frontend/src/assets/symbols/operator.svg#gh-light-mode-only" alt="Operator" title="Operator" width="64" height="64">
  <img src="frontend/src/assets/symbols/dark/operator.svg#gh-dark-mode-only" alt="Operator" title="Operator" width="64" height="64">
  <img src="frontend/src/assets/symbols/origin-of-replication.svg#gh-light-mode-only" alt="Origin of replication" title="Origin of replication" width="64" height="64">
  <img src="frontend/src/assets/symbols/dark/origin-of-replication.svg#gh-dark-mode-only" alt="Origin of replication" title="Origin of replication" width="64" height="64">
  <img src="frontend/src/assets/symbols/origin-of-transfer.svg#gh-light-mode-only" alt="Origin of transfer" title="Origin of transfer" width="64" height="64">
  <img src="frontend/src/assets/symbols/dark/origin-of-transfer.svg#gh-dark-mode-only" alt="Origin of transfer" title="Origin of transfer" width="64" height="64">
  <img src="frontend/src/assets/symbols/polyA.svg#gh-light-mode-only" alt="Poly(A) site" title="Poly(A) site" width="64" height="64">
  <img src="frontend/src/assets/symbols/dark/polyA.svg#gh-dark-mode-only" alt="Poly(A) site" title="Poly(A) site" width="64" height="64">
  <img src="frontend/src/assets/symbols/primer-binding-site.svg#gh-light-mode-only" alt="Primer binding site" title="Primer binding site" width="64" height="64">
  <img src="frontend/src/assets/symbols/dark/primer-binding-site.svg#gh-dark-mode-only" alt="Primer binding site" title="Primer binding site" width="64" height="64">
</p>

Glyphs are shown in the order listed above. See the
[detector configuration](backend/app/data_configs/glyphs.yaml) for the exact class names.

---
## 🧩 System Architecture

The following diagram illustrates the complete workflow of GC-AI, from the initial image input and AI detection to the generation of standardized SBOL3 files and optional conversions:

<p align="center">
  <img src="docs/GC-AI Architecture Flow.png" alt="GC-AI Architecture Flow" width="100%">
</p>

---

## ⚙️ Installation 

The installation and setup of this application for local use are provided in the following repository:

- [GC-AI Environment](https://github.com/DRAGGON-Lab/GC-AI-environment)

Please refer to that repository for detailed instructions on setting up and running the application.

---

## 🔗 API Endpoints

The full contract is in [`docs/openapi.yaml`](docs/openapi.yaml), with a guide
and a worked walkthrough in [`docs/api_documentation.md`](docs/api_documentation.md).

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/inference/` | Detects SBOL Visual glyphs in an image and returns their classes and bounding boxes. |
| `GET` | `/component/names` | Lists registry part names for a role. |
| `GET` | `/component/interactions` | Lists the participation roles an interaction type expects. |
| `GET` | `/component/details` | Returns one registry part with its description and sequence. |
| `POST` | `/file/create` | Generates SBOL3 documents for a design. |
| `POST` | `/file/convert` | Converts a generated document to GenBank and/or FASTA. |
| `GET` | `/healthcheck/` | Readiness: 200 when detector and database are usable; otherwise 503. |

To check whether a running instance is usable, call
`GET /component/names?role=Promoter`: it succeeds only when the application is
serving, the detection model has loaded and the parts database answers.

---

## 📁 Project Structure

 **`app/`**: Contains the main application code, including subdirectories:
  -  **`data_configs/`**: Configuration files for data management.
  -  **`files_converted/`**: Stores converted files.
  -  **`files_generated/`**: Stores generated files like SBOL3 outputs.
  -  **`models/`**: Machine learning models and related files.
  -  **`routes/`**: API route definitions.
  -  **`utils/`**: Utility scripts for backend operations.
-  **`run.py`**: Entry point for the backend.
-  **`requirements.txt`**: Lists all dependencies.
-  **`gc-ai-backend.log`**: Log file for backend operations.

---

## 📚 Documentation

For a detailed API reference, user guide, and additional resources, visit the `docs` folder in this repository. This folder includes:

-  **API Documentation:** Detailed explanations of each endpoint, including parameters, request examples, and responses.
-  **User Guide:** Step-by-step instructions on how to use the application.
-  **Examples Folder:** Contains example files and use cases to better understand the functionality.
-  **[`examples/`](examples/):** Runnable scripts that take a diagram to SBOL3 and put the result in a registry.
-  **[`client/`](client/):** A Python client and command line tool for the API, and an MCP server over it.

[**Video Tutorial**](https://drive.google.com/file/d/1RuKLGXI1q8kWlBau8AR73cHA5y5vItGI/view?usp=sharing)

## 📝 License

This project is licensed under the MIT License. See the `LICENSE` file for details.

Hosted TLS/authentication, resource limits, and migration instructions: [deployment](docs/deployment.md). `/livez` provides dependency-independent liveness.

CPU research release work and remaining gates: [qualification](docs/release/qualification.md)
and [epic #8 evidence](docs/release/epic-8.md).
