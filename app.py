# Import necessary modules from Flask and other libraries
from flask import Flask, render_template, request, redirect, url_for, flash, session, Response # Import Response
import gspread # Library for interacting with Google Sheets
from oauth2client.service_account import ServiceAccountCredentials # For authenticating with Google APIs
import pandas as pd # Library for data manipulation, useful for working with tabular data from Google Sheets
from pydrive.auth import GoogleAuth # For Google Drive authentication
from pydrive.drive import GoogleDrive # For interacting with Google Drive
import os # For path manipulation (e.g., getting file extension)
from datetime import datetime # For getting current timestamp
import requests # NEW: Import requests library for making HTTP requests (to fetch images)
import json
import cloudinary
import cloudinary.uploader
import cloudinary.api

# Initialize the Flask application
app = Flask(__name__)
# Set a secret key for Flask sessions (needed for flash messages and session management)
# *** สำคัญ: เปลี่ยนเป็นคีย์ลับของคุณเองเพื่อความปลอดภัย! ***
app.secret_key = os.environ.get('SECRET_KEY', 'your_super_secret_key_for_customer_app_2025_new')

# --- Configuration for Google Sheets & Drive API Access ---
# Define the scope of access for the Google Sheets and Google Drive APIs.
# 'https://www.googleapis.com/auth/drive' gives full read/write access to Google Drive files and folders.
GOOGLE_API_SCOPE = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]

# Path to your service account key file.
# Make sure 'exclusive.json' is located in the same directory as this app.py file.
SERVICE_ACCOUNT_KEY_FILE = 'exclusive.json'

# --- Google Sheets Configuration ---
# *** ส่วนนี้สำหรับข้อมูลผู้ใช้ (Login) ***
USER_LOGIN_SPREADSHEET_NAME = 'UserLoginData' # Google Sheet สำหรับ User Login
USER_LOGIN_WORKSHEET_NAME = 'users'           # Worksheet สำหรับ User Login

# *** ส่วนนี้สำหรับข้อมูลลูกค้า (Customer Records) ***
SPREADSHEET_NAME = 'data1' # Google Sheet สำหรับข้อมูลลูกค้า
WORKSHEET_NAME = 'customer_records' # Worksheet สำหรับข้อมูลลูกค้า

# Define headers for the customer data worksheet.
# This list must match the order of data you intend to save.
CUSTOMER_DATA_WORKSHEET_HEADERS = [
    'Timestamp', 'ชื่อ', 'นามสกุล', 'เลขบัตรประชาชน', 'เบอร์มือถือ',
    'จดทะเบียน', 'ชื่อกิจการ', 'ประเภทธุรกิจ', 'ที่อยู่จดทะเบียน', 'สถานะ',
    'วงเงินที่ต้องการ', 'วงเงินที่อนุมัติ', 'เคยขอเข้ามาในเครือหรือยัง', 'เช็ค',
    'ขอเข้ามาทางไหน', 'LINE ID', 'หักดอกหัวท้าย', 'ค่าดำเนินการ',
    'วันที่ขอเข้ามา', 'ลิงค์โลเคชั่นบ้าน', 'ลิงค์โลเคชั่นที่ทำงาน', 'หมายเหตุ',
    'Image URLs', # This column will store comma-separated URLs of uploaded images
    'Logged In User' # This is the LAST column for the logged-in username
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
    creds_json = None # This will store the dictionary of the service account key

    # ขั้นแรก: อ่านเนื้อหา JSON ของ Service Account Key ไม่ว่าจะมาจาก Environment Variable หรือไฟล์
    if os.environ.get('GOOGLE_SERVICE_ACCOUNT_KEY_JSON'):
        creds_json_str = os.environ.get('GOOGLE_SERVICE_ACCOUNT_KEY_JSON')
        creds_json = json.loads(creds_json_str) # แปลง string JSON เป็น Python dictionary
    else:
        # ถ้าไม่มี Environment Variable (สำหรับ Dev ในเครื่อง) ให้อ่านจากไฟล์
        # ตรวจสอบว่าไฟล์ 'exclusive.json' อยู่ในโฟลเดอร์เดียวกันกับ app.py
        with open(SERVICE_ACCOUNT_KEY_FILE, 'r') as f:
            creds_json = json.load(f)

    # ถ้า creds_json ถูกโหลดได้สำเร็จ
    if creds_json:
        # Create ServiceAccountCredentials object (used by both gspread and PyDrive)
        # ตัวแปร 'creds' นี้จะถูกใช้สำหรับทั้ง gspread และ PyDrive
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, GOOGLE_API_SCOPE)

        # 1. สำหรับ gspread: Authenticate gspread client
        GSPREAD_CLIENT = gspread.authorize(creds)

        # 2. สำหรับ PyDrive: Initialize PyDrive client
        gauth = GoogleAuth()
        # กำหนด ServiceAccountCredentials object ให้กับ gauth.credentials โดยตรง
        gauth.credentials = creds
        # (บรรทัด gauth.Authorize() อาจไม่จำเป็นสำหรับ Service Account แต่อาจช่วยได้ถ้ายังติดปัญหา)
        # gauth.Authorize() # Un-comment บรรทัดนี้ถ้ายังเจอ error เกี่ยวกับการ authenticate ของ PyDrive

        DRIVE_CLIENT = GoogleDrive(gauth)
    else:
        raise ValueError("Service Account credentials could not be loaded from environment or file.")

