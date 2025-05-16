# Plan to Build and Run the Streamlit Quotation Comparison App

This document outlines the steps to build and run the Streamlit application for comparing SKU quotations using Gemini AI, including containerization with Docker.

**Steps:**

1.  **Create the Application File:** A new Python file, likely named [`app.py`](app.py) will be created in the workspace directory (`d:/code/python/quotation_comparison_service`).
2.  **Write the Code:** The provided Python code will be written into the [`app.py`](app.py) file.
3.  **Create .env file:** Create a `.env` file in the workspace directory to store the `GEMINI_API_KEY`.
4.  **Create Dockerfile:** Create a `Dockerfile` in the workspace directory to define the application's container environment.
5.  **Install Dependencies:** The necessary Python packages (`streamlit`, `pandas`, `google-generativeai`) will be installed using pip, as specified in the Dockerfile.
6.  **Build Docker Image:** Build the Docker image for the application.
7.  **Run Docker Container:** Run the Docker container, mounting the `.env` file and exposing the necessary port.