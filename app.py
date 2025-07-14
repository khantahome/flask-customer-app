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
SPREADSHEET_NAME = 'data1' # Main spreadsheet containing all data

# User Login Sheet
USER_LOGIN_SPREADSHEET_NAME = 'UserLoginData'
USER_LOGIN_WORKSHEET_NAME = 'users'

# Original Customer Records Sheet (uses เลขบัตรประชาชน)
WORKSHEET_NAME = 'customer_records' 
CUSTOMER_DATA_WORKSHEET_HEADERS = [
    'Timestamp', 'ชื่อ', 'นามสกุล', 'เลขบัตรประชาชน', 'เบอร์มือถือ',
    'จดทะเบียน', 'ชื่อกิจการ', 'ประเภทธุรกิจ', 'ที่อยู่จดทะเบียน', 'สถานะ',
    'วงเงินที่ต้องการ', 'วงเงินที่อนุมัติ', 'เคยขอเข้ามาในเครือหรือยัง', 'เช็ค',
    'ขอเข้ามาทางไหน', 'LINE ID', 'หักดอกหัวท้าย', 'ค่าดำเนินการ',
    'วันที่ขอเข้ามา', 'ลิงค์โลเคชั่นบ้าน', 'ลิงค์โลเคชั่นที่ทำงาน', 'หมายเหตุ',
    'Image URLs',
    'Logged In User'
]

# NEW: Worksheet for auto-incrementing customer IDs (for loan customers)
CUSTOMER_ID_WORKSHEET_NAME = 'loan_customer_id_counter' 

# NEW: Worksheet for loan-specific customer records (uses รหัสลูกค้า)
LOAN_CUSTOMER_RECORDS_WORKSHEET_NAME = 'Loan_Customers'
LOAN_CUSTOMER_DATA_WORKSHEET_HEADERS = ['รหัสลูกค้า', 'ชื่อ', 'นามสกุล'] # Headers for the new loan customer sheet

# UPDATED: Define headers for the Loan Transactions worksheet
LOAN_TRANSACTIONS_WORKSHEET_NAME = os.environ.get('LOAN_TRANSACTIONS_WORKSHEET_NAME', 'Loan_Transactions')
LOAN_TRANSACTIONS_WORKSHEET_HEADERS = [
    'Timestamp', 'รหัสเงินกู้', 'รหัสลูกค้า', 'ชื่อลูกค้า', 'นามสกุลลูกค้า', # Changed from เลขบัตรประชาชนลูกค้า
    'วงเงินกู้', 'ดอกเบี้ย (%)', 'วันที่เริ่มกู้',
    'หักดอกหัวท้าย', 'ยอดเงินต้นที่ต้องคืน',
    'ค่าดำเนินการ', 'ยอดที่ต้องชำระรายวัน', 'ยอดชำระแล้ว', 'ยอดค้างชำระ',
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


# --- Helper Functions for Google Sheets (Moved to top) ---

def get_worksheet(spreadsheet_name, worksheet_name, headers=None):
    """Helper to get a specific worksheet, creating it and setting headers if needed."""
    if not GSPREAD_CLIENT:
        print(f"Gspread client not initialized. Cannot access worksheet '{worksheet_name}'.")
        return None
    try:
        spreadsheet = GSPREAD_CLIENT.open(spreadsheet_name)
        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
            if headers:
                existing_headers = worksheet.row_values(1)
                if not existing_headers or existing_headers != headers:
                    print(f"Warning: Worksheet '{worksheet_name}' headers do not match expected. Updating headers.")
                    worksheet.update('A1', [headers])
                    print(f"Worksheet '{worksheet_name}' headers updated.")
            return worksheet
        except gspread.exceptions.WorksheetNotFound:
            print(f"Worksheet '{worksheet_name}' not found. Creating it...")
            worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows="100", cols=str(len(headers) if headers else 20))
            if headers:
                worksheet.append_row(headers)
            print(f"Worksheet '{worksheet_name}' created with headers.")
            return worksheet
    except Exception as e:
        print(f"Error accessing/creating worksheet '{worksheet_name}': {e}")
        return None

