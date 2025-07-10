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

# Initialize the Flask application
app = Flask(__name__)
# Set a secret key for Flask sessions (needed for flash messages and session management)
# *** สำคัญ: เปลี่ยนเป็นคีย์ลับของคุณเองเพื่อความปลอดภัย! ***
app.secret_key = 'your_super_secret_key_for_customer_app_2025_new' # Make sure this is a strong, unique key

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

# --- Google Drive Configuration ---
# Name of the folder in Google Drive where images will be stored.
IMAGE_FOLDER_NAME = 'image2' # โฟลเดอร์สำหรับเก็บรูปภาพลูกค้า
# Global variable to store the ID of the image folder once found or created.
IMAGE_FOLDER_ID = None

# --- Initialize Google API Clients ---
# Initialize gspread client for Google Sheets
GSPREAD_CLIENT = None
try:
    GSPREAD_CREDS = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_KEY_FILE, GOOGLE_API_SCOPE)
    GSPREAD_CLIENT = gspread.authorize(GSPREAD_CREDS)
except Exception as e:
    print(f"CRITICAL ERROR: gspread client failed to initialize. Check 'exclusive.json' and network. Error: {e}")


# Initialize PyDrive client for Google Drive
DRIVE_CLIENT = None
try:
    GAUTH = GoogleAuth()
    GAUTH.credentials = GSPREAD_CREDS # Reuse credentials from gspread
    DRIVE_CLIENT = GoogleDrive(GAUTH)
except Exception as e:
    print(f"CRITICAL ERROR: PyDrive client failed to initialize. Check 'exclusive.json' and Google Drive API permissions. Error: {e}")


# --- Helper Functions for Google Sheets ---

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

def get_or_create_folder(folder_name):
    """
    Finds the ID of an existing Google Drive folder or creates it if it doesn't exist.
    Stores the ID in a global variable for efficiency.
    """
    global IMAGE_FOLDER_ID
    if IMAGE_FOLDER_ID:
        return IMAGE_FOLDER_ID

    if not DRIVE_CLIENT:
        print("PyDrive client not initialized. Cannot access Google Drive.")
        return None

    try:
        # Search for the folder by title and mimeType (folder type)
        file_list = DRIVE_CLIENT.ListFile(
            {'q': f"title='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"}
        ).GetList()

        if file_list:
            IMAGE_FOLDER_ID = file_list[0]['id']
            print(f"Found existing folder: '{folder_name}' with ID: {IMAGE_FOLDER_ID}")
        else:
            # Create the folder if not found
            print(f"Folder '{folder_name}' not found. Creating new folder...")
            folder_metadata = {'title': folder_name, 'mimeType': 'application/vnd.google-apps.folder'}
            folder = DRIVE_CLIENT.CreateFile(folder_metadata)
            folder.Upload()
            IMAGE_FOLDER_ID = folder['id']
            print(f"Created new folder: '{folder_name}' with ID: {IMAGE_FOLDER_ID}")
        return IMAGE_FOLDER_ID
    except Exception as e:
        print(f"Error getting or creating folder '{folder_name}': {e}")
        return None

def get_next_sequential_filename(folder_id, original_filename):
    """
    Determines the next available sequential filename (e.g., 000001.ext, 000002.ext).
    It checks existing files in the folder and finds the smallest missing number.
    """
    if not DRIVE_CLIENT or not folder_id:
        return None

    try:
        # Get list of files in the folder
        file_list = DRIVE_CLIENT.ListFile(
            {'q': f"'{folder_id}' in parents and trashed=false"}
        ).GetList()

        existing_numbers = set()
        for file_item in file_list:
            # Extract number from filename (assuming format NNNNNN.ext)
            name_parts = os.path.splitext(file_item['title'])
            if len(name_parts[0]) == 6 and name_parts[0].isdigit():
                existing_numbers.add(int(name_parts[0]))

        next_number = 1
        while next_number in existing_numbers:
            next_number += 1

        # Format the number with leading zeros (e.g., 1 -> 000001)
        new_base_name = f"{next_number:06d}"
        file_extension = os.path.splitext(original_filename)[1] # Keep original extension

        return f"{new_base_name}{file_extension}"

    except Exception as e:
        print(f"Error determining next sequential filename: {e}")
        return None

