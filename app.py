# Import necessary modules from Flask and other libraries
from flask import Flask, render_template, request, redirect, url_for, flash, session, Response, jsonify, current_app
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
import os
from datetime import datetime, timedelta
import requests
import json
import cloudinary
import cloudinary.uploader
import cloudinary.api
from flask_caching import Cache
from flask import request, jsonify, session
from datetime import datetime

# Initialize the Flask application
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your_super_secret_key_for_customer_app_2025_new')

cache = Cache(app, config={'CACHE_TYPE': 'simple'})

# --- Configuration for Google Sheets & Drive API Access ---
GOOGLE_API_SCOPE = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]

SERVICE_ACCOUNT_KEY_FILE = 'firebase-service-account.json'

# --- Google Sheets Configuration ---
SPREADSHEET_NAME = 'data1' # Main spreadsheet containing all data

PIDJOB_WORKSHEET_NAME = 'pidjob'
PIDJOB_WORKSHEET_HEADERS = [
    'status',
    'customer_id',
    'fullname',
    'phone',
    'approve_date',
    'approved_amount',
    'open_amount',
    'company',
    'other_company',
    'table1',
    'table2',
    'registrar',
    'timestamp'
]

# User Login Sheet
USER_LOGIN_SPREADSHEET_NAME = 'UserLoginData'
USER_LOGIN_WORKSHEET_NAME = 'users'

APPROVE_WORKSHEET_NAME = 'approove'
APPROVE_WORKSHEET_HEADERS = [
    'สถานะ', 
    'Customer ID', 
    'ชื่อลูกค้า', 
    'เบอร์มือถือ', 
    'วันที่ขอเข้ามา', 
    'วงเงินที่อนุมัติ', 
    'ผู้บันทึก'
]