def get_user_worksheet():
    return get_worksheet(USER_LOGIN_SPREADSHEET_NAME, USER_LOGIN_WORKSHEET_NAME)

def get_customer_data_worksheet():
    """Returns the original customer_records worksheet."""
    return get_worksheet(SPREADSHEET_NAME, WORKSHEET_NAME, CUSTOMER_DATA_WORKSHEET_HEADERS)

def get_loan_worksheet():
    """Returns the Loan_Transactions worksheet."""
    # เพิ่ม print statement ตรงนี้: เพื่อดูว่าพยายามเข้าถึงชีทชื่ออะไร
    print(f"DEBUG: Attempting to get loan worksheet: Spreadsheet='{SPREADSHEET_NAME}', Worksheet='{LOAN_TRANSACTIONS_WORKSHEET_NAME}'")
    
    worksheet = get_worksheet(SPREADSHEET_NAME, LOAN_TRANSACTIONS_WORKSHEET_NAME, LOAN_TRANSACTIONS_WORKSHEET_HEADERS)
    
    # เพิ่ม print statement ตรงนี้: เพื่อดูว่า get_worksheet คืนค่าเป็น None หรือไม่
    if not worksheet:
        print("DEBUG: get_loan_worksheet returned None.")
    return worksheet

def get_customer_id_counter_worksheet():
    """NEW: Gets or creates the worksheet for loan customer ID counter."""
    # This worksheet will just have one cell (A1) storing the last ID.
    # No specific headers needed.
    return get_worksheet(SPREADSHEET_NAME, CUSTOMER_ID_WORKSHEET_NAME)

def get_loan_customer_data_worksheet():
    """NEW: Returns the Loan_Customers worksheet."""
    return get_worksheet(SPREADSHEET_NAME, LOAN_CUSTOMER_RECORDS_WORKSHEET_NAME, LOAN_CUSTOMER_DATA_WORKSHEET_HEADERS)


def get_all_customer_records():
    """
    Retrieves all customer records from the original customer_records worksheet.
    Each record will be a dictionary, now including its row_index.
    """
    worksheet = get_customer_data_worksheet()
    if not worksheet:
        return []
    try:
        all_data = worksheet.get_all_values()
        if not all_data or len(all_data) < 2:
            print("DEBUG: Google Sheet 'customer_records' is empty or only has headers.")
            return []

        headers = all_data[0]
        data_rows = all_data[1:]
        
        customer_records = []
        # เริ่มต้นการวนลูปด้วย index (i) เพื่อใช้ในการคำนวณ row_index
        for i, row in enumerate(data_rows): # <--- แก้ไขตรงนี้: เพิ่ม enumerate(data_rows)
            record = {}
            for j, header in enumerate(headers):
                if j < len(row):
                    record[header] = row[j]
                else:
                    record[header] = ''
            
            # เพิ่มบรรทัดนี้: กำหนด row_index ให้กับแต่ละ record
            # i คือ index ที่เริ่มจาก 0 สำหรับ data_rows (ซึ่งคือแถวที่ 2 ของชีทจริง)
            # ดังนั้น row_index ใน Google Sheet คือ i + 2
            record['row_index'] = i + 2 
            
            customer_records.append(record)
        return customer_records
    except Exception as e:
        print(f"ERROR in get_all_customer_records (original customer_records): {e}")
        return []


def get_all_loan_customer_records():
    """
    NEW: Retrieves all loan-specific customer records from the Loan_Customers worksheet.
    Each record will be a dictionary.
    """
    worksheet = get_loan_customer_data_worksheet()
    if not worksheet:
        return []
    try:
        all_data = worksheet.get_all_values()
        if not all_data or len(all_data) < 2:
            print("DEBUG: Google Sheet 'Loan_Customers' is empty or only has headers.")
            return []

        headers = all_data[0]
        data_rows = all_data[1:]
        
        loan_customer_records = []
        for row in data_rows:
            record = {}
            for j, header in enumerate(headers):
                if j < len(row):
                    record[header] = row[j]
                else:
                    record[header] = ''
            loan_customer_records.append(record)
        return loan_customer_records
    except Exception as e:
        print(f"ERROR in get_all_loan_customer_records: {e}")
        return []


