# Import necessary modules from Flask and other libraries
from flask import Flask, render_template, request, redirect, url_for, flash, session, Response
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
import os
from datetime import datetime
import requests
import json
import cloudinary
import cloudinary.uploader
import cloudinary.api

# Initialize the Flask application
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your_super_secret_key_for_customer_app_2025_new')

# --- Configuration for Google Sheets & Drive API Access ---
GOOGLE_API_SCOPE = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]

SERVICE_ACCOUNT_KEY_FILE = 'firebase-service-account.json'

# --- Google Sheets Configuration ---
USER_LOGIN_SPREADSHEET_NAME = 'UserLoginData'
USER_LOGIN_WORKSHEET_NAME = 'users'

SPREADSHEET_NAME = 'data1'
WORKSHEET_NAME = 'customer_records'

LOAN_TRANSACTIONS_WORKSHEET_NAME = os.environ.get('LOAN_TRANSACTIONS_WORKSHEET_NAME', 'Loan_Transactions')
LOAN_TRANSACTIONS_WORKSHEET_HEADERS = [
    'Timestamp', 'เลขบัตรประชาชนลูกค้า', 'ชื่อลูกค้า', 'นามสกุลลูกค้า',
    'วงเงินกู้', 'ดอกเบี้ย (%)', 'ระยะเวลากู้ (เดือน)', 'วันที่เริ่มกู้', 
    'วันครบกำหนด', 'ยอดที่ต้องชำระรายเดือน', 'ยอดชำระแล้ว', 'ยอดค้างชำระ', 
    'สถานะเงินกู้', 'หมายเหตุเงินกู้', 'ผู้บันทึก'
]

CUSTOMER_DATA_WORKSHEET_HEADERS = [
    'Timestamp', 'ชื่อ', 'นามสกุล', 'เลขบัตรประชาชน', 'เบอร์มือถือ',
    'จดทะเบียน', 'ชื่อกิจการ', 'ประเภทธุรกิจ', 'ที่อยู่จดทะเบียน', 'สถานะ',
    'วงเงินที่ต้องการ', 'วงเงินที่อนุมัติ', 'เคยขอเข้ามาในเครือหรือยัง', 'เช็ค',
    'ขอเข้ามาทางไหน', 'LINE ID', 'หักดอกหัวท้าย', 'ค่าดำเนินการ',
    'วันที่ขอเข้ามา', 'ลิงค์โลเคชั่นบ้าน', 'ลิงค์โลเคชั่นที่ทำงาน', 'หมายเหตุ',
    'Image URLs',
    'Logged In User'
]

# NEW: Define headers for the Loan Transactions worksheet
LOAN_TRANSACTIONS_WORKSHEET_HEADERS = [
    'Timestamp', 'เลขบัตรประชาชนลูกค้า', 'ชื่อลูกค้า', 'นามสกุลลูกค้า',
    'วงเงินกู้', 'ดอกเบี้ย (%)', 'ระยะเวลากู้ (เดือน)', 'วันที่เริ่มกู้', 
    'วันครบกำหนด', 'ยอดที่ต้องชำระรายเดือน', 'ยอดชำระแล้ว', 'ยอดค้างชำระ', 
    'สถานะเงินกู้', 'หมายเหตุเงินกู้', 'ผู้บันทึก'
]


# --- Cloudinary Configuration ---
cloudinary.config(
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key = os.environ.get('CLOUDINARY_API_KEY'),
    api_secret = os.environ.get('CLOUDINARY_API_SECRET')
)

# --- Initialize Google API Clients ---
GSPREAD_CLIENT = None
DRIVE_CLIENT = None

try:
    creds_json = None

    if os.environ.get('GOOGLE_CREDENTIALS_JSON'):
        creds_json_str = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        creds_json = json.loads(creds_json_str)
    else:
        with open(SERVICE_ACCOUNT_KEY_FILE, 'r') as f:
            creds_json = json.load(f)

    if creds_json:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, GOOGLE_API_SCOPE)
        GSPREAD_CLIENT = gspread.authorize(creds)
        gauth = GoogleAuth()
        gauth.credentials = creds
        DRIVE_CLIENT = GoogleDrive(gauth)
    else:
        raise ValueError("Service Account credentials could not be loaded from environment or file.")