except Exception as e:
    print(f"CRITICAL ERROR: Google API clients failed to initialize. Error: {e}")
    GSPREAD_CLIENT = None
    DRIVE_CLIENT = None

# ... โค้ดส่วนอื่นๆ ของแอปของคุณจะอยู่ด้านล่างนี้ตามปกติ ...


# --- Helper Functions for Google Sheets ---
def get_customer_records_by_status(status_value):
    """
    Retrieves customer records where the 'สถานะ' (Status) column matches the given status_value,
    including their 1-based row index.
    """
    # Use the function that already retrieves all records with row_index
    all_records_with_index = get_all_customer_records()

    # Filter these records based on status
    filtered_records = [
        record for record in all_records_with_index
        if record.get('สถานะ') and status_value in record['สถานะ']
    ]
    return filtered_records

def get_all_customer_records():
    """
    Retrieves all customer records from the worksheet, including their 1-based row index.
    Each record will be a dictionary with an additional 'row_index' key.
    """
    worksheet = get_customer_data_worksheet()
    if not worksheet:
        return []
    try:
        # Get all data as a list of lists, including headers
        all_data = worksheet.get_all_values()
        if not all_data:
            return []

        # Assume the first row is headers
        headers = all_data[0]
        data_rows = all_data[1:] # All rows after the header

        customer_records = []
        for i, row in enumerate(data_rows):
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
            customer_records.append(record)
        return customer_records
    except Exception as e:
        print(f"Error getting all customer records with row index: {e}")
        return []
def get_customer_records_by_keyword(keyword):
    """
    Retrieves customer records that match the keyword in any relevant text column.
    """
    worksheet = get_customer_data_worksheet()
    if not worksheet:
        return []
    try:
        all_records = worksheet.get_all_records()
        if not keyword:
            return all_records # If no keyword, return all records

        # Convert keyword to lowercase for case-insensitive search
        keyword_lower = keyword.lower()

        matched_records = []
        for record in all_records:
            # Check relevant text columns for the keyword
            # You can customize which columns to search here
            searchable_columns = [
                'ชื่อ', 'นามสกุล', 'เลขบัตรประชาชน', 'เบอร์มือถือ',
                'จดทะเบียน', 'ชื่อกิจการ', 'ประเภทธุรกิจ', 'ที่อยู่จดทะเบียน',
                'สถานะ', 'LINE ID', 'หมายเหตุ'
            ]
            for col in searchable_columns:
                # Ensure the column exists and its value is not None, then convert to string and lower
                if col in record and record[col] is not None and keyword_lower in str(record[col]).lower():
                    matched_records.append(record)
                    break # Move to the next record once a match is found
        return matched_records
    except Exception as e:
        print(f"Error searching customer data: {e}")
        return []

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
        # ใช้ USER_LOGIN_SPREADSHEET_NAME และ USER_LOGIN_WORKSHEET_NAME สำหรับการโหลดผู้ใช้
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

def get_customer_data_worksheet():
    """
    Gets the customer data worksheet from the 'data1' Google Sheet.
    Creates it if it doesn't exist. Also ensures the header row is present and matches the defined headers.
    """
    if not GSPREAD_CLIENT:
        print("Gspread client not initialized. Cannot access customer data worksheet.")
        return None
    try:
        # ใช้ SPREADSHEET_NAME (ซึ่งคือ 'data1') สำหรับข้อมูลลูกค้า
        spreadsheet = GSPREAD_CLIENT.open(SPREADSHEET_NAME)
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

# --- Helper Functions for Google Drive ---





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

# Route for the login page.
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
            session['username'] = username # Store username in session
            return redirect(url_for('dashboard')) # Redirect to dashboard without username in URL
        else:
            error = "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"
    return render_template('login.html', error=error)

# Route for the dashboard page, which serves as the main menu.
@app.route('/dashboard') # No username in URL anymore, retrieve from session
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