def generate_next_customer_id():
    """
    NEW: Generates the next sequential customer ID for loan customers (e.g., 000001, 000002).
    Reads the last ID from a dedicated counter sheet, increments it, and updates the sheet.
    """
    worksheet = get_customer_id_counter_worksheet()
    if not worksheet:
        print("ERROR: Could not access customer ID counter worksheet.")
        return None

    try:
        # Try to read the last ID from cell A1
        last_id_str = worksheet.acell('A1').value
        if last_id_str:
            try:
                last_id_num = int(last_id_str)
            except ValueError:
                print(f"Warning: Invalid customer ID format '{last_id_str}' in counter sheet. Resetting to 0.")
                last_id_num = 0
        else:
            last_id_num = 0 # No ID found, start from 0

        next_id_num = last_id_num + 1
        next_id_str = f"{next_id_num:06d}" # Format as 000001, 000002, etc.

        # Update the worksheet with the new last ID
        worksheet.update('A1', next_id_str)
        print(f"Generated new loan customer ID: {next_id_str}")
        return next_id_str
    except Exception as e:
        print(f"ERROR generating next loan customer ID: {e}")
        return None

def load_users():
    """
    Loads user IDs and passwords from the specified Google Sheet (UserLoginData).
    It expects the sheet to have columns named 'id' and 'pass'.
    Returns a dictionary where keys are user IDs and values are their passwords.
    Returns an empty dictionary if there's an error or columns are missing.
    """
    if not GSPREAD_CLIENT:
        print("Gspread client not initialized. Cannot load users.")
        return {}
    try:
        sheet = GSPREAD_CLIENT.open(USER_LOGIN_SPREADSHEET_NAME).worksheet(USER_LOGIN_WORKSHEET_NAME)
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


def get_customer_records_by_status(status):
    """
    Retrieves customer records filtered by status from the original customer_records sheet.
    """
    print(f"DEBUG: get_customer_records_by_status called with status: {status}")
    all_records = get_all_customer_records()
    filtered_records = [record for record in all_records if record.get('สถานะ') == status]
    print(f"DEBUG: get_customer_records_by_status returning {len(filtered_records)} records for status '{status}'")
    return filtered_records

def get_customer_records_by_keyword(keyword):
    """
    Retrieves customer records filtered by keyword across all values from the original customer_records sheet.
    """
    print(f"DEBUG: get_customer_records_by_keyword called with keyword: {keyword}")
    all_records = get_all_customer_records()
    filtered_records = [
        record for record in all_records
        if any(keyword.lower() in str(value).lower() for value in record.values())
    ]
    print(f"DEBUG: get_customer_records_by_keyword returning {len(filtered_records)} records for keyword '{keyword}'")
    return filtered_records