except Exception as e:
    print(f"CRITICAL ERROR: Google API clients failed to initialize. Error: {e}")
    GSPREAD_CLIENT = None
    DRIVE_CLIENT = None


def get_all_customer_records():
    # ... (code for get_all_customer_records remains the same) ...
    """
    Retrieves all customer records from the worksheet, including their 1-based row index.
    Each record will be a dictionary with an additional 'row_index' key.
    """
    worksheet = get_customer_data_worksheet() # ใช้ฟังก์ชัน get_customer_data_worksheet() ที่ถูกแก้ไขแล้ว
    if not worksheet:
        return []
    try:
        # Get all data as a list of lists, including headers
        all_data = worksheet.get_all_values()
        if not all_data:
            print("DEBUG: Google Sheet 'all_data' is empty or only has headers.")
            return []

        # Assume the first row is headers
        headers = all_data[0]
        data_rows = all_data[1:] # All rows after the header
        # print(f"DEBUG: get_all_customer_records - headers: {headers}") # Commented out for less verbose logs
        # print(f"DEBUG: get_all_customer_records - data_rows contains {len(data_rows)} rows. First data row: {data_rows[0] if data_rows else 'N/A'}") # Commented out

        customer_records = []
        for i, row in enumerate(data_rows):
            # print(f"DEBUG: Loop entered for i={i}, processing row (snippet): {row[:5]}...") # Commented out
            # Create a dictionary for each row
            record = {}
            for j, header in enumerate(headers):
                if j < len(row): # Ensure index is within bounds of the current row
                    record[header] = row[j]
                else:
                    record[header] = '' # Handle cases where row might be shorter than headers
            
            # Add the 1-based row index (actual row in Google Sheet)
            # i is 0-indexed for data_rows, so i + 2 gives the 1-based row number
            # (1 for 0-indexing + 1 for header row)
            record['row_index'] = i + 2

            # print(f"DEBUG: Added record with row_index {record['row_index']} - Record snippet: {record.get('ชื่อ', '')}, Status: {record.get('สถานะ', '')}") # Commented out
            
            customer_records.append(record)
        # print(f"DEBUG: get_all_customer_records - Returning {len(customer_records)} records. First record BEFORE return: {customer_records[0] if customer_records else 'N/A'}") # Commented out
        return customer_records
    except Exception as e:
        print(f"ERROR in get_all_customer_records: {e}")
        return []


def get_customer_records_by_status(status):
    # ... (code for get_customer_records_by_status remains the same) ...
    """
    Retrieves customer records filtered by status.
    Assumes get_all_customer_records already adds 'row_index'.
    """
    print(f"DEBUG: get_customer_records_by_status called with status: {status}")
    all_records = get_all_customer_records() # เรียกใช้ฟังก์ชันที่ดึงข้อมูลทั้งหมดพร้อม row_index
    filtered_records = [record for record in all_records if record.get('สถานะ') == status]
    print(f"DEBUG: get_customer_records_by_status returning {len(filtered_records)} records for status '{status}'")
    return filtered_records

def get_customer_records_by_keyword(keyword):
    # ... (code for get_customer_records_by_keyword remains the same) ...
    """
    Retrieves customer records filtered by keyword across all values.
    Assumes get_all_customer_records already adds 'row_index'.
    """
    print(f"DEBUG: get_customer_records_by_keyword called with keyword: {keyword}")
    all_records = get_all_customer_records() # เรียกใช้ฟังก์ชันที่ดึงข้อมูลทั้งหมดพร้อม row_index
    filtered_records = [
        record for record in all_records
        if any(keyword.lower() in str(value).lower() for value in record.values())
    ]
    print(f"DEBUG: get_customer_records_by_keyword returning {len(filtered_records)} records for keyword '{keyword}'")
    return filtered_records

