# GC-AI 

![logo-GC-AI](docs/logo/GC-AI-FullLogo.svg)

**GC-AI** is a web application designed for symbol detection and SBOL3 file generation.

## 📖 Table of Contents

-  [Features](#features)
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
- **Database Integration**: Interacts with a MySQL database to retrieve and store relevant data.

---
## 🧩 System Architecture

The following diagram illustrates the complete workflow of GC-AI, from the initial image input and AI detection to the generation of standardized SBOL3 files and optional conversions:

<p align="center">
  <img src="docs/GC-AI Architecture Flow.png" alt="GC-AI Architecture Flow" width="100%">
</p>

---

## ⚙️ Installation 

The installation and setup of this application for local use are provided in the following repository:

- [GC-AI Environment](https://github.com/cvtalrc/GC-AI-environment)

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
| `GET` | `/healthcheck/` | Reports service status. Always answers `500` in the current build. |

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

[**Video Tutorial**](https://drive.google.com/file/d/1RuKLGXI1q8kWlBau8AR73cHA5y5vItGI/view?usp=sharing)

## 📝 License

This project is licensed under the MIT License. See the `LICENSE` file for details.