# Route for logging out
@app.route('/logout')
def logout():
    """
    Logs out the user by clearing the session.
    """
    session.pop('username', None) # Remove username from session
    flash('คุณได้ออกจากระบบแล้ว', 'success')
    return redirect(url_for('login'))

# Route for the customer data entry page
@app.route('/enter_customer_data', methods=['GET', 'POST'])
def enter_customer_data():
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
        worksheet = get_customer_data_worksheet()
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

# Route for the customer data search page
@app.route('/search_customer_data', methods=['GET'])
def search_customer_data():
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
    status_filter = request.args.get('status_filter', '').strip() # NEW: Get status filter

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
        # If no search_keyword and no status_filter, display all or none depending on desired default
        # For now, let's display all if no specific filter/keyword is provided
        customer_records = get_all_customer_records()
        if not customer_records:
            flash("ไม่พบข้อมูลลูกค้าในระบบ", "info")
        else:
            flash(f"แสดงข้อมูลลูกค้าทั้งหมด {len(customer_records)} รายการ", "info")


    return render_template(
        'search_data.html',
        customer_records=customer_records,
        search_keyword=search_keyword,
        username=logged_in_user,
        display_title=display_title # Pass the dynamic title
    )

# Route for editing customer data
@app.route('/edit_customer_data/<int:row_index>', methods=['GET', 'POST'])
def edit_customer_data(row_index):
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
    customer_data = {}
    
    worksheet = get_customer_data_worksheet()
    if not worksheet:
        flash('ไม่สามารถเข้าถึง Google Sheet สำหรับแก้ไขข้อมูลลูกค้าได้', 'error')
        return redirect(url_for('search_customer_data'))

    if request.method == 'GET':
        try:
            # Get specific row values (1-based index)
            row_values = worksheet.row_values(row_index)
            if row_values:
                # Map values to dictionary using headers
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
    
    elif request.method == 'POST':
        # Get updated text data from the form
        updated_data = {
            'Timestamp': customer_data.get('Timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')), # Keep original or update
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
            # 'Logged In User' is NOT updated from form, it remains the original or is set by system
        }

        # Handle existing image URLs (those not marked for deletion)
        # Get current image URLs from the sheet first
        current_sheet_row = worksheet.row_values(row_index)
        current_image_urls_str = current_sheet_row[CUSTOMER_DATA_WORKSHEET_HEADERS.index('Image URLs')] if 'Image URLs' in CUSTOMER_DATA_WORKSHEET_HEADERS else '-'
        current_image_urls = [url.strip() for url in current_image_urls_str.split(',')] if current_image_urls_str and current_image_urls_str != '-' else []

        # Get image URLs that were NOT removed via the form (hidden input)
        kept_image_urls_str = request.form.get('kept_image_urls', '')
        kept_image_urls = [url.strip() for url in kept_image_urls_str.split(',')] if kept_image_urls_str else []
        
        # Determine which images were actually deleted by comparing current_image_urls with kept_image_urls
        deleted_image_urls = [url for url in current_image_urls if url not in kept_image_urls]

        # Delete images from Google Drive that were marked for deletion
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

        # Ensure 'Logged In User' is not changed
        # Re-fetch the original 'Logged In User' from the sheet to ensure it's preserved
        original_logged_in_user_index = CUSTOMER_DATA_WORKSHEET_HEADERS.index('Logged In User')
        original_logged_in_user = current_sheet_row[original_logged_in_user_index]
        updated_data['Logged In User'] = original_logged_in_user

        try:
            # Prepare the row data in the correct order for gspread update
            row_to_update = [updated_data.get(header, '-') for header in CUSTOMER_DATA_WORKSHEET_HEADERS]
            worksheet.update(f'A{row_index}', [row_to_update])
            flash('บันทึกการแก้ไขข้อมูลลูกค้าเรียบร้อยแล้ว!', 'success')
            return redirect(url_for('search_customer_data')) # Redirect back to search results
        except Exception as e:
            flash(f'เกิดข้อผิดพลาดในการบันทึกการแก้ไขข้อมูล: {e}', 'error')
            print(f"Error updating row {row_index} in Google Sheet: {e}")
    
    return render_template('edit_customer_data.html', 
                           username=logged_in_user, 
                           customer_data=customer_data, 
                           row_index=row_index)





# --- Main execution block ---
if __name__ == '__main__':
    # Get port from environment variable, default to 5000 for local development
    port = int(os.environ.get('PORT', 5000))
    # Run the Flask application. Disable debug mode in production.
    app.run(host='0.0.0.0', port=port, debug=False)