# --- Route for Adding New Loan Record ---
@app.route('/add_loan_record', methods=['POST'])
def add_loan_record():
    """
    Handles form submission for adding a new loan record to the Google Sheet.
    This now also handles adding a new loan customer if their ID is not provided.
    """
    if 'username' not in session:
        flash('กรุณาเข้าสู่ระบบก่อน', 'error')
        return redirect(url_for('login'))

    logged_in_user = session['username']

    if request.method == 'POST':
        try:
            # Get data from the form
            customer_loan_id = request.form.get('customer_new_id', '').strip()
            new_customer_name = request.form.get('new_customer_name', '').strip()
            new_customer_surname = request.form.get('new_customer_surname', '').strip()

            loan_amount = float(request.form['loan_amount'])
            interest_rate = float(request.form['interest_rate'])
            start_date_str = request.form['start_date']
            processing_fee = float(request.form['processing_fee'])
            loan_note = request.form.get('loan_note', '').strip()

            customer_name_for_loan = ""
            customer_surname_for_loan = ""
            final_customer_id = ""

            # Logic to determine if it's an existing loan customer or a new one
            if customer_loan_id: # User selected an existing customer ID
                loan_customer_worksheet = get_loan_customer_data_worksheet()
                if not loan_customer_worksheet:
                    flash("ไม่สามารถเชื่อมต่อกับชีทข้อมูลลูกค้าเงินกู้ได้", 'error')
                    return redirect(url_for('loan_management'))

                all_loan_customers_data = get_all_loan_customer_records()
                found_loan_customer = next((rec for rec in all_loan_customers_data if rec.get('รหัสลูกค้า') == customer_loan_id), None)

                if found_loan_customer:
                    final_customer_id = customer_loan_id
                    customer_name_for_loan = found_loan_customer.get('ชื่อ', '')
                    customer_surname_for_loan = found_loan_customer.get('นามสกุล', '')
                else:
                    flash(f"ไม่พบข้อมูลลูกค้าเงินกู้สำหรับรหัสลูกค้า {customer_loan_id} ในระบบ กรุณาตรวจสอบรหัสหรือเพิ่มลูกค้าใหม่", 'warning')
                    return redirect(url_for('loan_management'))

            elif new_customer_name and new_customer_surname: # User provided new customer name and surname
                # Generate a new customer ID for this loan customer
                generated_id = generate_next_customer_id()
                if not generated_id:
                    flash('ไม่สามารถสร้างรหัสลูกค้าใหม่ได้ โปรดลองอีกครั้ง', 'error')
                    return redirect(url_for('loan_management'))
                
                final_customer_id = generated_id
                customer_name_for_loan = new_customer_name
                customer_surname_for_loan = new_customer_surname

                # Save this new loan customer to the Loan_Customers sheet
                loan_customer_worksheet = get_loan_customer_data_worksheet()
                if loan_customer_worksheet:
                    new_loan_customer_row = {
                        'รหัสลูกค้า': final_customer_id,
                        'ชื่อ': customer_name_for_loan,
                        'นามสกุล': customer_surname_for_loan
                    }
                    row_to_append_loan_customer = [new_loan_customer_row.get(header, '-') for header in LOAN_CUSTOMER_DATA_WORKSHEET_HEADERS]
                    loan_customer_worksheet.append_row(row_to_append_loan_customer)
                    flash(f'เพิ่มลูกค้าเงินกู้ใหม่ (รหัส: {final_customer_id}) เรียบร้อยแล้ว!', 'info')
                else:
                    flash('ไม่สามารถเข้าถึง Worksheet ลูกค้าเงินกู้เพื่อบันทึกข้อมูลลูกค้าใหม่ได้', 'error')
                    return redirect(url_for('loan_management'))

            else: # Neither existing ID nor new name/surname provided
                flash('กรุณาเลือกรหัสลูกค้าที่มีอยู่ หรือกรอกชื่อและนามสกุลลูกค้าใหม่', 'error')
                return redirect(url_for('loan_management'))

            # CALCULATIONS
            # 1. หักดอกหัวท้าย (Upfront Interest Deduction)
            # Formula: วงเงินกู้ * ดอกเบี้ย / 100
            upfront_interest_deduction = round(loan_amount * interest_rate / 100, 2)

            # 2. ยอดเงินต้นที่ต้องคืน (Principal to Return)
            # Formula: วงเงินกู้ - หักดอกหัวท้าย
            principal_to_return = round(loan_amount - upfront_interest_deduction, 2)
            
            # 3. ยอดที่ต้องชำระรายวัน (Daily Payment) - Assuming 180 days contract duration for now
            CONTRACT_DAYS = 180 
            if CONTRACT_DAYS == 0: # Avoid division by zero
                daily_payment = 0
            else:
                daily_payment = round((principal_to_return + processing_fee) / CONTRACT_DAYS, 2)

            # Prepare the data row for Loan Transactions sheet
            row_data = {
                'Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'รหัสเงินกู้': f"L{datetime.now().strftime('%Y%m%d%H%M%S')}", # Generate a simple loan ID
                'รหัสลูกค้า': final_customer_id, # Use the determined customer ID
                'ชื่อลูกค้า': customer_name_for_loan,
                'นามสกุลลูกค้า': customer_surname_for_loan,
                'วงเงินกู้': loan_amount,
                'ดอกเบี้ย (%)': interest_rate,
                'วันที่เริ่มกู้': start_date_str,
                'หักดอกหัวท้าย': upfront_interest_deduction,
                'ยอดเงินต้นที่ต้องคืน': principal_to_return,
                'ค่าดำเนินการ': processing_fee,
                'ยอดที่ต้องชำระรายวัน': daily_payment,
                'ยอดชำระแล้ว': 0, # Initial value is 0
                'ยอดค้างชำระ': principal_to_return, # Initially, outstanding is principal to return
                'สถานะเงินกู้': 'รออนุมัติ/ใหม่', # Default status
                'หมายเหตุเงินกู้': loan_note,
                'ผู้บันทึก': logged_in_user
            }

            # Convert dictionary to list in the correct order of headers
            row_to_append = [row_data.get(header, '-') for header in LOAN_TRANSACTIONS_WORKSHEET_HEADERS]

            # Get the Loan Transactions worksheet
            loan_worksheet = get_loan_worksheet()
            if loan_worksheet:
                loan_worksheet.append_row(row_to_append)
                flash('บันทึกรายการเงินกู้ใหม่เรียบร้อยแล้ว!', 'success')
            else:
                flash('ไม่สามารถเข้าถึง Worksheet เงินกู้ได้', 'error')

        except ValueError as e:
            flash(f'ข้อมูลที่กรอกไม่ถูกต้อง กรุณาตรวจสอบรูปแบบตัวเลขและวันที่: {e}', 'error')
        except KeyError as e:
            flash(f'ข้อมูลฟอร์มไม่ครบถ้วน: {e}', 'error')
        except Exception as e:
            flash(f'เกิดข้อผิดพลาดในการบันทึกรายการเงินกู้: {e}', 'error')
            print(f"Error adding loan record: {e}")

    return redirect(url_for('loan_management')) # Redirect back to the loan management page

