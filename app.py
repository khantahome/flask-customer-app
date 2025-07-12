# Import necessary modules from Flask and other libraries
from flask import Flask, render_template, request, redirect, url_for, flash, session, Response
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd # pandas is still used in load_users
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
import os
from datetime import datetime # Removed timedelta as it's no longer used
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
# UPDATED HEADERS FOR LOAN TRANSACTIONS WORKSHEET
LOAN_TRANSACTIONS_WORKSHEET_HEADERS = [
    'Timestamp', 'ชื่อลูกค้า', 'นามสกุลลูกค้า', 'เลขบัตรประชาชนลูกค้า',
    'วงเงินกู้', 'ดอกเบี้ย (%)', 'หักดอกหัว-ท้าย (%)', 'ค่าดำเนินการ',
    'วันที่เริ่มกู้', 'ยอดเงินต้นที่ต้องชำระ', # Changed from 'ยอดที่ต้องชำระรายเดือน'
    'ยอดชำระแล้ว', 'ยอดค้างชำระ', 'สถานะเงินกู้', 'หมายเหตุเงินกู้', 'ผู้บันทึก'
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

# --- Helper functions for Google Sheets ---

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

def get_customer_data_worksheet():
    """
    Gets the customer data worksheet from the 'data1' Google Sheet.
    Creates it if it doesn't exist. Also ensures the header row is present and matches the defined headers.
    """
    if not GSPREAD_CLIENT:
        print("Gspread client not initialized. Cannot access customer data worksheet.")
        return None
    try:
        spreadsheet = GSPREAD_CLIENT.open(SPREADSHEET_NAME)
        try:
            worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
            existing_headers = worksheet.row_values(1)
            if existing_headers != CUSTOMER_DATA_WORKSHEET_HEADERS:
                print("Warning: Existing worksheet headers do not match expected headers. Attempting to update headers.")
                worksheet.update('A1', [CUSTOMER_DATA_WORKSHEET_HEADERS])
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

def get_all_customer_records():
    """
    Retrieves all customer records from the worksheet, including their 1-based row index.
    Each record will be a dictionary with an additional 'row_index' key.
    """
    worksheet = get_customer_data_worksheet()
    if not worksheet:
        return []
    try:
        all_data = worksheet.get_all_values()
        if not all_data:
            print("DEBUG: Google Sheet 'all_data' is empty or only has headers.")
            return []

        headers = all_data[0]
        data_rows = all_data[1:]

        customer_records = []
        for i, row in enumerate(data_rows):
            record = {}
            for j, header in enumerate(headers):
                if j < len(row):
                    record[header] = row[j]
                else:
                    record[header] = ''

            record['row_index'] = i + 2
            customer_records.append(record)
        return customer_records
    except Exception as e:
        print(f"ERROR in get_all_customer_records: {e}")
        return []

def get_customer_records_by_status(status):
    """
    Retrieves customer records filtered by status.
    Assumes get_all_customer_records already adds 'row_index'.
    """
    print(f"DEBUG: get_customer_records_by_status called with status: {status}")
    all_records = get_all_customer_records()
    filtered_records = [record for record in all_records if record.get('สถานะ') == status]
    print(f"DEBUG: get_customer_records_by_status returning {len(filtered_records)} records for status '{status}'")
    return filtered_records

def get_customer_records_by_keyword(keyword):
    """
    Retrieves customer records filtered by keyword across all values.
    Assumes get_all_customer_records already adds 'row_index'.
    """
    print(f"DEBUG: get_customer_records_by_keyword called with keyword: {keyword}")
    all_records = get_all_customer_records()
    filtered_records = [
        record for record in all_records
        if any(keyword.lower() in str(value).lower() for value in record.values())
    ]
    print(f"DEBUG: get_customer_records_by_keyword returning {len(filtered_records)} records for keyword '{keyword}'")
    return filtered_records

def get_loan_worksheet():
    """
    Gets the Loan_Transactions worksheet.
    Creates it if it doesn't exist and ensures headers are correct.
    """
    if not GSPREAD_CLIENT:
        print("Gspread client not initialized. Cannot access Loan Transactions worksheet.")
        return None
    try:
        spreadsheet = GSPREAD_CLIENT.open(SPREADSHEET_NAME)

        try:
            worksheet = spreadsheet.worksheet(LOAN_TRANSACTIONS_WORKSHEET_NAME)
            existing_headers = worksheet.row_values(1)
            # IMPORTANT: Check if headers match the LATEST LOAN_TRANSACTIONS_WORKSHEET_HEADERS
            if not existing_headers or existing_headers != LOAN_TRANSACTIONS_WORKSHEET_HEADERS:
                print(f"Warning: Loan Transactions worksheet headers do not match expected headers or are empty. Updating headers to: {LOAN_TRANSACTIONS_WORKSHEET_HEADERS}")
                worksheet.update('A1', [LOAN_TRANSACTIONS_WORKSHEET_HEADERS])
                print(f"Worksheet '{LOAN_TRANSACTIONS_WORKSHEET_NAME}' headers updated.")
        except gspread.exceptions.WorksheetNotFound:
            print(f"Worksheet '{LOAN_TRANSACTIONS_WORKSHEET_NAME}' not found. Creating it...")
            worksheet = spreadsheet.add_worksheet(
                title=LOAN_TRANSACTIONS_WORKSHEET_NAME,
                rows="100",
                cols=str(len(LOAN_TRANSACTIONS_WORKSHEET_HEADERS))
            )
            worksheet.append_row(LOAN_TRANSACTIONS_WORKSHEET_HEADERS)
            print(f"Worksheet '{LOAN_TRANSACTIONS_WORKSHEET_NAME}' created with headers.")

        return worksheet
    except Exception as e:
        print(f"Error accessing or creating Loan Transactions worksheet: {e}")
        return None

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

            record['row_index'] = i + 2
            loan_records.append(record)
        return loan_records
    except Exception as e:
        print(f"ERROR in get_all_loan_records: {e}")
        return []

def upload_image_to_cloudinary(file_stream, original_filename):
    """
    Uploads an image file stream to Cloudinary.
    Returns the URL of the uploaded file, or None if upload fails.
    """
    try:
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
    Handles customer data entry.
    - GET request: Displays the data entry form.
    - POST request: Processes the submitted customer data and images.
    Requires user to be logged in.
    """
    if 'username' not in session:
        flash('กรุณาเข้าสู่ระบบก่อน', 'error')
        return redirect(url_for('login'))

    logged_in_user = session['username']

    if request.method == 'POST':
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
        application_date = request.form.get('application_date', '') or '-'
        home_location_link = request.form.get('home_location_link', '') or '-'
        work_location_link = request.form.get('work_location_link', '') or '-'
        remarks = request.form.get('remarks', '') or '-'

        image_urls = []
        if 'customer_images' in request.files:
            files = request.files.getlist('customer_images')
            for customer_image in files:
                if customer_image and customer_image.filename:
                    url = upload_image_to_cloudinary(customer_image.stream, customer_image.filename)
                    if url:
                        image_urls.append(url)

        image_urls_str = ', '.join(image_urls) if image_urls else '-'

        worksheet = get_customer_data_worksheet()
        if worksheet:
            try:
                row_data = [
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
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
                    image_urls_str,
                    logged_in_user
                ]
                worksheet.append_row(row_data)
                flash('บันทึกข้อมูลลูกค้าเรียบร้อยแล้ว!', 'success')
                return redirect(url_for('enter_customer_data'))
            except Exception as e:
                flash(f'เกิดข้อผิดพลาดในการบันทึกข้อมูล: {e}', 'error')
                print(f"Error saving data to Google Sheet: {e}")
        else:
            flash('ไม่สามารถเข้าถึง Google Sheet สำหรับบันทึกข้อมูลลูกค้าได้', 'error')
            print("Error: Customer data worksheet not available.")

    return render_template('data_entry.html', username=logged_in_user)

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
        customer_records = get_customer_records_by_status("รอดำเนินการ")
        display_title = "ข้อมูลลูกค้า: รอดำเนินการ (ค่าเริ่มต้น)"
        if not customer_records:
            flash("ไม่พบข้อมูลลูกค้าที่มีสถานะ 'รอดำเนินการ' ในระบบ", "info")
        else:
            flash(f"แสดงข้อมูลลูกค้า {len(customer_records)} รายการที่มีสถานะ 'รอดำเนินการ' (ค่าเริ่มต้น)", "info")

    return render_template(
        'search_data.html',
        customer_records=customer_records,
        search_keyword=search_keyword,
        username=logged_in_user,
        display_title=display_title
    )

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
        updated_data = {
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
            row_to_update = [updated_data.get(header, '-') for header in CUSTOMER_DATA_WORKSHEET_HEADERS]
            worksheet.update(f'A{row_index}', [row_to_update])
            flash('บันทึกการแก้ไขข้อมูลลูกค้าเรียบร้อยแล้ว!', 'success')
            return redirect(url_for('search_customer_data'))
        except Exception as e:
            flash(f'เกิดข้อผิดพลาดในการบันทึกการแก้ไขข้อมูล: {e}', 'error')
            print(f"Error updating row {row_index} in Google Sheet: {e}")

    return render_template('edit_customer_data.html',
                           username=logged_in_user,
                           customer_data=customer_data,
                           row_index=row_index)


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

    loan_records = get_all_loan_records()

    if not loan_records:
        flash('ไม่พบรายการเงินกู้ในระบบ', 'info')
    else:
        flash(f'พบ {len(loan_records)} รายการเงินกู้', 'success')

    return render_template('loan_management.html',
                           username=logged_in_user,
                           loan_records=loan_records,
                           loan_headers=LOAN_TRANSACTIONS_WORKSHEET_HEADERS)

@app.route('/add_loan_record', methods=['POST'])
def add_loan_record():
    """
    Handles form submission for adding a new loan record to the Google Sheet.
    """
    if 'username' not in session:
        flash('กรุณาเข้าสู่ระบบก่อน', 'error')
        return redirect(url_for('login'))

    logged_in_user = session['username']

    if request.method == 'POST':
        try:
            # Get data from the form
            customer_name = request.form['customer_name'].strip()
            customer_surname = request.form['customer_surname'].strip()
            # เลขบัตรประชาชน is not directly from form anymore, set to '-' for new records from this form
            id_card_number_for_sheet = '-'

            loan_amount = float(request.form['loan_amount'])
            interest_rate = float(request.form['interest_rate']) # Still annual percentage
            upfront_interest_percent = float(request.form.get('upfront_interest_percent', 0)) # New field
            processing_fee_amount = float(request.form.get('processing_fee_amount', 0)) # New field
            start_date_str = request.form['start_date']
            loan_note = request.form.get('loan_note', '').strip()

            # Calculate the effective principal amount after deductions
            # This is the 'ยอดเงินต้นที่ต้องชำระ' for the sheet
            initial_principal_to_pay = loan_amount
            if upfront_interest_percent > 0:
                initial_principal_to_pay -= (loan_amount * (upfront_interest_percent / 100))
            if processing_fee_amount > 0:
                initial_principal_to_pay -= processing_fee_amount
            
            initial_principal_to_pay = round(initial_principal_to_pay, 2)

            # Prepare the data row based on LOAN_TRANSACTIONS_WORKSHEET_HEADERS
            # Ensure the order matches the headers exactly!
            row_data = {
                'Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'ชื่อลูกค้า': customer_name,
                'นามสกุลลูกค้า': customer_surname,
                'เลขบัตรประชาชนลูกค้า': id_card_number_for_sheet,
                'วงเงินกู้': loan_amount,
                'ดอกเบี้ย (%)': interest_rate,
                'หักดอกหัว-ท้าย (%)': upfront_interest_percent,
                'ค่าดำเนินการ': processing_fee_amount,
                'วันที่เริ่มกู้': start_date_str,
                'ยอดเงินต้นที่ต้องชำระ': initial_principal_to_pay, # This is the new calculated field
                'ยอดชำระแล้ว': 0, # Initial value is 0
                'ยอดค้างชำระ': initial_principal_to_pay, # Initially, outstanding is the initial principal to pay
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

        except ValueError:
            flash('ข้อมูลที่กรอกไม่ถูกต้อง กรุณาตรวจสอบวงเงิน, ดอกเบี้ย, หักดอกหัว-ท้าย, ค่าดำเนินการ', 'error')
        except KeyError as e:
            flash(f'ข้อมูลฟอร์มไม่ครบถ้วน: {e}', 'error')
        except Exception as e:
            flash(f'เกิดข้อผิดพลาดในการบันทึกรายการเงินกู้: {e}', 'error')
            print(f"Error adding loan record: {e}")

    return redirect(url_for('loan_management'))

# --- Main execution block ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)