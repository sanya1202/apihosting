import uvicorn
from fastapi import FastAPI, File, UploadFile
import google.generativeai as genai
import pandas as pd
import tempfile
import json
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware

# Configure the API key
api_key = 'AIzaSyDJU1mkvu6cci0lOGKgxFK17YZeHkfVwdQ'  # Replace with your actual API key
genai.configure(api_key=api_key)

# Define the app object
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change this for production environments
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define categories for non-fruit/vegetable products
categories = ["Personal Care", "Household Care", "Dairy", "Staples", "Snacks and Beverages", "Packaged Food", "Fruits and Vegetables"]

# Upload image function
def upload_image(image_bytes):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
        temp_file.write(image_bytes)
        temp_file_path = temp_file.name
    
    sample_file = genai.upload_file(temp_file_path)
    return sample_file

# Classify image content (fruits/vegetables or others)
def classify_image(sample_file):
    model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest")
    response = model.generate_content([sample_file, "check whther it is an image of vegetable/fruit , do not get confused by the images of fruits and vegetables that are there on the packet of packaged food itmes? Answer 'yes' or 'no' only."])
    classification = response.text.strip().lower()
    return classification == "yes"

# Predict freshness for fruits/vegetables
def predict_freshness(sample_file):
    model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest")
    response = model.generate_content([sample_file, "Rate the freshness of the fruits/vegetables in the image on a scale of 1 to 10."])
    try:
        return int(response.text.strip())
    except ValueError:
        return None

# Generate product details for non-fruits/vegetables
def generate_product_details(sample_file):
    model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest")
    response = model.generate_content([
        sample_file, 
        f'List timestamp,product names,brands, MRP, expiry date,product count,whether it is expired YES or NO by comparing with today's date and expected life span in days by subtracting today's date from the expiry date and if it is already expired give expected life span as NA and if some details are not found then fill NA from the image in json format like this: '
        f'{{"products": [{{ "timestamp":"2024-12-10T05:14:01+05:30",product_name": "Tata Salt", "brand": "Tata" , "MRP":"60RS" ,"Expiry Date":"25-06-2025","count":"1","expired":"NO","expected_life_span":"197"}}, '
        f'{{ "timestamp":"2024-12-10T05:14:01+05:30","product_name": "Boost", "brand": "Nestlé",MRP":"60RS"  ,"Expiry Date":"25-06-2025","count":"1","expired":"NO","expected_life_span":"197"}}]}}. '
        f'I want only these details, no more text.'
    ])
    response_text = response.text.strip()
    print(f"Generated Product Details Response: {response_text}")  # Debugging output
    return response_text

def parse_response_to_dataframe(response_text):
    try:
        if response_text.startswith("```json") and response_text.endswith("```"):
            response_text = response_text[7:-3].strip()
        # Attempt to parse the response text as JSON
        products_list = json.loads(response_text)
        if 'products' in products_list:
            return pd.DataFrame(products_list['products'])
        else:
            print("No 'products' key found in response.")
            return pd.DataFrame()  # Return an empty DataFrame
    except json.JSONDecodeError:
        print("Failed to parse response text as JSON.")
        return pd.DataFrame()  # Return an empty DataFrame

# Define index route
@app.get('/')
def index():
    return {'message': 'Image API - Send an image to /predict'}

# Define the image prediction route
@app.post('/predict')
async def predict_image(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        sample_file = upload_image(contents)
        
        if not sample_file:
            return {"error": "Failed to upload the image"}

        is_fruits_or_vegetables = classify_image(sample_file)
        
        if is_fruits_or_vegetables:
            freshness_index = predict_freshness(sample_file)
            if freshness_index is not None:
                return {
                    "filename": file.filename,
                    "message": f"Image contains fruits/vegetables with a predicted freshness index of {freshness_index}"
                }
            else:
                return {"error": "Unable to predict freshness."}
        else:
            response_text = generate_product_details(sample_file)
            if response_text:
                df = parse_response_to_dataframe(response_text)
                if df.empty:
                    return {
                        "filename": file.filename,
                        "message": "No relevant product details found."
                    }
                return {
                    "filename": file.filename,
                    "message": "Product details extracted successfully.",
                    "product_details": df.to_dict(orient='records')
                }
            else:
                return {"error": "Unable to extract product details."}
    
    except Exception as e:
        return {"error": str(e)}

# Run the API with Uvicorn
if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=8000)