# Original Customer Records Sheet (uses เลขบัตรประชาชน)
WORKSHEET_NAME = 'customer_records'
CUSTOMER_DATA_WORKSHEET_HEADERS = [
    'Timestamp', 'ชื่อ', 'นามสกุล', 'เลขบัตรประชาชน', 'เบอร์มือถือ',
    'กลุ่มลูกค้าหลัก',
    'กลุ่มอาชีพย่อย',
    'ระบุอาชีพย่อยอื่นๆ', 
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
    """Returns the original customer_records worksheet and force-updates header row."""
    worksheet = get_worksheet(SPREADSHEET_NAME, WORKSHEET_NAME)

    if worksheet:
        try:
            worksheet.update('A1', [CUSTOMER_DATA_WORKSHEET_HEADERS])
            print("DEBUG: Header of 'customer_records' worksheet updated successfully.")
        except Exception as e:
            print(f"ERROR: Failed to update header for 'customer_records': {e}")
    
    return worksheet



@app.route('/get-customer-info/<customer_id>')
def get_customer_info(customer_id):
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        worksheet = GSPREAD_CLIENT.open(SPREADSHEET_NAME).worksheet(APPROVE_WORKSHEET_NAME)
        data = worksheet.get_all_values()
        if not data or len(data) < 2:
            return jsonify({'error': 'No data found'}), 404

        headers = data[0]
        rows = data[1:]
        records = [dict(zip(headers, row)) for row in rows]

        # ค้นหาข้อมูลลูกค้าตาม Customer ID (ปรับชื่อ key ให้ตรงกับ Google Sheet)
        customer = next((r for r in records if r.get('Customer ID') == customer_id), None)
        if not customer:
            return jsonify({'error': 'Customer not found'}), 404

        return jsonify(customer)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/save-approved-data', methods=['POST'])
def save_approved_data():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data received'}), 400

        # เปิด worksheet pidjob
        worksheet = GSPREAD_CLIENT.open(SPREADSHEET_NAME).worksheet('pidjob')

        # ตัวอย่างลำดับคอลัมน์ที่บันทึกลง pidjob
        # ปรับลำดับและชื่อฟิลด์ให้ตรงกับ Google Sheet คุณ
        row_to_insert = [
            data.get('customer_id', ''),
            data.get('status', ''),
            data.get('fullname', ''),
            data.get('phone', ''),
            data.get('approve_date', ''),
            data.get('approved_amount', ''),
            data.get('open_amount', ''),
            data.get('company', ''),
            data.get('other_company', ''),
            data.get('table1', ''),
            data.get('table2', ''),
            data.get('registrar', ''),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ]

        worksheet.append_row(row_to_insert)

        return jsonify({'message': 'บันทึกข้อมูลเรียบร้อย'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500   

@cache.cached(timeout=20, key_prefix='all_customer_records')
def get_all_customer_records():
    """
    Retrieves all customer records from the original customer_records worksheet.
    Each record will be a dictionary, now including its row_index.
    """
    global loan_customers_cache, loan_customers_cache_timestamp


    print("DEBUG: Fetching loan customer records from Google Sheet (cache expired or not set).")
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
# NEW: Route to get aggregated customer data for chart
@app.route('/get_customer_chart_data')
def get_customer_chart_data():
    """
    Retrieves customer data, aggregates it by year/month and 'กลุ่มลูกค้าหลัก',
    and returns it as JSON for charting.
    """
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    all_customers = get_all_customer_records()
    
    chart_data = {} # Stores aggregated data: {year: {month: {group: count}}}
    unique_customer_groups = set()
    unique_years = set()
    
    for record in all_customers:
        # ใช้ 'Timestamp' และ 'กลุ่มลูกค้าหลัก' ซึ่งเป็นส่วนหนึ่งของ CUSTOMER_DATA_WORKSHEET_HEADERS ที่คุณมีอยู่แล้ว
        timestamp_str = record.get('Timestamp') 
        customer_group = record.get('กลุ่มลูกค้าหลัก')

        if timestamp_str and customer_group:
            try:
                # Parse timestamp string (e.g., 'YYYY-MM-DD HH:MM:SS')
                dt_object = datetime.strptime(timestamp_str.split(' ')[0], '%Y-%m-%d')
                year = str(dt_object.year)
                month = dt_object.strftime('%m') # '01', '02', etc.

                unique_years.add(year)
                unique_customer_groups.add(customer_group)

                if year not in chart_data:
                    chart_data[year] = {}
                if month not in chart_data[year]:
                    chart_data[year][month] = {}
                
                chart_data[year][month][customer_group] = chart_data[year][month].get(customer_group, 0) + 1
            except ValueError:
                # Handle cases where timestamp might be malformed
                print(f"Warning: Could not parse timestamp '{timestamp_str}' for chart data.")
                continue

    # Convert sets to sorted lists for consistent ordering in frontend
    sorted_years = sorted(list(unique_years))
    sorted_customer_groups = sorted(list(unique_customer_groups))
    
    # Months list is fixed
    all_months = [str(i).zfill(2) for i in range(1, 13)]

    return jsonify({
        'chart_data': chart_data,
        'unique_customer_groups': sorted_customer_groups,
        'unique_years': sorted_years,
        'all_months': all_months
    })




@cache.cached(timeout=20, key_prefix='user_login_data')
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

@app.route('/loan_management')
def loan_management():
    if 'username' not in session:
        flash('กรุณาเข้าสู่ระบบก่อน', 'error')
        return redirect(url_for('login'))

    approove_data = []

    try:
        worksheet = GSPREAD_CLIENT.open("data1").worksheet("approove")
        data = worksheet.get_all_values()

        if data and len(data) > 1:
            headers = data[0]
            rows = data[1:]
            approove_data = [dict(zip(headers, row)) for row in rows]

    except Exception as e:
        flash(f"เกิดข้อผิดพลาดในการโหลดข้อมูล approove: {e}", "error")

    return render_template(
        'loan_management.html',
        username=session['username'],
        approove_data=approove_data
    )



@app.route('/logout')
def logout():
    """
    Logs out the user by clearing the session.
    """
    session.pop('username', None)
    flash('คุณได้ออกจากระบบแล้ว', 'success')
    return redirect(url_for('login'))

@app.route('/enter_customer_data', methods=['GET', 'POST']) #หน้าลงทะเบียนลูกค้า
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

            # --- เพิ่มการดึงข้อมูลกลุ่มลูกค้าใหม่ตรงนี้ ---
            main_customer_group = request.form.get('main_customer_group', '') or '-'
            sub_profession_group = request.form.get('sub_profession_group', '') or '-'
            other_sub_profession = request.form.get('other_sub_profession', '') or '-'

            # Logic เพื่อกำหนดค่าสุดท้ายของ 'กลุ่มอาชีพย่อย'
            final_sub_profession_value = sub_profession_group
            if sub_profession_group == "อื่นๆ":
                final_sub_profession_value = other_sub_profession

            # --- สิ้นสุดการเพิ่มข้อมูลกลุ่มลูกค้าใหม่ ---

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
                        # Make sure upload_image_to_cloudinary is defined elsewhere in app.py
                        url = upload_image_to_cloudinary(customer_image.stream, customer_image.filename)
                        if url:
                            image_urls.append(url)

            # Join all image URLs into a single comma-separated string, or "-" if no images
            image_urls_str = ', '.join(image_urls) if image_urls else '-'

            # Get the customer data worksheet
            worksheet = get_customer_data_worksheet()
            if worksheet:
                try:
                    row_data = {
                        'Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'ชื่อ': customer_name,
                        'นามสกุล': last_name,
                        'เลขบัตรประชาชน': id_card_number,
                        'เบอร์มือถือ': mobile_phone_number,
                        'กลุ่มลูกค้าหลัก': main_customer_group,
                        'กลุ่มอาชีพย่อย': final_sub_profession_value, 
                        'ระบุอาชีพย่อยอื่นๆ': other_sub_profession,
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

# ... (โค้ดส่วนบนของ app.py) ...


@app.route('/search_customer_data', methods=['GET'])
def search_customer_data():
    """
    Handles searching for customer data from the original customer_records sheet.
    Now defaults to showing 'รอดำเนินการ' status if no specific search or filter is applied.
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

    # Logic:
    # 1. If status_filter is explicitly 'pending', show pending.
    # 2. If a search_keyword is provided, perform keyword search.
    # 3. Otherwise (no explicit filter or keyword), default to showing 'รอดำเนินการ'.
    if status_filter == 'pending':
        customer_records = get_customer_records_by_status("รอดำเนินการ")
        display_title = "ข้อมูลลูกค้า: รอดำเนินการ"
        if not customer_records:
            flash("ไม่พบข้อมูลลูกค้าที่มีสถานะ 'รอดำเนินการ'", "info")
        else:
            flash(f"พบ {len(customer_records)} รายการที่มีสถานะ 'รอดำเนินการ'", "success")
    elif search_keyword:
        customer_records = get_customer_records_by_keyword(search_keyword)
        display_title = f"ผลการค้นหาสำหรับ: '{search_keyword}'"
        if not customer_records:
            flash(f"ไม่พบข้อมูลลูกค้าสำหรับ '{search_keyword}'", "info")
        else:
            flash(f"พบ {len(customer_records)} รายการสำหรับ '{search_keyword}'", "success")
    else:
        # Default behavior: Show records with status 'รอดำเนินการ'
        customer_records = get_customer_records_by_status("รอดำเนินการ")
        display_title = "ข้อมูลลูกค้า: รอดำเนินการ"
        if not customer_records:
            flash("ไม่พบข้อมูลลูกค้าที่มีสถานะ 'รอดำเนินการ' ในระบบ", "info")
        else:
            flash(f"แสดงข้อมูลลูกค้าที่มีสถานะ 'รอดำเนินการ' {len(customer_records)} รายการ", "info")


    return render_template(
        'search_data.html',
        customer_records=customer_records,
        search_keyword=search_keyword,
        username=logged_in_user,
        display_title=display_title
    )
# . . .เรียกตารางอนุมัติยอด(appove)มาโชว์
@app.route('/get_approove_data')
def get_approove_data():
    if 'username' not in session:
        return redirect(url_for('login'))

    try:
        worksheet = GSPREAD_CLIENT.open(SPREADSHEET_NAME).worksheet(APPROVE_WORKSHEET_NAME)
        data = worksheet.get_all_values()
        if not data or len(data) < 2:
            records = []
        else:
            headers = data[0]
            rows = data[1:]
            records = [dict(zip(headers, row)) for row in rows]

        # ใช้ key 'สถานะ' (ภาษาไทย) ให้ตรงกับ Google Sheet
        approve_data = [r for r in records if r.get('สถานะ') == 'อนุมัติ']
        closejob_data = [r for r in records if r.get('สถานะ') == 'ปิดจ๊อบ']

        return render_template('loan_management.html',
                               approve_data=approve_data,
                               closejob_data=closejob_data,
                               username=session['username'])
    except Exception as e:
        flash(f"เกิดข้อผิดพลาดในการโหลดข้อมูล approove: {e}", "error")
        return redirect(url_for('dashboard'))


# ... (โค้ดส่วนล่างของ app.py) ...


@app.route('/edit_customer_data/<int:row_index>', methods=['GET', 'POST'])
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

    # (ค่าที่รับมาจากลูกค้ารอดำเนินการ)
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
            'เลขบัตรประชาชน': request.form.get('id_card_number', '') or '-',
            'เบอร์มือถือ': request.form.get('mobile_phone_number', '') or '-',
            'กลุ่มลูกค้าหลัก': request.form.get('main_customer_group', '') or '-',
            'กลุ่มอาชีพย่อย': request.form.get('sub_profession_group', '') or '-',
            'ระบุอาชีพย่อยอื่นๆ': request.form.get('other_sub_profession', '') or '-',
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
        
        # New logic: Get customer ID from form, or keep the existing one if not 'อนุมัติ'
        customer_id = request.form.get('customer_id', '')

        # Check for image URLs from both new uploads and kept images
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
        updated_data['Logged In User'] = logged_in_user

        # ----------------------------------------------------
        # NEW LOGIC: Check for 'อนุมัติ' status and save to new worksheet
        # ----------------------------------------------------
        if updated_data.get('สถานะ') == 'อนุมัติ':
            try:
                # Get the 'approove' worksheet
                client = gspread.authorize(creds)
                approve_worksheet = client.open(SPREADSHEET_NAME).worksheet(APPROVE_WORKSHEET_NAME)

                # Get the next available customer ID
                all_records = approve_worksheet.get_all_records()
                next_id_number = len(all_records) + 1
                customer_id = f'SL{next_id_number}'

                # Create the row data for the 'approove' worksheet
                approved_data_row = [
                    "รอปิดจ๊อบ", # Status ที่บันทึก
                    customer_id,
                    f"{updated_data.get('ชื่อ', '')} {updated_data.get('นามสกุล', '')}".strip(),
                    updated_data.get('เบอร์มือถือ', ''),
                    updated_data.get('วันที่ขอเข้ามา', ''),
                    updated_data.get('วงเงินที่อนุมัติ', ''),
                    logged_in_user
                ]

                # Append the new approved record to the 'approove' worksheet
                approve_worksheet.append_row(approved_data_row)

                flash(f'ข้อมูลลูกค้าได้รับการอนุมัติและบันทึกในเวิร์คชีท "{APPROVE_WORKSHEET_NAME}" แล้ว ด้วยรหัสลูกค้า {customer_id}', 'success')

            except gspread.WorksheetNotFound:
                flash(f'ไม่พบเวิร์คชีท "{APPROVE_WORKSHEET_NAME}" กรุณาสร้างเวิร์คชีทดังกล่าว', 'error')
            except Exception as e:
                flash(f'เกิดข้อผิดพลาดในการบันทึกข้อมูลอนุมัติ: {e}', 'error')
                print(f"Error saving to approve worksheet: {e}")

        # Finalize the data to update the original customer_records worksheet
        updated_data['Customer ID'] = customer_id if customer_id else customer_data.get('Customer ID', '-')
        
        # Prepare the row to update in the correct order of headers
        try:
            worksheet_headers = CUSTOMER_DATA_WORKSHEET_HEADERS  # ไม่มี Customer ID
            row_to_update = [updated_data.get(header, '-') for header in worksheet_headers]
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

# --- Main execution block ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
