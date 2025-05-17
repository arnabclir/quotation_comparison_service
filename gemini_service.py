import streamlit as st
import os
import json
import tempfile
import shutil
from google import genai
from google.genai import types
from io import BytesIO
import base64 # Although not directly used in the moved code, it was in the original block, keeping for now.
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Gemini API Key Configuration ---
# Ensure your GEMINI_API_KEY is set as an environment variable
# For Streamlit Cloud, set it in the secrets.
# This could potentially be moved to a config module later if needed
if "GEMINI_API_KEY" in st.secrets:
    os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]

# --- Gemini Data Extraction Function ---
def run_gemini_extraction(uploaded_files):
    """
    Uploads files to Gemini, sends them for processing, and returns structured SKU data.
    Returns a list of dictionaries representing raw SKU data, or None on failure.
    """
    if not uploaded_files:
        return None

    client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY"),
    )

    gemini_files = []
    file_uris_for_prompt = []
    temp_files = []
    try:
        with st.spinner(f"Uploading {len(uploaded_files)} files to Gemini..."):
            for uploaded_file in uploaded_files:
                # Save uploaded file to a temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(uploaded_file.getvalue())
                    temp_files.append(tmp.name)
                # Upload file using file path (latest Gemini API)
                gf = client.files.upload(file=tmp.name)
                gemini_files.append(gf)
                file_uris_for_prompt.append(
                    types.Part.from_uri(file_uri=gf.uri, mime_type=gf.mime_type)
                )
                st.write(f"Uploaded {uploaded_file.name} to Gemini.")

        # Prepare prompt parts
        prompt_parts = [
            *file_uris_for_prompt,
            types.Part.from_text(text="""These are PDF quotation files received by a company.
                                  \nInstructions:\n
                                  1. For each distinct product item listed in these documents, extract the following details.\n
                                  2. The 'sku_supplier' should be the name of the company providing the quotation (e.g., NARSINGH PHARMA, MEDIVISION, S. D. M. AGENCY), not the medicine manufacturer like Alembic, Cipla, etc.\n
                                  3. Extract the product name as 'sku_name' (e.g., PARACETAMOL 500MG TAB). \n
                                  If there are product names across the quotations with similar product names, they should be given a common sku_name and used in the output\
                                  Ex: (i) "GLUCONORM G 1" and "GLUCONORM G1" are the same product \n
                                      (ii) "JANUMET 50/500" and "JANUMET 50/500 TAB" are the same product\n
                                      (iii) "JUST TEAR E/D" and "JUST TEAR LUBRICANT E/D" are the same product\n
                                      (iv) "SEROFLO 250 R/C", "SEROFLO 250 ROTA" and "SEROFLO 250 ROTACAP" are the same product\n
                                      (v) "ATORVA 20MG TAB" and "ATORVA-20" are the same product\n
                                  etc.\n
                                  4. Ensure all numeric fields like MRP, Base Rate, and Discount are extracted as strings, exactly as they appear.\n
                                  5. Extract the paid quantity as an integer in the 'paid_qty' field.\n
                                  6. Extract the free quantity as an integer in the 'free_qty' field.\n
                                  7. If a product appears in multiple documents, create a separate entry for each instance.\n
                                  8. Extract the batch number for each item. This is typically labeled "Batch" and may look like "IAK0040", "24491211", or "JT-2412".\n
                                  9. Extract the total price for the listed quantity of the SKU as an integer in the 'amount' field.\n
                                  Extract the data in the specified JSON schema including 'sku_name', 'paid_qty', 'free_qty', and 'amount'."""),
        ]

        generate_content_config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=genai.types.Schema(
                type=genai.types.Type.OBJECT,
                properties={
                    "sku_data": genai.types.Schema(
                        type=genai.types.Type.ARRAY,
                        items=genai.types.Schema(
                            type=genai.types.Type.OBJECT,
                            properties={
                                "sku_supplier": genai.types.Schema(type=genai.types.Type.STRING),
                                "sku_invoice": genai.types.Schema(type=genai.types.Type.STRING),
                                "sku_name": genai.types.Schema(type=genai.types.Type.STRING),
                                "mrp": genai.types.Schema(type=genai.types.Type.STRING),
                                "base_rate": genai.types.Schema(type=genai.types.Type.STRING),
                                "base_discount_percent": genai.types.Schema(type=genai.types.Type.STRING),
                                "paid_qty": genai.types.Schema(type=genai.types.Type.INTEGER),
                                "free_qty": genai.types.Schema(type=genai.types.Type.INTEGER),
                                "batch_number": genai.types.Schema(type=genai.types.Type.STRING),
                                "amount": genai.types.Schema(type=genai.types.Type.INTEGER),
                            },
                        ),
                    ),
                },
            ),
        )

        st.write("Sending request to Gemini for data extraction...")
        with st.spinner("Gemini is processing the documents... This may take a moment."):
            response_text = ""
            for chunk in client.models.generate_content_stream(
                model="gemini-2.0-flash",
                contents=[types.Content(role="user", parts=prompt_parts)],
                config=generate_content_config,
            ):
                response_text += chunk.text

        # Try to parse the JSON output
        try:
            json_data = json.loads(response_text)
            logging.info("Successfully decoded JSON response from Gemini.")
            return json_data.get("sku_data", [])
        except json.JSONDecodeError as e:
            logging.error(f"Error decoding JSON response from Gemini: {e}")
            st.error(f"Error decoding JSON response from Gemini. See logs for details.")
            st.text_area("Gemini Raw Response (Decoding Error)", response_text, height=200)
            return None
        except Exception as e:
            logging.error(f"An unexpected error occurred while processing Gemini response: {e}")
            st.error(f"An unexpected error occurred while processing Gemini response. See logs for details.")
            st.text_area("Gemini Raw Response (Processing Error)", response_text, height=200)
            return None
    except Exception as e:
        logging.error(f"An error occurred during Gemini processing: {e}")
        st.error(f"An error occurred during Gemini processing. See logs for details.")
        return None
    finally:
        # Clean up temp files
        for f in temp_files:
            try:
                os.remove(f)
            except Exception as e:
                logging.warning(f"Could not remove temporary file {f}: {e}")