def upload_image_to_drive(file_stream, original_filename):
    """
    Uploads an image file stream to the designated Google Drive folder with a sequential filename.
    Returns the direct download link of the uploaded file, or None if upload fails.
    """
    if not DRIVE_CLIENT:
        print("PyDrive client not initialized. Cannot upload image.")
        return None

    folder_id = get_or_create_folder(IMAGE_FOLDER_NAME)
    if not folder_id:
        print(f"Failed to get or create folder '{IMAGE_FOLDER_NAME}'. Image upload failed.")
        return None

    try:
        # Get the next sequential filename
        new_filename = get_next_sequential_filename(folder_id, original_filename)
        if not new_filename:
            return None

        # Create a new file in Google Drive with the determined filename and parent folder.
        file_metadata = {'title': new_filename, 'parents': [{'id': folder_id}]}
        gdrive_file = DRIVE_CLIENT.CreateFile(file_metadata)
        gdrive_file.content = file_stream # Set the content of the file from the stream

        gdrive_file.Upload() # Perform the upload

        # Make the file publicly accessible (optional, but needed if you want to display it directly without auth)
        gdrive_file.InsertPermission({
            'type': 'anyone',
            'value': 'reader',
            'role': 'reader'
        })
        
        # Create Direct Download Link using File ID
        if 'id' in gdrive_file:
            file_id = gdrive_file['id']
            direct_link = f"https://drive.google.com/uc?export=view&id={file_id}"
            print(f"Uploaded file '{new_filename}' to Google Drive. Direct Link: {direct_link}")
            return direct_link
        else:
            print(f"Warning: File ID not found for uploaded file '{new_filename}'. Cannot generate direct link.")
            return None
    except Exception as e:
        print(f"Error uploading image '{original_filename}' to Google Drive: {e}")
        return None