def load_users():
    # ... (code for load_users remains the same) ...
    """
    Loads user IDs and passwords from the specified Google Sheet (UserLoginData).
    It expects the sheet to have columns named 'id' and 'pass'.
    Returns a dictionary where keys are user IDs and values are their passwords.
    Returns an empty dictionary if there's an error or columns are missing.
    """
    if not GSPREAD_CLIENT: # ใช้ GSPREAD_CLIENT ที่ถูกกำหนดไว้แล้ว
        print("Gspread client not initialized. Cannot load users.")
        return {}
    try:
        # ใช้ USER_LOGIN_SPREADSHEET_NAME และ USER_LOGIN_WORKSHEET_NAME สำหรับการโหลดผู้ใช้
        sheet = GSPREAD_CLIENT.open(USER_LOGIN_SPREADSHEET_NAME).worksheet(USER_LOGIN_WORKSHEET_NAME) # ใช้ GSPREAD_CLIENT โดยตรง
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        if 'id' in df.columns and 'pass' in df.columns:
            users = dict(zip(df['id'], df['pass']))
            return users
        else:
            print("Error: 'id' or 'pass' columns not found in Google Sheet. Please check your sheet structure.")
            return {}
    except Exception as e:
        print(f"Error loading users from Google Sheet: {e}")
        return {}

def get_customer_data_worksheet():
    # ... (code for get_customer_data_worksheet remains the same) ...
    """
    Gets the customer data worksheet from the 'data1' Google Sheet.
    Creates it if it doesn't exist. Also ensures the header row is present and matches the defined headers.
    """
    if not GSPREAD_CLIENT: # ใช้ GSPREAD_CLIENT ที่ถูกกำหนดไว้แล้ว
        print("Gspread client not initialized. Cannot access customer data worksheet.")
        return None
    try:
        # ใช้ SPREADSHEET_NAME (ซึ่งคือ 'data1') สำหรับข้อมูลลูกค้า
        spreadsheet = GSPREAD_CLIENT.open(SPREADSHEET_NAME) # ใช้ GSPREAD_CLIENT โดยตรง
        try:
            worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
            # Verify headers if worksheet already exists
            existing_headers = worksheet.row_values(1)
            if existing_headers != CUSTOMER_DATA_WORKSHEET_HEADERS:
                print("Warning: Existing worksheet headers do not match expected headers. Attempting to update headers.")
                worksheet.update('A1', [CUSTOMER_DATA_WORKSHEET_HEADERS]) # Update row 1 with new headers
                print(f"Worksheet '{WORKSHEET_NAME}' headers updated.")
        except gspread.exceptions.WorksheetNotFound:
            print(f"Worksheet '{WORKSHEET_NAME}' not found. Creating it...")
            worksheet = spreadsheet.add_worksheet(title=WORKSHEET_NAME, rows="100", cols=str(len(CUSTOMER_DATA_WORKSHEET_HEADERS)))
            worksheet.append_row(CUSTOMER_DATA_WORKSHEET_HEADERS)
            print(f"Worksheet '{WORKSHEET_NAME}' created with headers.")
        return worksheet
    except Exception as e:
        print(f"Error accessing/creating customer data worksheet: {e}")
        return None

# Helper function to get the Loan Transactions worksheet
def get_loan_worksheet():
    """
    Gets the Loan_Transactions worksheet.
    Creates it if it doesn't exist and ensures headers are correct.
    """
    if not GSPREAD_CLIENT:
        print("Gspread client not initialized. Cannot access Loan Transactions worksheet.")
        return None
    try:
        # ใช้ SPREADSHEET_NAME ('data1') เดียวกันกับชีทข้อมูลลูกค้าหลัก
        spreadsheet = GSPREAD_CLIENT.open(SPREADSHEET_NAME) 

        try:
            # พยายามเข้าถึง Worksheet ที่มีอยู่
            worksheet = spreadsheet.worksheet(LOAN_TRANSACTIONS_WORKSHEET_NAME)

            # ตรวจสอบ Headers หาก Worksheet มีอยู่แล้ว
            existing_headers = worksheet.row_values(1)
            if not existing_headers or existing_headers != LOAN_TRANSACTIONS_WORKSHEET_HEADERS:
                print(f"Warning: Loan Transactions worksheet headers do not match expected headers or are empty. Updating headers to: {LOAN_TRANSACTIONS_WORKSHEET_HEADERS}")
                worksheet.update('A1', [LOAN_TRANSACTIONS_WORKSHEET_HEADERS])
                print(f"Worksheet '{LOAN_TRANSACTIONS_WORKSHEET_NAME}' headers updated.")
        except gspread.exceptions.WorksheetNotFound:
            print(f"Worksheet '{LOAN_TRANSACTIONS_WORKSHEET_NAME}' not found. Creating it...")
            # สร้าง Worksheet ใหม่พร้อม Headers
            worksheet = spreadsheet.add_worksheet(
                title=LOAN_TRANSACTIONS_WORKSHEET_NAME, 
                rows="100", # กำหนดจำนวนแถวเริ่มต้น (ปรับได้ตามต้องการ)
                cols=str(len(LOAN_TRANSACTIONS_WORKSHEET_HEADERS)) # กำหนดจำนวนคอลัมน์ตาม Headers
            )
            worksheet.append_row(LOAN_TRANSACTIONS_WORKSHEET_HEADERS) # เพิ่ม Headers
            print(f"Worksheet '{LOAN_TRANSACTIONS_WORKSHEET_NAME}' created with headers.")

        return worksheet
    except Exception as e:
        print(f"Error accessing or creating Loan Transactions worksheet: {e}")
        return None


