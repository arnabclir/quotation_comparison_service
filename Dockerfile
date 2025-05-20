# Use a lightweight Python image
FROM python:3.12-slim

# Set the working directory
WORKDIR /app

# Copy the requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create .streamlit directory and copy secrets.toml if it exists
RUN mkdir -p /app/.streamlit
COPY .streamlit/secrets.toml .streamlit/secrets.toml

# Copy the application code
COPY . /app

# Expose the Streamlit port
EXPOSE 8501

# Command to run the Streamlit application
CMD ["streamlit", "run", "app.py"]