def delete_image_from_drive(image_url):
    """
    Deletes an image from Google Drive given its direct download link.
    This function extracts the file ID from the direct link.
    """
    if not DRIVE_CLIENT:
        print("PyDrive client not initialized. Cannot delete image.")
        return False
    
    try:
        # Extract file ID from the direct download URL format: https://drive.google.com/uc?export=view&id=FILE_ID
        file_id = None
        if "id=" in image_url:
            file_id = image_url.split("id=")[1].split("&")[0] # In case there are other params after id=
        # Handle old webViewLink format if it exists in the sheet for old records
        elif "file/d/" in image_url and "/view" in image_url:
            file_id = image_url.split("file/d/")[1].split("/view")[0]

        if not file_id:
            print(f"Could not extract file ID from URL for deletion: {image_url}")
            return False

        # Get the file object by ID
        gdrive_file = DRIVE_CLIENT.CreateFile({'id': file_id})
        gdrive_file.Delete() # Move to trash
        print(f"Successfully deleted file with ID: {file_id}")
        return True
    except Exception as e:
        print(f"Error deleting image from Google Drive (URL: {image_url}): {e}")
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
                    url = upload_image_to_drive(customer_image.stream, customer_image.filename)
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
    Handles customer data search.
    Requires user to be logged in.
    """
    if 'username' not in session:
        flash('กรุณาเข้าสู่ระบบก่อน', 'error')
        return redirect(url_for('login'))
    
    logged_in_user = session['username']
    
    search_keyword = request.args.get('search_keyword', '').strip()
    customer_records = []
    
    if search_keyword: # Only perform search if a keyword is provided
        worksheet = get_customer_data_worksheet()

        if worksheet:
            try:
                # Get all values (including header) to get row index
                all_values = worksheet.get_all_values()
                
                if len(all_values) > 1: # Check if there's data beyond headers
                    headers = all_values[0]
                    data_rows = all_values[1:] # Exclude header row
                    
                    # Convert data_rows to list of dicts, including row_index
                    # row_index in gspread is 1-based, so for data_rows[i] it's i + 2 (1 for 1-based, 1 for header)
                    
                    # Filter records based on search keyword
                    filtered_records_raw = []
                    for i, row_values in enumerate(data_rows):
                        record_dict = dict(zip(headers, row_values))
                        # Add row_index to the dictionary (1-based sheet row number)
                        record_dict['row_index'] = i + 2 
                        
                        # Check if keyword exists in any of the searchable columns
                        found_match = False
                        search_columns = ['ชื่อ', 'นามสกุล', 'เบอร์มือถือ', 'เลขบัตรประชาชน', 'ชื่อกิจการ']
                        for col in search_columns:
                            if col in record_dict and search_keyword.lower() in str(record_dict[col]).lower():
                                found_match = True
                                break
                        
                        if found_match:
                            customer_records.append(record_dict)
                    
                    if not customer_records:
                        flash('ไม่พบข้อมูลลูกค้าที่ตรงกับเงื่อนไขการค้นหา', 'info')
                else:
                    flash('ยังไม่มีข้อมูลลูกค้าในระบบ', 'info')

            except Exception as e:
                flash(f'เกิดข้อผิดพลาดในการดึงข้อมูลลูกค้า: {e}', 'error')
                print(f"Error fetching customer data for search: {e}")
        else:
            flash('ไม่สามารถเข้าถึง Google Sheet สำหรับค้นหาข้อมูลลูกค้าได้', 'error')
    # else: If no search_keyword, customer_records remains empty, so no results are displayed initially

    return render_template('search_data.html', 
                           username=logged_in_user, 
                           customer_records=customer_records,
                           search_keyword=search_keyword) # Pass search_keyword back to pre-fill form

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
            delete_image_from_drive(url_to_delete) # This function needs to be implemented

        # Handle new image uploads
        new_image_urls = []
        if 'new_customer_images' in request.files:
            files = request.files.getlist('new_customer_images')
            for new_image in files:
                if new_image and new_image.filename:
                    url = upload_image_to_drive(new_image.stream, new_image.filename)
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

# NEW: Route for proxying images from Google Drive to bypass CORS
@app.route('/proxy_image')
def proxy_image():
    image_url = request.args.get('image_url')
    if not image_url:
        return "Missing image_url parameter", 400

    try:
        # Fetch the image from Google Drive
        response = requests.get(image_url, stream=True)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

        # Get content type from Google Drive's response
        content_type = response.headers.get('Content-Type', 'application/octet-stream')
        
        # Return the image content directly to the browser
        return Response(response.iter_content(chunk_size=1024), mimetype=content_type)
    except requests.exceptions.RequestException as e:
        print(f"Error proxying image from {image_url}: {e}")
        return "Error loading image", 500


# Route for deleting an image from Google Drive and updating the sheet
# This route is no longer directly called by the JS, but the delete_image_from_drive function is used
# when the edit form is submitted.
@app.route('/delete_image/<int:row_index>/<path:image_url_encoded>', methods=['POST'])
def delete_image_route(row_index, image_url_encoded):
    # This route is kept for completeness, but the actual deletion logic is now handled
    # within the POST request of /edit_customer_data/<int:row_index>
    # The 'image_url_encoded' from the path is not directly used here, but the image_url
    # is expected from request.form.get('image_url') if this route were to be called directly.
    flash("การลบรูปภาพถูกจัดการผ่านหน้าแก้ไขข้อมูลแล้ว", "info")
    return redirect(url_for('edit_customer_data', row_index=row_index))


# --- Main execution block ---
if __name__ == '__main__':
    # Run the Flask application.
    # debug=True: Enables debug mode, which provides helpful error messages and auto-reloads the server on code changes.
    # host='0.0.0.0': This is crucial! It tells the Flask server to listen on all available public IPs.
    #                 This allows you to access the web app from other devices on your local network (like your phone).
    #                 Without this, it would only be accessible from 127.0.0.1 (localhost) on your computer.
    app.run(host='0.0.0.0', port=5000, debug=True)