# NEW: Helper function to get all loan records
def get_all_loan_records():
    """
    Retrieves all loan transaction records from the worksheet, including their 1-based row index.
    Each record will be a dictionary with an additional 'row_index' key.
    """
    worksheet = get_loan_worksheet()
    if not worksheet:
        return []
    try:
        all_data = worksheet.get_all_values()
        if not all_data:
            print("DEBUG: Google Sheet 'Loan Transactions' data is empty or only has headers.")
            return []

        headers = all_data[0]
        data_rows = all_data[1:]

        loan_records = []
        for i, row in enumerate(data_rows):
            record = {}
            for j, header in enumerate(headers):
                if j < len(row):
                    record[header] = row[j]
                else:
                    record[header] = ''
            
            record['row_index'] = i + 2 # 1-based row index in Google Sheet
            loan_records.append(record)
        return loan_records
    except Exception as e:
        print(f"ERROR in get_all_loan_records: {e}")
        return []


def upload_image_to_cloudinary(file_stream, original_filename):
    # ... (code for upload_image_to_cloudinary remains the same) ...
    """
    Uploads an image file stream to Cloudinary.
    Returns the URL of the uploaded file, or None if upload fails.
    """
    try:
        # Upload the file directly from the stream
        # The 'folder' parameter allows you to organize images in Cloudinary
        upload_result = cloudinary.uploader.upload(
            file_stream,
            folder="customer_app_images" # คุณสามารถเปลี่ยนชื่อโฟลเดอร์นี้ได้ตามต้องการใน Cloudinary
        )

        if upload_result and 'secure_url' in upload_result:
            print(f"Uploaded file '{original_filename}' to Cloudinary. URL: {upload_result['secure_url']}")
            return upload_result['secure_url']
        else:
            print(f"Error uploading image '{original_filename}' to Cloudinary: No secure_url returned.")
            return None
    except Exception as e:
        print(f"Error uploading image '{original_filename}' to Cloudinary: {e}")
        return None

def delete_image_from_cloudinary(image_url):
    # ... (code for delete_image_from_cloudinary remains the same) ...
    """
    Deletes an image from Cloudinary using its URL.
    """
    if not image_url:
        return True # ไม่มี URL ให้ลบ ถือว่าสำเร็จ

    try:
        # Extract public_id from Cloudinary URL
        # Example URL: https://res.cloudinary.com/your_cloud_name/image/upload/v12345/folder/public_id.jpg
        parts = image_url.split('/')
        if len(parts) < 2: # Basic check for valid URL structure
            print(f"Invalid Cloudinary URL for deletion: {image_url}")
            return False

        # The public_id is usually the last part before the file extension,
        # sometimes including folder path if specified during upload
        # We need to get the part that was used as 'public_id' in Cloudinary.
        # A more robust way would be to store public_id in the sheet.
        # For simplicity, let's try to extract it from the URL based on the 'folder' we used during upload
        public_id_with_folder = "/".join(parts[-2:]).split('.')[0] # e.g., "customer_app_images/image_001"
        
        # If you used a specific folder, you must include it in the public_id for deletion
        # In our example, folder is 'customer_app_images'
        if "customer_app_images" in public_id_with_folder:
            public_id_to_delete = public_id_with_folder
        else: # Fallback if not in folder, assuming it's root
            public_id_to_delete = parts[-1].split('.')[0]

        print(f"Attempting to delete Cloudinary image with public_id: {public_id_to_delete}")

        delete_result = cloudinary.uploader.destroy(public_id_to_delete)

        if delete_result and delete_result.get('result') == 'ok':
            print(f"Successfully deleted image from Cloudinary: {image_url}")
            return True
        else:
            print(f"Failed to delete image from Cloudinary: {image_url}, Result: {delete_result}")
            return False
    except Exception as e:
        print(f"Error deleting image from Cloudinary: {image_url}, Error: {e}")
        return False


