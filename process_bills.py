import imaplib
import email
import os
import json
import google.generativeai as genai
from datetime import datetime

# --- CONFIGURATION ---
EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASS = os.environ["GMAIL_APP_PASSWORD"]
GEMINI_KEY = os.environ["GEMINI_API_KEY"]

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-pro')

def get_latest_emails():
    print("Connecting to Gmail...")
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(EMAIL_USER, EMAIL_PASS)
    mail.select("inbox")

    # Change 1: Search for ANY email with "LIC" or "Premium" in subject
    # This covers "LIC Receipt", "Premium Payment", etc.
    status, messages = mail.search(None, '(OR (SUBJECT "LIC") (SUBJECT "Premium"))')
    
    email_ids = messages[0].split()
    
    if not email_ids:
        print("No related emails found.")
        return []

    data_list = []
    
    # Change 2: Scan last 15 emails to find older bills (3 days old)
    print(f"Scanning last {min(15, len(email_ids))} emails...")
    for e_id in email_ids[-15:]:
        try:
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

                    if body:
                        # Ask Gemini to Extract Data
                        prompt = f"""
                        Analyze this email text. It might be an LIC receipt or premium notice. 
                        Extract these 5 fields into JSON:
                        - policy_holder_name
                        - policy_number
                        - mode (e.g. Yearly, Quarterly)
                        - premium_amount (number only, remove commas)
                        - next_due_date (DD/MM/YYYY)

                        If exact data is missing, guess based on context or put "N/A".
                        Email Body: {body[:3000]} 
                        """
                        
                        try:
                            response = model.generate_content(prompt)
                            clean_json = response.text.replace("```json", "").replace("```", "").strip()
                            data = json.loads(clean_json)
                            
                            # Valid Check: Sirf tab add karo jab Policy Number mile
                            if data.get('policy_number') and data.get('policy_number') != "N/A":
                                data_list.append(data)
                                print(f"Found Bill: {data['policy_number']}")
                        except:
                            pass # Skip if extraction fails

        except Exception as e:
            print(f"Error on email {e_id}: {e}")

    mail.logout()
    return data_list

def update_database(new_data):
    db_file = 'lic_data.json'
    existing_data = []
    
    if os.path.exists(db_file):
        with open(db_file, 'r') as f:
            try:
                existing_data = json.load(f)
            except:
                existing_data = []

    # Duplicate Check
    existing_keys = {f"{item['policy_number']}_{item.get('next_due_date')}" for item in existing_data}
    
    for item in new_data:
        key = f"{item['policy_number']}_{item.get('next_due_date')}"
        if key not in existing_keys:
            existing_data.append(item)
            print(f"New Record Added: {item['policy_number']}")
    
    with open(db_file, 'w') as f:
        json.dump(existing_data, f, indent=4)

if __name__ == "__main__":
    data = get_latest_emails()
    if data:
        update_database(data)
    else:
        print("No relevant emails found in last 15 messages.")
