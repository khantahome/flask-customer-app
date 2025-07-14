# app.py content with modifications

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

# UPDATED: Define headers for the Loan Transactions worksheet for daily loans
LOAN_TRANSACTIONS_WORKSHEET_NAME = os.environ.get('LOAN_TRANSACTIONS_WORKSHEET_NAME', 'Loan_Transactions')
LOAN_TRANSACTIONS_WORKSHEET_HEADERS = [
    'Timestamp', 'เลขบัตรประชาชนลูกค้า', 'ชื่อลูกค้า', 'นามสกุลลูกค้า',
    'วงเงินกู้', 'ดอกเบี้ย (%)', 'วันที่เริ่มกู้', 'ค่าดำเนินการ',
    'หักดอกหัว-ท้าย', 
    'เงินต้นที่ต้องคืน', # CHANGED: Renamed from 'ยอดที่ต้องชำระรายวัน'
    'ยอดที่ต้องชำระรายวัน', # NEW: Added new daily payment field
    'ยอดชำระแล้ว', 'ยอดค้างชำระ', 
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
            print("DEBUG: Google Sheet 'all_data' is empty or only has headers.")
            return []

        # Assume the first row is headers
        headers = all_data[0]
        data_rows = all_data[1:] # All rows after the header
        
        customer_records = []
        for i, row in enumerate(data_rows):
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
            # Verify headers if worksheet already exists
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
        spreadsheet = GSPREAD_CLIENT.open(SPREADSHEET_NAME) 

        try:
            worksheet = spreadsheet.worksheet(LOAN_TRANSACTIONS_WORKSHEET_NAME)

            existing_headers = worksheet.row_values(1)
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

# --- Route for Adding New Loan Record ---
@app.route('/add_loan_record', methods=['POST'])
def add_loan_record():
    """
    Handles form submission for adding a new loan record to the Google Sheet.
    Calculates daily payment based on provided formula.
    """
    if 'username' not in session:
        flash('กรุณาเข้าสู่ระบบก่อน', 'error')
        return redirect(url_for('login'))
    
    logged_in_user = session['username']

    if request.method == 'POST':
        try:
            # Get data from the form
            id_card_number = request.form['id_card_number'].strip()
            loan_amount = float(request.form['loan_amount'])
            interest_rate = float(request.form['interest_rate'])
            start_date_str = request.form['start_date']
            processing_fee = float(request.form['processing_fee'])
            upfront_deduction = float(request.form['upfront_deduction']) 
            loan_note = request.form.get('loan_note', '').strip()

            customer_name = ""
            customer_surname = ""

            # --- Advanced: Fetch customer name from customer_records worksheet ---
            customer_worksheet = get_customer_data_worksheet()
            if customer_worksheet:
                customer_records_data = customer_worksheet.get_all_records()
                found_customer = next((rec for rec in customer_records_data if rec.get('เลขบัตรประชาชน') == id_card_number), None)
                if found_customer:
                    customer_name = found_customer.get('ชื่อ', '')
                    customer_surname = found_customer.get('นามสกุล', '')
                else:
                    flash(f"ไม่พบข้อมูลลูกค้าสำหรับเลขบัตรประชาชน {id_card_number} ในระบบ กรุณากรอกข้อมูลลูกค้าก่อน", 'warning')
            else:
                flash("ไม่สามารถเชื่อมต่อกับชีทข้อมูลลูกค้าได้", 'error')
            # --- End Advanced Fetch ---

            # NEW: Calculate 'เงินต้นที่ต้องคืน' (Principal to be Returned)
            # Formula: ((วงเงินกู้ - (วงเงินกู้ * ดอกเบี้ย / 100)) * 2) + ค่าดำเนินการ - วงเงินกู้ - หักดอกหัว-ท้าย
            amount_after_interest_deduction = loan_amount - (loan_amount * interest_rate / 100)
            principal_to_return = (amount_after_interest_deduction * 2) + processing_fee - loan_amount - upfront_deduction
            principal_to_return = round(principal_to_return, 2)

            # NEW: Calculate 'ยอดที่ต้องชำระรายวัน' (Daily Payment)
            # Formula: วงเงินกู้ - (วงเงินกู้ * ดอกเบี้ย / 100)
            daily_payment = loan_amount - (loan_amount * interest_rate / 100)
            daily_payment = round(daily_payment, 2)


            # Prepare the data row based on LOAN_TRANSACTIONS_WORKSHEET_HEADERS
            row_data = {
                'Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'เลขบัตรประชาชนลูกค้า': id_card_number,
                'ชื่อลูกค้า': customer_name,
                'นามสกุลลูกค้า': customer_surname,
                'วงเงินกู้': loan_amount,
                'ดอกเบี้ย (%)': interest_rate,
                'วันที่เริ่มกู้': start_date_str,
                'ค่าดำเนินการ': processing_fee,
                'หักดอกหัว-ท้าย': upfront_deduction, 
                'เงินต้นที่ต้องคืน': principal_to_return, # NEW VALUE
                'ยอดที่ต้องชำระรายวัน': daily_payment, # NEW VALUE
                'ยอดชำระแล้ว': 0, # Initial value
                'ยอดค้างชำระ': principal_to_return, # Initial outstanding is now based on 'เงินต้นที่ต้องคืน'
                'สถานะเงินกู้': 'Active', # Initial status
                'หมายเหตุเงินกู้': loan_note,
                'ผู้บันทึก': logged_in_user
            }

            # Ensure the order of values matches the headers
            ordered_row_values = [str(row_data.get(header, '')) for header in LOAN_TRANSACTIONS_WORKSHEET_HEADERS]
            
            # Append the new row to the worksheet
            loan_worksheet = get_loan_worksheet()
            if loan_worksheet:
                loan_worksheet.append_row(ordered_row_values)
                flash('บันทึกรายการเงินกู้ใหม่สำเร็จ!', 'success')
            else:
                flash('ไม่สามารถบันทึกรายการเงินกู้ได้: ไม่พบชีทรายการเงินกู้', 'error')

        except ValueError as ve:
            flash(f'ข้อมูลไม่ถูกต้อง: กรุณาป้อนตัวเลขสำหรับวงเงินกู้, ดอกเบี้ย, ค่าดำเนินการ และหักดอกหัว-ท้าย. ({ve})', 'error')
        except KeyError as ke:
            flash(f'ข้อมูลฟอร์มไม่ครบถ้วน: ขาดข้อมูลสำคัญ. ({ke})', 'error')
        except Exception as e:
            flash(f'เกิดข้อผิดพลาดในการบันทึกข้อมูล: {e}', 'error')

    return redirect(url_for('loan_management'))


# Route for handling loan record deletion
@app.route('/delete_loan_record/<int:row_index>', methods=['POST'])
def delete_loan_record(row_index):
    """
    Handles deletion of a loan record based on its row index in the Google Sheet.
    """
    if 'username' not in session:
        flash('กรุณาเข้าสู่ระบบก่อน', 'error')
        return redirect(url_for('login'))
    
    # Ensure the row_index is valid (Google Sheets rows are 1-based)
    if row_index < 2: # Row 1 is headers
        flash('ไม่สามารถลบแถวส่วนหัวได้', 'error')
        return redirect(url_for('loan_management'))

    try:
        worksheet = get_loan_worksheet()
        if worksheet:
            # Delete the row
            worksheet.delete_row(row_index)
            flash(f'ลบรายการเงินกู้ในแถวที่ {row_index} สำเร็จ!', 'success')
        else:
            flash('ไม่สามารถเชื่อมต่อกับชีทรายการเงินกู้ได้', 'error')
    except Exception as e:
        flash(f'เกิดข้อผิดพลาดในการลบรายการเงินกู้: {e}', 'error')
    
    return redirect(url_for('loan_management'))


# --- Existing Routes (No changes unless specified) ---

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        users = load_users() # Load users from Google Sheet

        if username in users and users[username] == password:
            session['username'] = username
            flash('เข้าสู่ระบบสำเร็จ!', 'success')
            return redirect(url_for('customer_data'))
        else:
            flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('ออกจากระบบแล้ว', 'info')
    return redirect(url_for('login'))

@app.route('/customer_data')
def customer_data():
    if 'username' not in session:
        flash('กรุณาเข้าสู่ระบบก่อน', 'error')
        return redirect(url_for('login'))
    
    logged_in_user = session['username']
    all_customer_records = get_all_customer_records()
    return render_template('customer_data.html', 
                           username=logged_in_user, 
                           customer_records=all_customer_records)

@app.route('/add_customer', methods=['GET', 'POST'])
def add_customer():
    if 'username' not in session:
        flash('กรุณาเข้าสู่ระบบก่อน', 'error')
        return redirect(url_for('login'))

    logged_in_user = session['username']

    if request.method == 'POST':
        try:
            # Collect data from form
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            name = request.form['name']
            surname = request.form['surname']
            id_card = request.form['id_card']
            mobile = request.form['mobile']
            registered = request.form.get('registered', '')
            business_name = request.form.get('business_name', '')
            business_type = request.form.get('business_type', '')
            registered_address = request.form.get('registered_address', '')
            status = request.form.get('status', 'ใหม่') # Default to 'ใหม่'
            desired_loan_amount = request.form.get('desired_loan_amount', '')
            approved_loan_amount = request.form.get('approved_loan_amount', '')
            
            # Convert boolean from checkbox to Thai string
            # 'on' if checked, None if not. Convert to 'ใช่' or 'ไม่'
            ever_applied_thai = 'ใช่' if request.form.get('ever_applied') == 'on' else 'ไม่'
            
            check_value = request.form.get('check_value', '')
            how_applied = request.form.get('how_applied', '')
            line_id = request.form.get('line_id', '')
            upfront_interest = request.form.get('upfront_interest', '')
            processing_fee = request.form.get('processing_fee', '')
            date_applied = request.form.get('date_applied', '')
            home_location_link = request.form.get('home_location_link', '')
            work_location_link = request.form.get('work_location_link', '')
            notes = request.form.get('notes', '')

            # Image uploads
            image_urls = []
            if 'images' in request.files:
                for file in request.files.getlist('images'):
                    if file and file.filename:
                        upload_result = cloudinary.uploader.upload(file)
                        image_urls.append(upload_result['secure_url'])
            
            # Prepare row data as a dictionary
            row_data = {
                'Timestamp': timestamp,
                'ชื่อ': name,
                'นามสกุล': surname,
                'เลขบัตรประชาชน': id_card,
                'เบอร์มือถือ': mobile,
                'จดทะเบียน': registered,
                'ชื่อกิจการ': business_name,
                'ประเภทธุรกิจ': business_type,
                'ที่อยู่จดทะเบียน': registered_address,
                'สถานะ': status,
                'วงเงินที่ต้องการ': desired_loan_amount,
                'วงเงินที่อนุมัติ': approved_loan_amount,
                'เคยขอเข้ามาในเครือหรือยัง': ever_applied_thai,
                'เช็ค': check_value,
                'ขอเข้ามาทางไหน': how_applied,
                'LINE ID': line_id,
                'หักดอกหัวท้าย': upfront_interest,
                'ค่าดำเนินการ': processing_fee,
                'วันที่ขอเข้ามา': date_applied,
                'ลิงค์โลเคชั่นบ้าน': home_location_link,
                'ลิงค์โลเคชั่นที่ทำงาน': work_location_link,
                'หมายเหตุ': notes,
                'Image URLs': ', '.join(image_urls), # Store all image URLs as a comma-separated string
                'Logged In User': logged_in_user
            }

            # Get the worksheet
            worksheet = get_customer_data_worksheet()
            if worksheet:
                # Ensure the order of values matches the headers
                ordered_row_values = [row_data.get(header, '') for header in CUSTOMER_DATA_WORKSHEET_HEADERS]
                worksheet.append_row(ordered_row_values)
                flash('บันทึกข้อมูลลูกค้าสำเร็จ!', 'success')
            else:
                flash('ไม่สามารถบันทึกข้อมูลลูกค้าได้: ไม่พบชีทข้อมูลลูกค้า', 'error')
            
            return redirect(url_for('customer_data'))

        except Exception as e:
            flash(f'เกิดข้อผิดพลาดในการบันทึกข้อมูล: {e}', 'error')
            # Stay on the add customer page with form data
            return render_template('add_customer.html', 
                                   username=logged_in_user, 
                                   form_data=request.form)

    return render_template('add_customer.html', username=logged_in_user)

@app.route('/edit_customer/<int:row_index>', methods=['GET', 'POST'])
def edit_customer(row_index):
    if 'username' not in session:
        flash('กรุณาเข้าสู่ระบบก่อน', 'error')
        return redirect(url_for('login'))
    
    logged_in_user = session['username']
    worksheet = get_customer_data_worksheet()

    if not worksheet:
        flash('ไม่สามารถเชื่อมต่อกับชีทข้อมูลลูกค้าได้', 'error')
        return redirect(url_for('customer_data'))

    try:
        # Fetch the specific row data
        # worksheet.row_values(1) is headers, so row_index is the actual Google Sheet row number
        customer_values = worksheet.row_values(row_index)
        
        if not customer_values:
            flash('ไม่พบข้อมูลลูกค้าสำหรับแถวที่ระบุ', 'error')
            return redirect(url_for('customer_data'))
        
        # Convert list of values to a dictionary using headers
        customer_data = dict(zip(CUSTOMER_DATA_WORKSHEET_HEADERS, customer_values))

        if request.method == 'POST':
            # Update data from form
            updated_data = {
                'Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'ชื่อ': request.form['name'],
                'นามสกุล': request.form['surname'],
                'เลขบัตรประชาชน': request.form['id_card'],
                'เบอร์มือถือ': request.form['mobile'],
                'จดทะเบียน': request.form.get('registered', ''),
                'ชื่อกิจการ': request.form.get('business_name', ''),
                'ประเภทธุรกิจ': request.form.get('business_type', ''),
                'ที่อยู่จดทะเบียน': request.form.get('registered_address', ''),
                'สถานะ': request.form.get('status', 'ใหม่'), # Default to 'ใหม่'
                'วงเงินที่ต้องการ': request.form.get('desired_loan_amount', ''),
                'วงเงินที่อนุมัติ': request.form.get('approved_loan_amount', ''),
                'เคยขอเข้ามาในเครือหรือยัง': 'ใช่' if request.form.get('ever_applied') == 'on' else 'ไม่',
                'เช็ค': request.form.get('check_value', ''),
                'ขอเข้ามาทางไหน': request.form.get('how_applied', ''),
                'LINE ID': request.form.get('line_id', ''),
                'หักดอกหัวท้าย': request.form.get('upfront_interest', ''),
                'ค่าดำเนินการ': request.form.get('processing_fee', ''),
                'วันที่ขอเข้ามา': request.form.get('date_applied', ''),
                'ลิงค์โลเคชั่นบ้าน': request.form.get('home_location_link', ''),
                'ลิงค์โลเคชั่นที่ทำงาน': request.form.get('work_location_link', ''),
                'หมายเหตุ': request.form.get('notes', ''),
                # Keep existing Image URLs unless new images are uploaded
                'Image URLs': customer_data.get('Image URLs', ''),
                'Logged In User': logged_in_user
            }

            # Handle new image uploads (append to existing if any)
            new_image_urls = []
            if 'images' in request.files:
                for file in request.files.getlist('images'):
                    if file and file.filename:
                        upload_result = cloudinary.uploader.upload(file)
                        new_image_urls.append(upload_result['secure_url'])
            
            if new_image_urls:
                existing_image_urls = customer_data.get('Image URLs', '')
                updated_data['Image URLs'] = existing_image_urls + (', ' if existing_image_urls else '') + ', '.join(new_image_urls)

            # Prepare list of values in the correct order for update
            updated_values = [updated_data.get(header, '') for header in CUSTOMER_DATA_WORKSHEET_HEADERS]
            
            # Update the row in the Google Sheet
            worksheet.update(f'A{row_index}', [updated_values])
            flash('อัปเดตข้อมูลลูกค้าสำเร็จ!', 'success')
            return redirect(url_for('customer_data'))

    except gspread.exceptions.APIError as api_e:
        flash(f'เกิดข้อผิดพลาดกับ Google Sheets API: {api_e}', 'error')
        print(f"Google Sheets API Error: {api_e}")
    except Exception as e:
        flash(f'เกิดข้อผิดพลาดในการดึงหรืออัปเดตข้อมูล: {e}', 'error')
        print(f"Error in edit_customer: {e}")
    
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
                           loan_records=loan_records, # Pass fetched loan data to template
                           loan_headers=LOAN_TRANSACTIONS_WORKSHEET_HEADERS) # Pass headers for table display



# --- Main execution block ---
if __name__ == '__main__':
    # For local development, set environment variables directly or use a .env file
    # For production, ensure these are set in your hosting environment (e.g., Railway, Heroku)
    # Example:
    # os.environ['SECRET_KEY'] = 'your_super_secret_key_for_customer_app_2025_new'
    # os.environ['GOOGLE_CREDENTIALS_JSON'] = json.dumps({'type': 'service_account', ...})
    # os.environ['CLOUDINARY_CLOUD_NAME'] = 'your_cloud_name'
    # os.environ['CLOUDINARY_API_KEY'] = 'your_api_key'
    # os.environ['CLOUDINARY_API_SECRET'] = 'your_api_secret'
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))