# --- Flask Routes Definition ---

@app.route('/', methods=['GET', 'POST'])
def login():
    # ... (code for login remains the same) ...
    """
    Handles user login functionality.
    """
    error = None
    users = load_users()

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username in users and users[username] == password:
            session['username'] = username # Store username in session
            return redirect(url_for('dashboard')) # Redirect to dashboard without username in URL
        else:
            error = "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"
    return render_template('login.html', error=error)

@app.route('/dashboard')
def dashboard():
    # ... (code for dashboard remains the same) ...
    """
    Displays the main menu page after successful login.
    Requires user to be logged in.
    """
    if 'username' not in session:
        flash('กรุณาเข้าสู่ระบบก่อน', 'error')
        return redirect(url_for('login'))
    username = session['username']
    return render_template('main_menu.html', username=username)

@app.route('/logout')
def logout():
    # ... (code for logout remains the same) ...
    """
    Logs out the user by clearing the session.
    """
    session.pop('username', None) # Remove username from session
    flash('คุณได้ออกจากระบบแล้ว', 'success')
    return redirect(url_for('login'))

@app.route('/enter_customer_data', methods=['GET', 'POST'])
def enter_customer_data():
    # ... (code for enter_customer_data remains the same) ...
    """
    Handles customer data entry.
    - GET request: Displays the data entry form.
    - POST request: Processes the submitted customer data and images.
    Requires user to be logged in.
    """
    if 'username' not in session:
        flash('กรุณาเข้าสู่ระบบก่อน', 'error')
        return redirect(url_for('login'))

    logged_in_user = session['username'] # Get logged-in username from session

    if request.method == 'POST':
        # Get text data from the form using .get() with a default empty string
        # Then replace empty strings with "-"
        customer_name = request.form.get('customer_name', '') or '-'
        last_name = request.form.get('last_name', '') or '-'
        id_card_number = request.form.get('id_card_number', '') or '-'
        mobile_phone_number = request.form.get('mobile_phone_number', '') or '-'
        registered = request.form.get('registered', '') or '-'
        business_name = request.form.get('business_name', '') or '-'
        business_type = request.form.get('business_type', '') or '-'
        registered_address = request.form.get('registered_address', '') or '-'
        status = request.form.get('status', '') or '-'
        desired_credit_limit = request.form.get('desired_credit_limit', '') or '-'
        approved_credit_limit = request.form.get('approved_credit_limit', '') or '-'
        applied_before = request.form.get('applied_before', '') or '-'
        check = request.form.get('check', '') or '-'
        how_applied = request.form.get('how_applied', '') or '-'
        line_id = request.form.get('line_id', '') or '-'
        upfront_interest = request.form.get('upfront_interest', '') or '-'
        processing_fee = request.form.get('processing_fee', '') or '-'
        application_date = request.form.get('application_date', '') or '-' # Keep this required in HTML for now
        home_location_link = request.form.get('home_location_link', '') or '-'
        work_location_link = request.form.get('work_location_link', '') or '-'
        remarks = request.form.get('remarks', '') or '-'

        # Handle multiple image uploads
        image_urls = []
        if 'customer_images' in request.files:
            files = request.files.getlist('customer_images')
            for customer_image in files:
                if customer_image and customer_image.filename:
                    url = upload_image_to_cloudinary(customer_image.stream, customer_image.filename)
                    if url:
                        image_urls.append(url)
                    # else: flash message is already handled inside upload_image_to_drive
        
        # Join all image URLs into a single comma-separated string, or "-" if no images
        image_urls_str = ', '.join(image_urls) if image_urls else '-'

        # Get the customer data worksheet
        worksheet = get_customer_data_worksheet() # ใช้ get_customer_data_worksheet() ที่ถูกแก้ไขแล้ว
        if worksheet:
            try:
                # Prepare the data row, ensuring order matches CUSTOMER_DATA_WORKSHEET_HEADERS
                row_data = [
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'), # Timestamp
                    customer_name,
                    last_name,
                    id_card_number,
                    mobile_phone_number,
                    registered,
                    business_name,
                    business_type,
                    registered_address,
                    status,
                    desired_credit_limit,
                    approved_credit_limit,
                    applied_before,
                    check,
                    how_applied,
                    line_id,
                    upfront_interest,
                    processing_fee,
                    application_date,
                    home_location_link,
                    work_location_link,
                    remarks,
                    image_urls_str, # Comma-separated image URLs
                    logged_in_user # Logged In User - This is the last item in the row
                ]
                worksheet.append_row(row_data)
                flash('บันทึกข้อมูลลูกค้าเรียบร้อยแล้ว!', 'success')
                return redirect(url_for('enter_customer_data')) # Redirect to clear form
            except Exception as e:
                flash(f'เกิดข้อผิดพลาดในการบันทึกข้อมูล: {e}', 'error')
                print(f"Error saving data to Google Sheet: {e}") # Log to console for debugging
        else:
            flash('ไม่สามารถเข้าถึง Google Sheet สำหรับบันทึกข้อมูลลูกค้าได้', 'error')
            print("Error: Customer data worksheet not available.") # Log to console for debugging

    return render_template('data_entry.html', username=logged_in_user) # Pass username to template

