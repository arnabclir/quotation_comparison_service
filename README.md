# SKU Quotation Comparator using Gemini AI

## Project Description

This project provides a Streamlit web application that allows users to upload PDF quotation files from different suppliers and compare the pricing of Stock Keeping Units (SKUs) listed within them. It leverages the Google Gemini AI API to extract structured data from the PDF documents and then processes this data to generate a comparative table, highlighting the best deal for each SKU across suppliers.

The application has been rearchitected into a modular structure for improved maintainability, testability, and readability.

## Setup and Installation

To set up and run this project locally, follow these steps:

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd quotation_comparison_service
    ```
    (Replace `<repository_url>` with the actual repository URL)

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv .venv
    ```

3.  **Activate the virtual environment:**
    *   On Windows:
        ```bash
        .venv\Scripts\activate
        ```
    *   On macOS and Linux:
        ```bash
        source .venv/bin/activate
        ```

4.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

5.  **Configure Gemini API Key:**
    *   Obtain a Gemini API key from the Google AI Studio ([https://aistudio.google.com/](https://aistudio.google.com/)).
    *   Set the `GEMINI_API_KEY` as an environment variable.
    *   Alternatively, for Streamlit Cloud deployment, use Streamlit Secrets. Create a `.streamlit` directory in the project root and add a `secrets.toml` file with the following content:
        ```toml
        GEMINI_API_KEY="YOUR_API_KEY"
        ```
        Replace `"YOUR_API_KEY"` with your actual Gemini API key.

## How to Run the Application

1.  Ensure your virtual environment is activated and dependencies are installed.
2.  Make sure your `GEMINI_API_KEY` is configured (either as an environment variable or in `.streamlit/secrets.toml`).
3.  Run the Streamlit application from the project root directory:
    ```bash
    streamlit run app.py
    ```
4.  The application will open in your default web browser.

## Project Structure Overview

The project follows a modular architecture to separate concerns:

*   `app.py`: The main Streamlit application entry point and orchestrator. Handles the overall application flow and session state.
*   `models.py`: Defines data structures used throughout the application (e.g., `RawSkuItem`, `ProcessedSkuItem`).
*   `gemini_service.py`: Encapsulates the logic for interacting with the Google Gemini API, including file uploads and data extraction.
*   `sku_processing.py`: Contains the core data processing and comparison logic, such as parsing quantities, calculating metrics, and generating the comparison table data.
*   `ui_components.py`: Houses functions responsible for rendering specific parts of the Streamlit user interface.
*   `Dockerfile`: Defines the steps to build a Docker image for the application.
*   `requirements.txt`: Lists the project's Python dependencies.
*   `rearchitecture_plan.md`: Detailed document explaining the rearchitecture process and module interactions.

## Key Features

*   Upload multiple PDF quotation files.
*   Extract structured SKU data from PDFs using Google Gemini AI.
*   Compare SKU pricing across different suppliers.
*   Highlight the best deal for each SKU in the comparison table.
*   Download the comparison table as a CSV file.

## Architecture Details

For a more in-depth understanding of the project's architecture, module responsibilities, and data flow, please refer to the [Rearchitecture Plan](rearchitecture_plan.md).