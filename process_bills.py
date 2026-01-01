import imaplib
import email
from email.header import decode_header
import os
import json
import google.generativeai as genai
from datetime import datetime

# 1. Setup Configurations from GitHub Secrets
EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASS = os.environ["GMAIL_APP_PASSWORD"]
GEMINI_KEY = os.environ["GEMINI_API_KEY"]

# 2. Configure Gemini
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-pro')

def get_latest_emails():
    # Connect to Gmail
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(EMAIL_USER, EMAIL_PASS)
    mail.select("inbox")

    # Search for LIC emails (Adjust keyword as needed)
    # We look for emails from last 1 day to keep it fast
    status, messages = mail.search(None, '(FROM "lic.india@licindia.com")') 
    
    email_ids = messages[0].split()
    data_list = []

    # Process last 3 emails only (to save time)
    for e_id in email_ids[-3:]:
        _, msg_data = mail.fetch(e_id, "(RFC822)")
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])
                
                # Extract Body
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode()
                            break
                else:
                    body = msg.get_payload(decode=True).decode()

                # 3. ASK GEMINI TO EXTRACT DATA
                if body:
                    prompt = f"""
                    Analyze this email text from LIC. Extract the following details into a valid JSON format:
                    - policy_holder_name
                    - policy_number
                    - premium_amount (just the number)
                    - payment_date (DD/MM/YYYY)
                    - next_due_date (DD/MM/YYYY)
                    
                    If specific data is missing, put "N/A".
                    Email Text: {body}
                    """
                    
                    try:
                        response = model.generate_content(prompt)
                        # Clean up Gemini response to get pure JSON
                        json_text = response.text.replace("```json", "").replace("```", "")
                        data = json.loads(json_text)
                        data_list.append(data)
                        print(f"Extracted: {data['policy_number']}")
                    except Exception as e:
                        print(f"Gemini Error: {e}")

    mail.logout()
    return data_list

# 4. Save to Database (JSON file)
def update_database(new_data):
    db_file = 'lic_data.json'
    
    # Load existing data
    if os.path.exists(db_file):
        with open(db_file, 'r') as f:
            existing_data = json.load(f)
    else:
        existing_data = []

    # Avoid duplicates (Check by Policy Number + Date)
    existing_policies = {f"{x['policy_number']}_{x['payment_date']}" for x in existing_data}
    
    for item in new_data:
        unique_key = f"{item['policy_number']}_{item['payment_date']}"
        if unique_key not in existing_policies:
            existing_data.append(item)
            print(f"Added new record: {item['policy_number']}")

    # Write back
    with open(db_file, 'w') as f:
        json.dump(existing_data, f, indent=4)

if __name__ == "__main__":
    extracted_data = get_latest_emails()
    if extracted_data:
        update_database(extracted_data)
    else:
        print("No new data found.")