@app.route('/search_customer_data', methods=['GET'])
def search_customer_data():
    # ... (code for search_customer_data remains the same) ...
    """
    Handles searching for customer data.
    Can search by keyword or filter by 'รอดำเนินการ' status.
    Requires user to be logged in.
    """
    if 'username' not in session:
        flash('กรุณาเข้าสู่ระบบก่อน', 'error')
        return redirect(url_for('login'))

    logged_in_user = session['username']
    
    search_keyword = request.args.get('search_keyword', '').strip()
    status_filter = request.args.get('status_filter', '').strip()

    customer_records = []
    display_title = "ค้นหาข้อมูลลูกค้า" # Default title

    if status_filter == 'pending':
        customer_records = get_customer_records_by_status("รอดำเนินการ")
        display_title = "ข้อมูลลูกค้า: รอดำเนินการ"
        if not customer_records:
            flash("ไม่พบข้อมูลลูกค้าที่มีสถานะ 'รอดำเนินการ'", "info")
        else:
            flash(f"พบ {len(customer_records)} รายการที่มีสถานะ 'รอดำเนินการ'", "success")
    elif search_keyword:
        customer_records = get_customer_records_by_keyword(search_keyword)
        if not customer_records:
            flash(f"ไม่พบข้อมูลลูกค้าสำหรับ '{search_keyword}'", "info")
        else:
            flash(f"พบ {len(customer_records)} รายการสำหรับ '{search_keyword}'", "success")
    else:
        # === ส่วนที่ต้องแก้ไข: ทำให้แสดง 'รอดำเนินการ' เป็นค่าเริ่มต้น ===
        customer_records = get_customer_records_by_status("รอดำเนินการ")
        display_title = "ข้อมูลลูกค้า: รอดำเนินการ (ค่าเริ่มต้น)"
        if not customer_records:
            flash("ไม่พบข้อมูลลูกค้าที่มีสถานะ 'รอดำเนินการ' ในระบบ", "info")
        else:
            flash(f"แสดงข้อมูลลูกค้า {len(customer_records)} รายการที่มีสถานะ 'รอดำเนินการ' (ค่าเริ่มต้น)", "info")
        # ================================================================

    # --- ส่วน DEBUGGING ที่เพิ่มเข้าไป ---
    # print(f"DEBUG: search_customer_data - Final customer_records before rendering. Contains {len(customer_records)} records. First record (if any): {customer_records[0] if customer_records else 'N/A'}") # Commented out
    
    # print(f"DEBUG: customer_records list contains {len(customer_records)} records.") # Commented out
    # if customer_records:
    #     print(f"DEBUG: First record in list: {customer_records[0]}")
    #     if 'row_index' in customer_records[0]:
    #         print(f"DEBUG: First record HAS 'row_index': {customer_records[0]['row_index']}")
    #     else:
    #         print("DEBUG: First record DOES NOT HAVE 'row_index'. THIS IS THE PROBLEM.")
    # --- สิ้นสุดส่วน DEBUGGING ---

    return render_template(
        'search_data.html',
        customer_records=customer_records,
        search_keyword=search_keyword,
        username=logged_in_user,
        display_title=display_title # Pass the dynamic title
    )