def upload_image_to_cloudinary(file_stream, original_filename):
    """
    Uploads an image file stream to Cloudinary.
    Returns the URL of the uploaded file, or None if upload fails.
    """
    try:
        # Upload the file directly from the stream
        # The 'folder' parameter allows you to organize images in Cloudinary
        upload_result = cloudinary.uploader.upload(
            file_stream,
            folder="customer_app_images"
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
    """
    Deletes an image from Cloudinary using its URL.
    """
    if not image_url:
        return True # No URL to delete, consider it success

    try:
        parts = image_url.split('/')
        if len(parts) < 2:
            print(f"Invalid Cloudinary URL for deletion: {image_url}")
            return False

        public_id_with_folder = "/".join(parts[-2:]).split('.')[0] 
        
        if "customer_app_images" in public_id_with_folder:
            public_id_to_delete = public_id_with_folder
        else:
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
    """
    Handles user login functionality.
    """
    error = None
    users = load_users() 

    if request.method == 'POST':
        username = request.form.get('username') 
        password = request.form.get('password') 

        if username in users and users[username] == password:
            session['username'] = username
            return redirect(url_for('dashboard'))
        else:
            error = "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"
    return render_template('login.html', error=error)

@app.route('/dashboard')
def dashboard():
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
    """
    Logs out the user by clearing the session.
    """
    session.pop('username', None)
    flash('คุณได้ออกจากระบบแล้ว', 'success')
    return redirect(url_for('login'))

@app.route('/enter_customer_data', methods=['GET', 'POST'])
def enter_customer_data():
    """
    Handles customer data entry for original customer_records sheet.
    - GET request: Displays the data entry form.
    - POST request: Processes the submitted customer data and images.
    Requires user to be logged in.
    """
    if 'username' not in session:
        flash('กรุณาเข้าสู่ระบบก่อน', 'error')
        return redirect(url_for('login'))

    logged_in_user = session['username']

    if request.method == 'POST':
        try:
            # Get text data from the form using .get() with a default empty string
            # Then replace empty strings with "-"
            customer_name = request.form.get('customer_name', '') or '-'
            last_name = request.form.get('last_name', '') or '-'
            id_card_number = request.form.get('id_card_number', '') or '-' # This still uses ID card
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
            application_date = request.form.get('application_date', '') or '-' 
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
            
            # Join all image URLs into a single comma-separated string, or "-" if no images
            image_urls_str = ', '.join(image_urls) if image_urls else '-'

            # Get the customer data worksheet
            worksheet = get_customer_data_worksheet()
            if worksheet:
                try:
                    # Prepare the data row, ensuring order matches CUSTOMER_DATA_WORKSHEET_HEADERS exactly
                    row_data = {
                        'Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'ชื่อ': customer_name,
                        'นามสกุล': last_name,
                        'เลขบัตรประชาชน': id_card_number, # Original ID card field
                        'เบอร์มือถือ': mobile_phone_number,
                        'จดทะเบียน': registered,
                        'ชื่อกิจการ': business_name,
                        'ประเภทธุรกิจ': business_type,
                        'ที่อยู่จดทะเบียน': registered_address,
                        'สถานะ': status,
                        'วงเงินที่ต้องการ': desired_credit_limit,
                        'วงเงินที่อนุมัติ': approved_credit_limit,
                        'เคยขอเข้ามาในเครือหรือยัง': applied_before,
                        'เช็ค': check,
                        'ขอเข้ามาทางไหน': how_applied,
                        'LINE ID': line_id,
                        'หักดอกหัวท้าย': upfront_interest,
                        'ค่าดำเนินการ': processing_fee,
                        'วันที่ขอเข้ามา': application_date,
                        'ลิงค์โลเคชั่นบ้าน': home_location_link,
                        'ลิงค์โลเคชั่นที่ทำงาน': work_location_link,
                        'หมายเหตุ': remarks,
                        'Image URLs': image_urls_str,
                        'Logged In User': logged_in_user
                    }
                    
                    row_to_append = [row_data.get(header, '-') for header in CUSTOMER_DATA_WORKSHEET_HEADERS]
                    worksheet.append_row(row_to_append)
                    flash('บันทึกข้อมูลลูกค้าเรียบร้อยแล้ว!', 'success')
                    return redirect(url_for('enter_customer_data')) # Redirect to clear form
                except Exception as e:
                    flash(f'เกิดข้อผิดพลาดในการบันทึกข้อมูล: {e}', 'error')
                    print(f"Error saving data to Google Sheet: {e}")
            else:
                flash('ไม่สามารถเข้าถึง Google Sheet สำหรับบันทึกข้อมูลลูกค้าได้', 'error')
                print("Error: Customer data worksheet not available.")
        except Exception as e:
            flash(f'เกิดข้อผิดพลาดในการประมวลผลข้อมูลลูกค้า: {e}', 'error')
            print(f"Error processing customer data form: {e}")

    return render_template('data_entry.html', username=logged_in_user)

@app.route('/search_customer_data', methods=['GET'])
def search_customer_data():
    """
    Handles searching for customer data from the original customer_records sheet.
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
    display_title = "ค้นหาข้อมูลลูกค้า"

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
        customer_records = get_all_customer_records() # Show all customers by default
        display_title = "ข้อมูลลูกค้าทั้งหมด"
        if not customer_records:
            flash("ไม่พบข้อมูลลูกค้าในระบบ", "info")
        else:
            flash(f"แสดงข้อมูลลูกค้าทั้งหมด {len(customer_records)} รายการ", "info")


    return render_template(
        'search_data.html',
        customer_records=customer_records,
        search_keyword=search_keyword,
        username=logged_in_user,
        display_title=display_title
    )

@app.route('/edit_customer_data/<int:row_index>', methods=['GET', 'POST']) # Changed back to int:row_index for original customer data
def edit_customer_data(row_index):
    """
    Handles editing of a specific customer record from the original customer_records sheet.
    - GET request: Displays the pre-filled edit form.
    - POST request: Processes the updated customer data and new images.
    Requires user to be logged in.
    """
    if 'username' not in session:
        flash('กรุณาเข้าสู่ระบบก่อน', 'error')
        return redirect(url_for('login'))

    logged_in_user = session['username']
    customer_data = {}

    worksheet = get_customer_data_worksheet()
    if not worksheet:
        flash('ไม่สามารถเข้าถึง Google Sheet สำหรับแก้ไขข้อมูลลูกค้าได้', 'error')
        return redirect(url_for('search_customer_data'))

    try:
        row_values = worksheet.row_values(row_index)
        if row_values:
            customer_data = dict(zip(CUSTOMER_DATA_WORKSHEET_HEADERS, row_values))
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

    if request.method == 'POST':
        # Get updated text data from the form
        updated_data = {
            'Timestamp': customer_data.get('Timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
            'ชื่อ': request.form.get('customer_name', '') or '-',
            'นามสกุล': request.form.get('last_name', '') or '-',
            'เลขบัตรประชาชน': request.form.get('id_card_number', '') or '-', # Still uses ID card
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

        current_image_urls = customer_data.get('existing_image_urls', [])

        kept_image_urls_str = request.form.get('kept_image_urls', '')
        kept_image_urls = [url.strip() for url in kept_image_urls_str.split(',')] if kept_image_urls_str else []
        
        deleted_image_urls = [url for url in current_image_urls if url not in kept_image_urls]

        for url_to_delete in deleted_image_urls:
            delete_image_from_cloudinary(url_to_delete)

        new_image_urls = []
        if 'new_customer_images' in request.files:
            files = request.files.getlist('new_customer_images')
            for new_image in files:
                if new_image and new_image.filename:
                    url = upload_image_to_cloudinary(new_image.stream, new_image.filename)
                    if url:
                        new_image_urls.append(url)
        
        final_image_urls = kept_image_urls + new_image_urls
        updated_data['Image URLs'] = ', '.join(final_image_urls) if final_image_urls else '-'

        updated_data['Logged In User'] = customer_data.get('Logged In User', logged_in_user)

        try:
            # Prepare the row to update in the correct order of headers
            row_to_update = [updated_data.get(header, '-') for header in CUSTOMER_DATA_WORKSHEET_HEADERS]
            worksheet.update(f'A{row_index}', [row_to_update]) # Use the found row_index
            flash('บันทึกการแก้ไขข้อมูลลูกค้าเรียบร้อยแล้ว!', 'success')
            return redirect(url_for('search_customer_data'))
        except Exception as e:
            flash(f'เกิดข้อผิดพลาดในการบันทึกการแก้ไขข้อมูล: {e}', 'error')
            print(f"Error updating row {row_index} in Google Sheet: {e}")
    
    return render_template('edit_customer_data.html', 
                           username=logged_in_user, 
                           customer_data=customer_data, 
                           row_index=row_index) # Pass row_index back


# NEW: Route for the Loan Management page
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
    
    # Fetch all loan records
    loan_records = get_all_loan_customer_records() # <--- Error reported here
    # Fetch all loan-specific customer records to populate datalist and display names
    all_loan_customers = get_all_loan_customer_records() 
    
    if not loan_records:
        flash('ไม่พบรายการเงินกู้ในระบบ', 'info')
    else:
        flash(f'พบ {len(loan_records)} รายการเงินกู้', 'success')

    return render_template('loan_management.html', 
                           username=logged_in_user,
                           loan_records=loan_records, # Pass fetched loan data to template
                           loan_headers=LOAN_TRANSACTIONS_WORKSHEET_HEADERS, # Pass headers for table display
                           all_customers=all_loan_customers # Pass loan-specific customer data for name lookup and datalist
                           )


# --- Main execution block ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