@app.route('/edit_customer_data/<int:row_index>', methods=['GET', 'POST'])
def edit_customer_data(row_index):
    # ... (code for edit_customer_data remains the same) ...
    """
    Handles editing of a specific customer record.
    - GET request: Displays the pre-filled edit form.
    - POST request: Processes the updated customer data and new images.
    Requires user to be logged in.
    """
    if 'username' not in session:
        flash('กรุณาเข้าสู่ระบบก่อน', 'error')
        return redirect(url_for('login'))

    logged_in_user = session['username']
    customer_data = {} # Initialize as empty, will be populated below

    worksheet = get_customer_data_worksheet() # ใช้ get_customer_data_worksheet() ที่ถูกแก้ไขแล้ว
    if not worksheet:
        flash('ไม่สามารถเข้าถึง Google Sheet สำหรับแก้ไขข้อมูลลูกค้าได้', 'error')
        return redirect(url_for('search_customer_data'))

    # --- Fetch current customer data for both GET and POST requests ---
    # This ensures customer_data is always populated with the latest from the sheet
    try:
        row_values = worksheet.row_values(row_index)
        if row_values:
            customer_data = dict(zip(CUSTOMER_DATA_WORKSHEET_HEADERS, row_values))
            # Store original image URLs for display and potential deletion
            if 'Image URLs' in customer_data and customer_data['Image URLs'] != '-':
                customer_data['existing_image_urls'] = customer_data['Image URLs'].split(', ')
            else:
                customer_data['existing_image_urls'] = []
        else:
            flash('ไม่พบข้อมูลลูกค้าในแถวที่ระบุ', 'error')
            return redirect(url_for('search_customer_data'))
    except Exception as e:
        flash(f'เกิดข้อผิดพลาดในการดึงข้อมูลลูกค้าเพื่อแก้ไข: {e}', 'error')
        print(f"Error fetching row {row_index} for edit: {e}")
        return redirect(url_for('search_customer_data'))
    # --- End of data fetching for GET/POST ---

    if request.method == 'POST':
        # Get updated text data from the form
        updated_data = {
            # Preserve original Timestamp if not updated by form, or use current time if it's new (unlikely for edit)
            'Timestamp': customer_data.get('Timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
            'ชื่อ': request.form.get('customer_name', '') or '-',
            'นามสกุล': request.form.get('last_name', '') or '-',
            'เลขบัตรประชาชน': request.form.get('id_card_number', '') or '-',
            'เบอร์มือถือ': request.form.get('mobile_phone_number', '') or '-',
            'จดทะเบียน': request.form.get('registered', '') or '-',
            'ชื่อกิจการ': request.form.get('business_name', '') or '-',
            'ประเภทธุรกิจ': request.form.get('business_type', '') or '-',
            'ที่อยู่จดทะเบียน': request.form.get('registered_address', '') or '-',
            'สถานะ': request.form.get('status', '') or '-',
            'วงเงินที่ต้องการ': request.form.get('desired_credit_limit', '') or '-',
            'วงเงินที่อนุมัติ': request.form.get('approved_credit_limit', '') or '-',
            'เคยขอเข้ามาในเครือหรือยัง': request.form.get('applied_before', '') or '-',
            'เช็ค': request.form.get('check', '') or '-',
            'ขอเข้ามาทางไหน': request.form.get('how_applied', '') or '-',
            'LINE ID': request.form.get('line_id', '') or '-',
            'หักดอกหัวท้าย': request.form.get('upfront_interest', '') or '-',
            'ค่าดำเนินการ': request.form.get('processing_fee', '') or '-',
            'วันที่ขอเข้ามา': request.form.get('application_date', '') or '-',
            'ลิงค์โลเคชั่นบ้าน': request.form.get('home_location_link', '') or '-',
            'ลิงค์โลเคชั่นที่ทำงาน': request.form.get('work_location_link', '') or '-',
            'หมายเหตุ': request.form.get('remarks', '') or '-',
        }

        # Handle existing image URLs (those not marked for deletion)
        # current_image_urls is now available from the initial data fetch
        current_image_urls = customer_data.get('existing_image_urls', []) # Use the already parsed list

        # Get image URLs that were NOT removed via the form (hidden input)
        kept_image_urls_str = request.form.get('kept_image_urls', '')
        kept_image_urls = [url.strip() for url in kept_image_urls_str.split(',')] if kept_image_urls_str else []
        
        # Determine which images were actually deleted by comparing current_image_urls with kept_image_urls
        deleted_image_urls = [url for url in current_image_urls if url not in kept_image_urls]

        # Delete images from Cloudinary that were marked for deletion
        for url_to_delete in deleted_image_urls:
            delete_image_from_cloudinary(url_to_delete)

        # Handle new image uploads
        new_image_urls = []
        if 'new_customer_images' in request.files:
            files = request.files.getlist('new_customer_images')
            for new_image in files:
                if new_image and new_image.filename:
                    url = upload_image_to_cloudinary(new_image.stream, new_image.filename)
                    if url:
                        new_image_urls.append(url)
        
        # Combine kept existing images with newly uploaded images
        final_image_urls = kept_image_urls + new_image_urls
        updated_data['Image URLs'] = ', '.join(final_image_urls) if final_image_urls else '-'

        # Ensure 'Logged In User' is not changed (preserve original from fetched customer_data)
        updated_data['Logged In User'] = customer_data.get('Logged In User', logged_in_user)

        try:
            # Prepare the row data in the correct order for gspread update
            row_to_update = [updated_data.get(header, '-') for header in CUSTOMER_DATA_WORKSHEET_HEADERS]
            worksheet.update(f'A{row_index}', [row_to_update])
            flash('บันทึกการแก้ไขข้อมูลลูกค้าเรียบร้อยแล้ว!', 'success')
            return redirect(url_for('search_customer_data')) # Redirect back to search results
        except Exception as e:
            flash(f'เกิดข้อผิดพลาดในการบันทึกการแก้ไขข้อมูล: {e}', 'error')
            print(f"Error updating row {row_index} in Google Sheet: {e}")
    
    # For GET request, or if POST fails before redirect, render the template
    return render_template('edit_customer_data.html', 
                           username=logged_in_user, 
                           customer_data=customer_data, 
                           row_index=row_index)


# NEW: Route for the Loan Management page - Modified to fetch loan_records
@app.route('/loan_management', methods=['GET'])
def loan_management():
    """
    Displays the loan management dashboard with all loan records.
    Requires user to be logged in.
    """
    if 'username' not in session:
        flash('กรุณาเข้าสู่ระบบก่อน', 'error')
        return redirect(url_for('login'))
    
    logged_in_user = session['username']
    
    # Fetch all loan records using the new helper function
    loan_records = get_all_loan_records() 
    
    # Optional: You can add flash messages here based on if records are found
    if not loan_records:
        flash('ไม่พบรายการเงินกู้ในระบบ', 'info')
    else:
        flash(f'พบ {len(loan_records)} รายการเงินกู้', 'success')

    return render_template('loan_management.html', 
                           username=logged_in_user,
                           loan_records=loan_records, # ส่งข้อมูลเงินกู้ที่ดึงมาแล้วไปที่เทมเพลต
                           loan_headers=LOAN_TRANSACTIONS_WORKSHEET_HEADERS) # ส่ง headers ไปด้วยเพื่อใช้แสดงในตาราง


# --- Main execution block ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)