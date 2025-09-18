# -*- coding: utf-8 -*-
import os
import logging
from dotenv import load_dotenv
 
# REVISED: Explicitly load the .env file from the project's root directory.
# This makes the app's configuration more robust and independent of the current working directory.
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=dotenv_path)
from datetime import datetime, timedelta, UTC
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, Response, jsonify, current_app
from flask_caching import Cache

# NEW: Import password hashing utilities
from werkzeug.security import check_password_hash, generate_password_hash
import pandas as pd
import numpy as np

# NEW: SQLAlchemy and database imports
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_, and_

# NEW: Cloudinary for image uploads
import cloudinary
import cloudinary.uploader
import cloudinary.api

# =================================================================================
# FLASK APP INITIALIZATION AND CONFIGURATION
# =================================================================================

app = Flask(__name__)

# --- Secret Key Configuration ---
# IMPORTANT: Set this in your environment variables for production
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("No SECRET_KEY set for Flask application. Please set it in your environment variables.")
app.secret_key = SECRET_KEY

# --- Logging Configuration ---
# This sets up a file-based logger which is crucial for debugging on a server.
if not app.debug:
    # Create a directory for logs if it doesn't exist
    if not os.path.exists('logs'):
        os.mkdir('logs')
    
    # Set up a rotating file handler
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler('logs/customer_app.log', maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Customer App startup')

# --- Database Configuration (MySQL with SQLAlchemy) ---
DB_USER = os.environ.get('DB_USER', 'root')
DB_PASSWORD = os.environ.get('DB_PASSWORD') # It's better to not have a default password
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_NAME = os.environ.get('DB_NAME', 'loan_system')

if not DB_PASSWORD:
    raise ValueError("No DB_PASSWORD set for Flask application. Please set it in your environment variables.")

app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}?charset=utf8mb4'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_recycle': 280} # Prevents connection timeouts

# --- Cloudinary Configuration ---
cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
    secure=True
)

db = SQLAlchemy(app)

# --- Cache Configuration ---
# To fix the DeprecationWarning, we use the full path to the backend class.
cache = Cache(app, config={
    'CACHE_TYPE': 'flask_caching.backends.SimpleCache', 
    'CACHE_DEFAULT_TIMEOUT': 300
})


# =================================================================================
# DATABASE MODELS (Replaces Google Sheets Structure)
# =================================================================================

class CustomerRecord(db.Model):
    __tablename__ = 'customer_records'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    customer_id = db.Column(db.String(50), unique=True, nullable=False)
    first_name = db.Column(db.String(255))
    last_name = db.Column(db.String(255))
    id_card_number = db.Column(db.String(100))
    mobile_phone = db.Column(db.String(100))
    main_customer_group = db.Column(db.String(255))
    sub_profession_group = db.Column(db.String(255))
    other_sub_profession = db.Column(db.Text)
    is_registered = db.Column(db.String(50))
    business_name = db.Column(db.String(255))
    province = db.Column(db.String(255))
    registered_address = db.Column(db.Text)
    status = db.Column(db.String(100))
    desired_credit_limit = db.Column(db.DECIMAL(15, 2))
    approved_credit_limit = db.Column(db.DECIMAL(15, 2))
    applied_before = db.Column(db.String(1000))
    check_status = db.Column(db.String(50))
    application_channel = db.Column(db.String(255))
    assigned_company = db.Column(db.String(255))
    upfront_interest_deduction = db.Column(db.DECIMAL(15, 2))
    processing_fee = db.Column(db.DECIMAL(15, 2))
    application_date = db.Column(db.Date)
    home_location_link = db.Column(db.Text)
    work_location_link = db.Column(db.Text)
    remarks = db.Column(db.Text)
    image_urls = db.Column(db.Text)
    logged_in_user = db.Column(db.String(100))
    inspection_date = db.Column(db.Date)
    inspection_time = db.Column(db.Time)
    inspector = db.Column(db.String(255))

    # NEW: Add a Full-Text Search index for faster, more relevant text searching.
    __table_args__ = (
        db.Index('ix_customer_records_fulltext', 'first_name', 'last_name', 'business_name', 'remarks', mysql_prefix='FULLTEXT'),
    )

    def to_dict(self):
        """Converts the object to a dictionary, matching the old Google Sheet format."""
        return {
            'row_index': self.id, # Use DB id as the unique row identifier
            'Timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S') if self.timestamp else '',
            'Customer ID': self.customer_id,
            'ชื่อ': self.first_name,
            'นามสกุล': self.last_name,
            'เลขบัตรประชาชน': self.id_card_number,
            'เบอร์มือถือ': self.mobile_phone,
            'กลุ่มลูกค้าหลัก': self.main_customer_group,
            'กลุ่มอาชีพย่อย': self.sub_profession_group,
            'ระบุอาชีพย่อยอื่นๆ': self.other_sub_profession,
            'จดทะเบียน': self.is_registered,
            'ชื่อกิจการ': self.business_name,
            'จังหวัดที่อยู่': self.province,
            'ที่อยู่จดทะเบียน': self.registered_address,
            'สถานะ': self.status,
            'วงเงินที่ต้องการ': self.desired_credit_limit,
            'วงเงินที่อนุมัติ': self.approved_credit_limit,
            'เคยขอเข้ามาในเครือหรือยัง': self.applied_before,
            'เช็ค': self.check_status,
            'ขอเข้ามาทางไหน': self.application_channel,
            'บริษัทที่รับงาน': self.assigned_company,
            'หักดอกหัวท้าย': self.upfront_interest_deduction,
            'ค่าดำเนินการ': self.processing_fee,
            'วันที่ขอเข้ามา': self.application_date.strftime('%Y-%m-%d') if self.application_date else '',
            'ลิงค์โลเคชั่นบ้าน': self.home_location_link,
            'ลิงค์โลเคชั่นที่ทำงาน': self.work_location_link,
            'หมายเหตุ': self.remarks,
            'Image URLs': self.image_urls,
            'Logged In User': self.logged_in_user,
            'วันที่นัดตรวจ': self.inspection_date.strftime('%Y-%m-%d') if self.inspection_date else '',
            'เวลานัดตรวจ': self.inspection_time.strftime('%H:%M:%S') if self.inspection_time else '',
            'ผู้รับงานตรวจ': self.inspector
        }

class User(db.Model):
    __tablename__ = 'users'
    user_id = db.Column('id', db.String(100), primary_key=True)
    password = db.Column(db.String(255), nullable=False)

class Approval(db.Model):
    __tablename__ = 'approvals'
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(100))
    customer_id = db.Column(db.String(50))
    full_name = db.Column(db.String(255))
    phone_number = db.Column(db.String(100))
    approval_date = db.Column(db.Date)
    approved_amount = db.Column(db.DECIMAL(15, 2))
    assigned_company = db.Column(db.String(255))
    registrar = db.Column(db.String(255))
    contract_image_urls = db.Column(db.Text)

class BadDebtRecord(db.Model):
    __tablename__ = 'bad_debt_records'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    customer_id = db.Column(db.String(50))
    customer_name = db.Column(db.String(255))
    phone = db.Column(db.String(100))
    approved_amount = db.Column(db.DECIMAL(15, 2))
    outstanding_balance = db.Column(db.DECIMAL(15, 2))
    marked_by = db.Column(db.String(100))
    notes = db.Column(db.Text)

class PullPlugRecord(db.Model):
    __tablename__ = 'pull_plug_records'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    customer_id = db.Column(db.String(50))
    customer_name = db.Column(db.String(255))
    phone = db.Column(db.String(100))
    pull_plug_amount = db.Column(db.DECIMAL(15, 2))
    marked_by = db.Column(db.String(100))
    notes = db.Column(db.Text)

class ReturnPrincipalRecord(db.Model):
    __tablename__ = 'return_principal_records'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    customer_id = db.Column(db.String(50))
    customer_name = db.Column(db.String(255))
    phone = db.Column(db.String(100))
    return_amount = db.Column(db.DECIMAL(15, 2))
    marked_by = db.Column(db.String(100))
    notes = db.Column(db.Text)

class AllPidJob(db.Model):
    __tablename__ = 'all_pid_jobs'
    id = db.Column(db.Integer, primary_key=True)
    transaction_date = db.Column(db.Date)
    company_name = db.Column(db.String(255))
    customer_id = db.Column(db.String(50))
    transaction_time = db.Column(db.Time)
    customer_name = db.Column(db.String(255))
    interest = db.Column(db.DECIMAL(15, 2))
    table1_opening_balance = db.Column(db.DECIMAL(15, 2), default=0)
    table1_net_opening = db.Column(db.DECIMAL(15, 2), default=0)
    table1_principal_returned = db.Column(db.DECIMAL(15, 2), default=0)
    table1_lost_amount = db.Column(db.DECIMAL(15, 2), default=0)
    table2_opening_balance = db.Column(db.DECIMAL(15, 2), default=0)
    table2_net_opening = db.Column(db.DECIMAL(15, 2), default=0)
    table2_principal_returned = db.Column(db.DECIMAL(15, 2), default=0)
    table2_lost_amount = db.Column(db.DECIMAL(15, 2), default=0)
    table3_opening_balance = db.Column(db.DECIMAL(15, 2), default=0)
    table3_net_opening = db.Column(db.DECIMAL(15, 2), default=0)
    table3_principal_returned = db.Column(db.DECIMAL(15, 2), default=0)
    table3_lost_amount = db.Column(db.DECIMAL(15, 2), default=0)
    main_assigned_company = db.Column(db.String(255))

    def to_dict(self):
        """Converts the AllPidJob object to a dictionary for API responses."""
        return {
            'Date': self.transaction_date.strftime('%Y-%m-%d') if self.transaction_date else None,
            'CompanyName': self.company_name,
            'CustomerID': self.customer_id,
            'Time': self.transaction_time.strftime('%H:%M:%S') if self.transaction_time else None,
            'CustomerName': self.customer_name,
            'บริษัทที่รับงาน': self.main_assigned_company,
            'interest': float(self.interest) if self.interest is not None else None,
            'Table1_OpeningBalance': float(self.table1_opening_balance) if self.table1_opening_balance is not None else None,
            'Table1_NetOpening': float(self.table1_net_opening) if self.table1_net_opening is not None else None,
            'Table1_PrincipalReturned': float(self.table1_principal_returned) if self.table1_principal_returned is not None else None,
            'Table1_LostAmount': float(self.table1_lost_amount) if self.table1_lost_amount is not None else None,
            'Table2_OpeningBalance': float(self.table2_opening_balance) if self.table2_opening_balance is not None else None,
            'Table2_NetOpening': float(self.table2_net_opening) if self.table2_net_opening is not None else None,
            'Table2_PrincipalReturned': float(self.table2_principal_returned) if self.table2_principal_returned is not None else None,
            'Table2_LostAmount': float(self.table2_lost_amount) if self.table2_lost_amount is not None else None,
            'Table3_OpeningBalance': float(self.table3_opening_balance) if self.table3_opening_balance is not None else None,
            'Table3_NetOpening': float(self.table3_net_opening) if self.table3_net_opening is not None else None,
            'Table3_PrincipalReturned': float(self.table3_principal_returned) if self.table3_principal_returned is not None else None,
            'Table3_LostAmount': float(self.table3_lost_amount) if self.table3_lost_amount is not None else None,
        }

class ContractDocument(db.Model):
    __tablename__ = 'contract_documents'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.String(50))
    document_url = db.Column(db.Text)
    uploaded_by = db.Column(db.String(100))
    upload_timestamp = db.Column(db.DateTime, default=lambda: datetime.now(UTC))


# =================================================================================
# AUTHENTICATION & DECORATORS
# =================================================================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            # REVISED: Check if the request is an API call (expecting JSON).
            # If so, return a 401 Unauthorized error in JSON format instead of redirecting.
            # This prevents the "Unexpected token '<'" error on the frontend.
            is_api_request = request.path.startswith('/api/') or request.is_json
            
            if is_api_request:
                return jsonify(error="Authentication required. Your session may have expired.", login_url=url_for('login')), 401
            else:
                # For regular page loads, flash a message and redirect to the login page.
                flash('กรุณาเข้าสู่ระบบก่อน', 'danger')
                return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# REFACTORED: Now loads users from the database
@cache.cached(timeout=60, key_prefix='user_login_data')
def load_users():
    """Loads users from the MySQL database."""
    try:
        all_users = User.query.all()
        return {user.user_id: user.password for user in all_users}
    except Exception as e:
        current_app.logger.error(f"Error loading users from database: {e}")
        return {}

# =================================================================================
# HELPER FUNCTIONS (DATA ACCESS LAYER - REFACTORED FOR MYSQL)
# =================================================================================

# REFACTORED: This function now queries the database
def get_all_customer_records():
    """Fetches all customer records from the database and returns them as a list of dicts."""
    try:
        records = CustomerRecord.query.order_by(CustomerRecord.timestamp.desc()).all()
        # Convert SQLAlchemy objects to dictionaries to maintain compatibility with templates
        return [record.to_dict() for record in records]
    except Exception as e:
        current_app.logger.error(f"Error fetching customer records: {e}")
        return []

# REFACTORED: Generates next ID based on the database's max ID.
def generate_next_customer_id():
    """Generates a new numeric customer ID based on the last ID in the database."""
    try:
        # This query finds the highest numeric ID by casting the column to an integer.
        # This is more robust than string parsing.
        last_id_scalar = db.session.query(func.max(func.cast(CustomerRecord.customer_id, db.Integer))).scalar()
        
        # If no records exist, start from 1001. Otherwise, take the last number and add 1.
        next_id_num = (last_id_scalar or 1000) + 1
        return f"{next_id_num}"

    except Exception as e:
        current_app.logger.error(f"Error generating next customer ID: {e}")
        # Fallback to a timestamp-based ID to avoid collision
        return f"ERR-{int(datetime.now().timestamp())}"

# NEW HELPER: Get a single customer by their database ID
def get_customer_by_db_id(record_id):
    try:
        return db.session.get(CustomerRecord, record_id)
    except Exception as e:
        current_app.logger.error(f"Error getting customer by DB id {record_id}: {e}")
        return None

# NEW HELPER: Get a single customer by their Customer ID (PID-xxxx)
def get_customer_by_customer_id(customer_id):
    try:
        return CustomerRecord.query.filter_by(customer_id=customer_id).first()
    except Exception as e:
        current_app.logger.error(f"Error getting customer by customer_id {customer_id}: {e}")
        return None

def get_records_from_model(model_class):
    """Generic function to fetch all records from any given model."""
    try:
        records = model_class.query.order_by(model_class.id.desc()).all()
        # This generic version returns objects. Specific conversion to dict may be needed if used in templates.
        return records
    except Exception as e:
        current_app.logger.error(f"Error fetching records from {model_class.__tablename__}: {e}")
        return []

# =================================================================================
# FLASK ROUTES
# =================================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password_candidate = request.form['password']
        
        # REFACTORED: Query for a single user instead of loading all users.
        # This is much more efficient and secure.
        user = User.query.filter_by(user_id=username).first()

        # REFACTORED: Use check_password_hash to securely compare passwords.
        if user and check_password_hash(user.password, password_candidate):
            session['logged_in'] = True
            session['username'] = username
            flash('เข้าสู่ระบบสำเร็จ', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('ออกจากระบบแล้ว', 'success')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard(): # <-- แก้ชื่อฟังก์ชันตรงนี้
    return render_template('main_menu.html')

@app.route('/customer_data')
@login_required
@cache.cached(timeout=30, key_prefix='customer_data_view')
def customer_data():
    all_records = get_all_customer_records()
    return render_template('customer_data.html', customer_records=all_records)

# REFACTORED: Search now uses efficient database queries
@app.route('/search_customer_data', methods=['GET'])
@login_required
def search_customer_data():
    search_keyword = request.args.get('search_keyword', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 15  # Number of items per page

    results = []
    pagination = None
    display_title = "แสดงข้อมูลลูกค้าทั้งหมด"

    try:
        base_query = CustomerRecord.query

        if search_keyword:
            display_title = f"ผลการค้นหาสำหรับ: '{search_keyword}'"
            like_term = f"%{search_keyword}%"
            
            # REVISED: Use a universal LIKE search for all databases.
            # This avoids potential errors from MySQL-specific FULLTEXT search if the index is not set up correctly.
            # This method is more robust and works across different environments (like testing with SQLite).
            search_filter = or_(
                CustomerRecord.customer_id.ilike(like_term),
                CustomerRecord.first_name.ilike(like_term),
                CustomerRecord.last_name.ilike(like_term),
                CustomerRecord.mobile_phone.ilike(like_term),
                CustomerRecord.id_card_number.ilike(like_term),
                CustomerRecord.business_name.ilike(like_term),
                CustomerRecord.remarks.ilike(like_term)
            )
            base_query = base_query.filter(search_filter)
        
        pagination = base_query.order_by(CustomerRecord.timestamp.desc()).paginate(page=page, per_page=per_page, error_out=False)
        results_obj = pagination.items
        results = [record.to_dict() for record in results_obj]

        if not results and search_keyword:
            flash('ไม่พบข้อมูลที่ตรงกับเงื่อนไขการค้นหา', 'info')

    except Exception as e:
        current_app.logger.error(f"Error during search for '{search_keyword}': {e}")
        flash('เกิดข้อผิดพลาดระหว่างการค้นหา', 'danger')

    return render_template('search_data.html', customer_records=results, search_keyword=search_keyword, display_title=display_title, username=session.get('username'), pagination=pagination)

# REFACTORED: Uses SQLAlchemy to add a new record
@app.route('/enter_customer_data', methods=['GET', 'POST'])
@login_required
def enter_customer_data():
    if request.method == 'POST':
        try:
            new_customer_id = generate_next_customer_id()
            inspection_time_str = request.form.get('inspection_time')
            inspection_time_obj = None
            if inspection_time_str:
                try:
                    inspection_time_obj = datetime.strptime(inspection_time_str, '%H:%M').time()
                except ValueError:
                    # Handle case where time is not in HH:MM format, maybe log it
                    pass
            
            # REVISED: Add data validation and cleaning for numeric fields to prevent crashes
            def clean_decimal(value):
                if value is None or value.strip() == '':
                    return None
                # Remove commas and convert to numeric, return None if it fails
                return pd.to_numeric(str(value).replace(',', ''), errors='coerce')

            new_customer = CustomerRecord(
                timestamp=datetime.now(),
                customer_id=new_customer_id,
                first_name=request.form.get('customer_name', '').strip(),
                last_name=request.form.get('last_name', '').strip(),
                id_card_number=request.form.get('id_card_number') or None,
                mobile_phone=request.form.get('mobile_phone_number') or None,
                main_customer_group=request.form.get('main_customer_group') or None,
                sub_profession_group=request.form.get('sub_profession_group') or None,
                other_sub_profession=request.form.get('other_sub_profession') or None,
                is_registered=request.form.get('registered') or None,
                business_name=request.form.get('business_name') or None,
                province=request.form.get('province') or None,
                registered_address=request.form.get('registered_address') or None,
                status=request.form.get('status', 'รอติดต่อ'),
                desired_credit_limit=clean_decimal(request.form.get('desired_credit_limit')),
                approved_credit_limit=clean_decimal(request.form.get('approved_credit_limit')),
                applied_before=request.form.get('applied_before') or None,
                check_status=request.form.get('check') or None,
                application_channel=request.form.get('how_applied') or None,
                assigned_company=request.form.get('assigned_company') or None,
                upfront_interest_deduction=clean_decimal(request.form.get('upfront_interest')),
                processing_fee=clean_decimal(request.form.get('processing_fee')),
                application_date=request.form.get('application_date') or None,
                home_location_link=request.form.get('home_location_link') or None,
                work_location_link=request.form.get('work_location_link') or None,
                remarks=request.form.get('remarks') or None,
                image_urls=request.form.get('image_urls') or None,
                logged_in_user=session.get('username', 'unknown'),
                inspection_date=request.form.get('inspection_date') or None,
                inspection_time=inspection_time_obj,
                inspector=request.form.get('inspector')
            )
            db.session.add(new_customer)
            db.session.commit()
            
            cache.delete('customer_data_view') # Clear cache after adding new data
            # flash(f'บันทึกข้อมูลลูกค้า {new_customer_id} เรียบร้อยแล้ว!', 'success')
            return jsonify({'success': True, 'message': f'บันทึกข้อมูลลูกค้า {new_customer_id} เรียบร้อยแล้ว!', 'customer_id': new_customer_id})
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error saving new customer data: {e}")
            return jsonify({'success': False, 'message': f'เกิดข้อผิดพลาด: {e}'}), 500

    return render_template('data_entry.html', username=session.get('username'))

# REFACTORED: Fetches data from DB to populate the edit form
@app.route('/edit_customer_data/<int:record_id>', methods=['GET', 'POST'])
@login_required
def edit_customer_data(record_id):
    customer = get_customer_by_db_id(record_id)
    if not customer:
        flash('ไม่พบข้อมูลลูกค้า', 'danger')
        return redirect(url_for('search_customer_data'))

    if request.method == 'POST':
        try:
            # --- NEW: Get original status before making changes ---
            original_status = customer.status
            new_status = request.form.get('status', customer.status)

            # Update customer object with form data
            customer.first_name = request.form.get('customer_name', customer.first_name).strip()
            customer.last_name = request.form.get('last_name', customer.last_name).strip()
            customer.id_card_number = request.form.get('id_card_number', customer.id_card_number)
            customer.mobile_phone = request.form.get('mobile_phone_number', customer.mobile_phone)
            customer.main_customer_group = request.form.get('main_customer_group', customer.main_customer_group)
            
            sub_profession_group = request.form.get('sub_profession_group')
            other_sub_profession = request.form.get('other_sub_profession')
            # REVISED: Clear the 'other' field if a standard option is chosen to maintain data integrity.
            if sub_profession_group == 'อื่นๆ':
                # When 'Other' is selected, use the text input for both fields.
                customer.sub_profession_group = other_sub_profession 
                customer.other_sub_profession = other_sub_profession
            else:
                customer.sub_profession_group = sub_profession_group
                customer.other_sub_profession = None # Clear the custom field if not used.

            customer.is_registered = request.form.get('registered', customer.is_registered)
            customer.business_name = request.form.get('business_name', customer.business_name)
            customer.province = request.form.get('province', customer.province)
            customer.registered_address = request.form.get('registered_address', customer.registered_address)
            customer.status = new_status # Apply the new status
            
            # REVISED: Apply the same robust data cleaning from the data entry form to prevent crashes.
            def clean_decimal(value):
                if value is None or str(value).strip() == '':
                    return None
                # Remove commas and convert to numeric, return None if it fails
                return pd.to_numeric(str(value).replace(',', ''), errors='coerce')

            customer.desired_credit_limit = clean_decimal(request.form.get('desired_credit_limit', customer.desired_credit_limit))
            customer.approved_credit_limit = clean_decimal(request.form.get('approved_credit_limit', customer.approved_credit_limit))
            
            customer.applied_before = request.form.get('applied_before', customer.applied_before)
            customer.check_status = request.form.get('check', customer.check_status)
            customer.application_channel = request.form.get('how_applied', customer.application_channel)
            customer.assigned_company = request.form.get('assigned_company', customer.assigned_company)
            
            customer.upfront_interest_deduction = clean_decimal(request.form.get('upfront_interest', customer.upfront_interest_deduction))
            customer.processing_fee = clean_decimal(request.form.get('processing_fee', customer.processing_fee))
            
            application_date_str = request.form.get('application_date')
            if application_date_str:
                customer.application_date = datetime.strptime(application_date_str, '%Y-%m-%d').date()

            customer.home_location_link = request.form.get('home_location_link', customer.home_location_link)
            customer.work_location_link = request.form.get('work_location_link', customer.work_location_link)
            customer.remarks = request.form.get('remarks', customer.remarks)
            
            customer.inspector = request.form.get('inspector', customer.inspector)

            inspection_date_str = request.form.get('inspection_date')
            customer.inspection_date = datetime.strptime(inspection_date_str, '%Y-%m-%d').date() if inspection_date_str else None
            
            inspection_time_str = request.form.get('inspection_time')
            if inspection_time_str:
                # REVISED: Handle both 'HH:MM' and 'HH:MM:SS' formats from the time input
                time_format = '%H:%M:%S' if len(inspection_time_str) > 5 else '%H:%M'
                customer.inspection_time = datetime.strptime(inspection_time_str, time_format).time()
            else:
                customer.inspection_time = None
                
            # --- REVISED: Handle image deletion and updates ---
            # 1. Delete images marked for removal from Cloudinary
            deleted_urls_str = request.form.get('deleted_image_urls', '')
            if deleted_urls_str:
                deleted_urls = [url.strip() for url in deleted_urls_str.split(',') if url.strip()]
                for url in deleted_urls:
                    try:
                        # Extract public_id from URL and delete from Cloudinary
                        public_id_with_folder = '/'.join(url.split('/')[-2:])
                        public_id = os.path.splitext(public_id_with_folder)[0]
                        cloudinary.uploader.destroy(public_id)
                        current_app.logger.info(f"Successfully deleted image {public_id} from Cloudinary.")
                    except Exception as cloudinary_error:
                        current_app.logger.warning(f"Could not delete image from Cloudinary for URL {url}: {cloudinary_error}")
            # 2. Save the final list of URLs (kept + new) to the database
            customer.image_urls = request.form.get('final_image_urls', customer.image_urls)

            # --- NEW: Logic to create an Approval record when status is changed to 'อนุมัติ' ---
            if new_status == 'อนุมัติ' and original_status != 'อนุมัติ':
                # Check if an approval record already exists to prevent duplicates
                existing_approval = Approval.query.filter_by(customer_id=customer.customer_id).first()
                if not existing_approval:
                    new_approval = Approval(
                        status='รอปิดจ๊อบ',  # Initial status for loan management
                        customer_id=customer.customer_id,
                        full_name=f"{customer.first_name} {customer.last_name}",
                        phone_number=customer.mobile_phone,
                        approval_date=datetime.now().date(), # Use current date for approval
                        approved_amount=customer.approved_credit_limit,
                        assigned_company=customer.assigned_company,
                        registrar=session.get('username'),
                        contract_image_urls=customer.image_urls # Copy image URLs for reference
                    )
                    db.session.add(new_approval)
                    flash('สร้างรายการอนุมัติในหน้าจัดการสินเชื่อเรียบร้อยแล้ว', 'info')

            db.session.commit()
            cache.clear() # Clear all cache after an edit
            flash('อัปเดตข้อมูลลูกค้าสำเร็จ', 'success')
            return redirect(url_for('search_customer_data'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating customer {record_id}: {e}")
            flash(f'เกิดข้อผิดพลาดในการอัปเดตข้อมูล: {e}', 'danger')

    # For GET request, pass the customer object to the template
    # The template expects a dictionary, so we convert the object
    customer_dict = customer.to_dict()
    customer_dict['existing_image_urls'] = [url.strip() for url in (customer.image_urls or '').split(',') if url.strip()]
    return render_template('edit_customer_data.html', customer_data=customer_dict, row_index=record_id, username=session.get('username'))


@app.route('/loan_management')
@login_required
def loan_management():
    """Displays the loan management page with active loan records."""
    try:
        # Fetch records from the 'approvals' table.
        approvals_obj = Approval.query.order_by(Approval.approval_date.desc()).all()
        
        # Convert SQLAlchemy objects to a list of dictionaries for the template
        approvals_list = []
        for record in approvals_obj:
            approvals_list.append({
                'id': record.id,
                'สถานะ': record.status,
                'Customer ID': record.customer_id,
                'ชื่อ-นามสกุล': record.full_name,
                'หมายเลขโทรศัพท์': record.phone_number,
                'วันที่อนุมัติ': record.approval_date.strftime('%Y-%m-%d') if record.approval_date else '',
                'วงเงินที่อนุมัติ': f"{record.approved_amount:,.2f}" if record.approved_amount is not None else '-',
                'บริษัทที่รับงาน': record.assigned_company,
                'ชื่อผู้ลงทะเบียน': record.registrar
            })
        return render_template('loan_management.html', approove=approvals_list, username=session.get('username'))
    except Exception as e:
        current_app.logger.error(f"Error fetching data for loan management: {e}")
        flash('เกิดข้อผิดพลาดในการโหลดข้อมูลจัดการสินเชื่อ', 'danger')
        return render_template('loan_management.html', approove=[], username=session.get('username'))


# REFACTORED: Uses database ID for deletion
@app.route('/delete_customer/<int:record_id>', methods=['POST'])
@login_required
def delete_customer(record_id):
    customer = get_customer_by_db_id(record_id)
    if customer:
        try:
            db.session.delete(customer)
            db.session.commit()
            cache.clear()
            flash(f'ลบข้อมูลลูกค้า {customer.customer_id} สำเร็จ', 'success')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error deleting customer {record_id}: {e}")
            flash(f'เกิดข้อผิดพลาดในการลบข้อมูล: {e}', 'danger')
    else:
        flash('ไม่พบข้อมูลลูกค้าที่จะลบ', 'danger')
    return redirect(url_for('search_customer_data'))


# The following routes for approove, bad_debt etc. need to be refactored
# in a similar way as the customer_data routes.
# Here is an example for one of them:

@app.route('/approove')
@login_required
def approove():
    approvals = get_records_from_model(Approval)
    return render_template('approove.html', approove_records=approvals)

@app.route('/bad_debt_records')
@login_required
def bad_debt_records_view():
    records = get_records_from_model(BadDebtRecord)
    return render_template('bad_debt_records.html', bad_debt_records=records)

@app.route('/pull_plug_records')
@login_required
def pull_plug_records_view():
    records = get_records_from_model(PullPlugRecord)
    return render_template('pull_plug_records.html', pull_plug_records=records)

@app.route('/return_principal_records')
@login_required
def return_principal_records_view():
    records = get_records_from_model(ReturnPrincipalRecord)
    return render_template('return_principal_records.html', return_principal_records=records)

# =================================================================================
# API & DYNAMIC CONTENT ROUTES
# =================================================================================

@app.route('/get-customer-info/<customer_id>', methods=['GET'])
@login_required
def get_customer_info(customer_id):
    """
    API endpoint to fetch detailed information for a customer who has been approved.
    This is used by the 'View Info' modal in loan management.
    """
    try:
        # 1. ค้นหาข้อมูลการอนุมัติของลูกค้า
        approval_record = Approval.query.filter_by(customer_id=customer_id).first()

        if not approval_record:
            return jsonify({'error': 'ไม่พบข้อมูลการอนุมัติสำหรับลูกค้านี้'}), 404

        # 2. ค้นหาเอกสารสัญญาทั้งหมดที่เกี่ยวข้อง
        contract_docs = ContractDocument.query.filter_by(customer_id=customer_id).order_by(ContractDocument.upload_timestamp.asc()).all()
        image_urls = [doc.document_url for doc in contract_docs]
        image_urls_str = ','.join(image_urls) if image_urls else '-'

        # 3. สร้างข้อมูลสำหรับส่งกลับไปในรูปแบบที่ Frontend ต้องการ
        customer_info = {
            'Customer ID': approval_record.customer_id,
            'ชื่อ-นามสกุล': approval_record.full_name,
            'สถานะ': approval_record.status,
            'หมายเลขโทรศัพท์': approval_record.phone_number,
            'วันที่อนุมัติ': approval_record.approval_date.strftime('%Y-%m-%d') if approval_record.approval_date else '-',
            'วงเงินที่อนุมัติ': f"{approval_record.approved_amount:,.2f}" if approval_record.approved_amount is not None else '-',
            'ชื่อผู้ลงทะเบียน': approval_record.registrar,
            'รูปถ่ายสัญญา': image_urls_str
        }

        return jsonify(customer_info)

    except Exception as e:
        current_app.logger.error(f"Error fetching info for customer_id {customer_id}: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาดในเซิร์ฟเวอร์'}), 500

@app.route('/upload_contract_docs', methods=['POST'])
@login_required
def upload_contract_docs():
    """
    API endpoint to upload contract document images for a specific customer.
    Handles multiple file uploads and saves them to Cloudinary and the database.
    """
    if 'contract_files[]' not in request.files:
        return jsonify({'success': False, 'error': 'No files selected for upload'}), 400

    files = request.files.getlist('contract_files[]')
    customer_id = request.form.get('customer_id')
    username = session.get('username')

    if not customer_id:
        return jsonify({'success': False, 'error': 'Customer ID is missing'}), 400
    
    if not files or files[0].filename == '':
        return jsonify({'success': False, 'error': 'No files selected for upload'}), 400

    errors = []

    try:
        for file in files:
            try:
                # Upload to Cloudinary
                upload_result = cloudinary.uploader.upload(
                    file,
                    folder="customer_app_images", # Same folder as in the signature API
                    transformation=[{'width': 1000, 'height': 1000, 'crop': 'limit'}] # Apply a transformation
                )
                
                # Create a new database record for the document
                new_doc = ContractDocument(
                    customer_id=customer_id,
                    document_url=upload_result['secure_url'],
                    uploaded_by=username
                )
                db.session.add(new_doc)
            except Exception as upload_error:
                current_app.logger.error(f"Error uploading file '{file.filename}' for customer {customer_id}: {upload_error}")
                errors.append(f"Could not upload file {file.filename}.")

        if errors:
            db.session.rollback()
            return jsonify({'success': False, 'error': '. '.join(errors)}), 500
        
        db.session.commit()
        return jsonify({'success': True, 'message': f'Successfully uploaded {len(files)} files.'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"General error in upload_contract_docs for customer {customer_id}: {e}")
        return jsonify({'success': False, 'error': 'An unexpected server error occurred.'}), 500

@app.route('/api/customer-balance/<customer_id>', methods=['GET'])
@login_required
def get_customer_balance(customer_id):
    """
    Calculates the total outstanding balance for a customer from the all_pid_jobs table.
    This is the sum of money given out minus the sum of money returned.
    """
    try:
        # Sum up all the amounts that represent money given out
        total_given_out = db.session.query(
            func.sum(
                func.coalesce(AllPidJob.table1_opening_balance, 0) +
                func.coalesce(AllPidJob.table1_net_opening, 0) +
                func.coalesce(AllPidJob.table2_opening_balance, 0) +
                func.coalesce(AllPidJob.table2_net_opening, 0) +
                func.coalesce(AllPidJob.table3_opening_balance, 0) +
                func.coalesce(AllPidJob.table3_net_opening, 0)
            )
        ).filter(AllPidJob.customer_id == customer_id).scalar() or 0

        # Sum up all the amounts that represent money returned
        total_returned = db.session.query(
            func.sum(
                func.coalesce(AllPidJob.table1_principal_returned, 0) +
                func.coalesce(AllPidJob.table2_principal_returned, 0) +
                func.coalesce(AllPidJob.table3_principal_returned, 0)
            )
        ).filter(AllPidJob.customer_id == customer_id).scalar() or 0
        
        outstanding_balance = total_given_out - total_returned

        return jsonify({'total_transactions_value': float(outstanding_balance)})

    except Exception as e:
        current_app.logger.error(f"Error calculating balance for customer_id {customer_id}: {e}")
        return jsonify({'error': 'Could not calculate balance'}), 500

@app.route('/save-approved-data', methods=['POST'])
@login_required
def save_approved_data():
    """
    Saves the 'close job' transaction data to the all_pid_jobs table
    and updates the customer's approval status.
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid data provided'}), 400

    customer_id = data.get('customer_id')
    transactions = data.get('transactions', [])

    if not customer_id or not transactions:
        return jsonify({'error': 'Missing customer ID or transactions'}), 400

    try:
        # 1. Update the approval status to 'ปิดจ๊อบแล้ว'
        approval_record = Approval.query.filter_by(customer_id=customer_id).first()
        if approval_record:
            approval_record.status = 'ปิดจ๊อบแล้ว'
        
        # REFACTORED: Use a mapping for safer and clearer attribute setting.
        # This prevents arbitrary attribute setting and makes the logic easier to follow.
        action_to_column_map = {
            'เปิดยอด': 'opening_balance',
            'เปิดสุทธิ': 'net_opening',
            'คืนต้น': 'principal_returned'
        }

        # 2. Add new records to AllPidJob for each transaction
        for trans in transactions:
            new_job = AllPidJob(transaction_date=datetime.now().date(), transaction_time=datetime.now().time(), company_name=trans.get('company'), customer_id=customer_id, customer_name=data.get('fullname'), interest=data.get('interest'), main_assigned_company=data.get('assigned_company'))
            
            action_type = trans.get('action_type')
            amount = trans.get('amount')
            table_number_str = trans.get('table_select', '').replace('โต๊ะ', '')

            # Validate the inputs before proceeding
            if table_number_str.isdigit() and action_type in action_to_column_map and amount is not None:
                table_number = int(table_number_str)
                column_suffix = action_to_column_map[action_type]
                # Construct the full attribute name, e.g., 'table1_opening_balance'
                attribute_name = f'table{table_number}_{column_suffix}'
                setattr(new_job, attribute_name, amount)

            db.session.add(new_job)
        db.session.commit()
        return jsonify({'success': True, 'message': 'บันทึกข้อมูลการปิดจ๊อบเรียบร้อยแล้ว'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving approved data for customer {customer_id}: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาดในเซิร์ฟเวอร์ขณะบันทึกข้อมูล'}), 500

@app.route('/api/daily-jobs', methods=['GET'])
@login_required
def get_daily_jobs():
    """
    API endpoint to fetch daily job transactions based on date and company.
    """
    search_date_str = request.args.get('date')
    search_company = request.args.get('company')

    if not search_date_str:
        return jsonify({'error': 'Date parameter is required'}), 400

    try:
        search_date = datetime.strptime(search_date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Please use YYYY-MM-DD.'}), 400

    try:
        query = AllPidJob.query.filter(AllPidJob.transaction_date == search_date)

        if search_company:
            query = query.filter(AllPidJob.company_name == search_company)

        results = query.order_by(AllPidJob.transaction_time).all()

        # REFACTORED: Use the new to_dict() method for cleaner code
        jobs_list = [job.to_dict() for job in results]
        return jsonify(jobs_list)

    except Exception as e:
        current_app.logger.error(f"Error fetching daily jobs: {e}")
        return jsonify({'error': 'An internal server error occurred'}), 500

@app.route('/delete_contract_doc', methods=['POST'])
@login_required
def delete_contract_doc():
    """
    API endpoint to delete a specific contract document image.
    It deletes the record from the database and the file from Cloudinary.
    """
    data = request.get_json()
    customer_id = data.get('customer_id')
    image_url = data.get('image_url_to_delete')

    if not customer_id or not image_url:
        return jsonify({'success': False, 'error': 'Missing customer ID or image URL'}), 400

    try:
        # Find the document in the database
        doc_to_delete = ContractDocument.query.filter_by(customer_id=customer_id, document_url=image_url).first()

        if not doc_to_delete:
            return jsonify({'success': False, 'error': 'Document not found in database'}), 404

        # Delete from Cloudinary by extracting the public_id from the URL
        # Example URL: https://res.cloudinary.com/<cloud_name>/image/upload/v12345/customer_app_images/public_id.jpg
        # The public_id for Cloudinary is 'customer_app_images/public_id'
        try:
            public_id_with_folder = '/'.join(image_url.split('/')[-2:])
            public_id = os.path.splitext(public_id_with_folder)[0]
            cloudinary.uploader.destroy(public_id)
        except Exception as cloudinary_error:
            # Log the error but continue to delete from DB, as the link is broken anyway
            current_app.logger.warning(f"Could not delete image from Cloudinary for URL {image_url}: {cloudinary_error}")

        # Delete from our database
        db.session.delete(doc_to_delete)
        db.session.commit()

        return jsonify({'success': True, 'message': 'ลบรูปภาพเรียบร้อยแล้ว'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting contract doc for customer {customer_id}: {e}")
        return jsonify({'success': False, 'error': 'เกิดข้อผิดพลาดในเซิร์ฟเวอร์'}), 500

# REFACTORED: Helper function to reduce duplication in status marking routes.
def _mark_status_and_log(customer_id, status_text, log_model, payload):
    """A generic helper to update an approval's status and create a corresponding log record."""
    approval = Approval.query.filter_by(customer_id=customer_id).first()
    if not approval:
        raise ValueError(f'Approval record not found for customer {customer_id}')
    
    approval.status = status_text

    log_data = {
        'customer_id': customer_id,
        'customer_name': approval.full_name,
        'phone': payload.get('phone'),
        'marked_by': session.get('username'),
        'notes': payload.get('notes')
    }

    # Add model-specific fields
    if log_model == BadDebtRecord:
        log_data['approved_amount'] = approval.approved_amount
        log_data['outstanding_balance'] = payload.get('outstanding_balance')
    elif log_model == PullPlugRecord:
        log_data['pull_plug_amount'] = payload.get('pull_plug_amount')
    elif log_model == ReturnPrincipalRecord:
        log_data['return_amount'] = payload.get('return_amount')

    new_log_record = log_model(**log_data)
    db.session.add(new_log_record)

def _handle_status_marking_request(status_text, log_model, success_message):
    """Boilerplate handler for status marking API requests."""
    data = request.get_json()
    customer_id = data.get('customer_id')
    if not customer_id:
        return jsonify({'success': False, 'error': 'Customer ID is required'}), 400
    try:
        _mark_status_and_log(customer_id, status_text, log_model, data)
        db.session.commit()
        return jsonify({'success': True, 'message': success_message})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error marking '{status_text}' for customer {customer_id}: {e}")
        return jsonify({'success': False, 'error': f'เกิดข้อผิดพลาดในเซิร์ฟเวอร์: {e}'}), 500

@app.route('/mark_as_bad_debt', methods=['POST'])
@login_required
def mark_as_bad_debt():
    return _handle_status_marking_request('หนี้เสีย', BadDebtRecord, 'บันทึกหนี้เสียเรียบร้อยแล้ว')

@app.route('/mark_as_pull_plug', methods=['POST'])
@login_required
def mark_as_pull_plug():
    return _handle_status_marking_request('ชั๊กปลั๊ก', PullPlugRecord, 'บันทึกการชั๊กปลั๊กเรียบร้อยแล้ว')

@app.route('/mark_as_return_principal', methods=['POST'])
@login_required
def mark_as_return_principal():
    return _handle_status_marking_request('คืนต้น', ReturnPrincipalRecord, 'บันทึกการคืนต้นเรียบร้อยแล้ว')

@app.route('/finish_return_principal', methods=['POST'])
@login_required
def finish_return_principal():
    """
    API endpoint to mark a 'return principal' customer as finished.
    """
    data = request.get_json()
    customer_id = data.get('customer_id')

    if not customer_id:
        return jsonify({'success': False, 'error': 'Customer ID is required'}), 400

    try:
        approval = Approval.query.filter_by(customer_id=customer_id).first()
        if not approval:
            return jsonify({'success': False, 'error': 'Approval record not found'}), 404
        
        approval.status = 'คืนต้นครบแล้ว'
        db.session.commit()
        return jsonify({'success': True, 'message': 'อัปเดตสถานะเป็น "คืนต้นครบแล้ว" เรียบร้อย'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error finishing return principal for customer {customer_id}: {e}")
        return jsonify({'success': False, 'error': 'เกิดข้อผิดพลาดในเซิร์ฟเวอร์'}), 500

# REFACTORED: Generic API endpoint for fetching log-style records
MODEL_API_CONFIG = {
    'bad-debt': {
        'model': BadDebtRecord,
        'fields': {
            'Timestamp': (lambda r: r.timestamp.strftime('%Y-%m-%d %H:%M') if r.timestamp else '-'),
            'CustomerID': 'customer_id', 'CustomerName': 'customer_name', 'Phone': 'phone',
            'ApprovedAmount': (lambda r: f"{r.approved_amount:,.2f}" if r.approved_amount is not None else '-'),
            'OutstandingBalance': (lambda r: f"{r.outstanding_balance:,.2f}" if r.outstanding_balance is not None else '-'),
            'MarkedBy': 'marked_by', 'Notes': 'notes'
        }
    },
    'pull-plug': {
        'model': PullPlugRecord,
        'fields': {
            'Timestamp': (lambda r: r.timestamp.strftime('%Y-%m-%d %H:%M') if r.timestamp else '-'),
            'CustomerID': 'customer_id', 'CustomerName': 'customer_name', 'Phone': 'phone',
            'PullPlugAmount': (lambda r: f"{r.pull_plug_amount:,.2f}" if r.pull_plug_amount is not None else '-'),
            'MarkedBy': 'marked_by', 'Notes': 'notes'
        }
    },
    'return-principal': {
        'model': ReturnPrincipalRecord,
        'fields': {
            'Timestamp': (lambda r: r.timestamp.strftime('%Y-%m-%d %H:%M') if r.timestamp else '-'),
            'CustomerID': 'customer_id', 'CustomerName': 'customer_name', 'Phone': 'phone',
            'ReturnAmount': (lambda r: f"{r.return_amount:,.2f}" if r.return_amount is not None else '-'),
            'MarkedBy': 'marked_by', 'Notes': 'notes'
        }
    }
}

@app.route('/api/records/<record_type>', methods=['GET'])
@login_required
def get_records_api(record_type):
    config = MODEL_API_CONFIG.get(record_type)
    if not config:
        return jsonify({'error': 'Invalid record type'}), 404
    
    try:
        records = config['model'].query.order_by(config['model'].timestamp.desc()).all()
        records_list = []
        for r in records:
            record_dict = {}
            for key, accessor in config['fields'].items():
                if callable(accessor):
                    record_dict[key] = accessor(r)
                else:
                    record_dict[key] = getattr(r, accessor, None)
            records_list.append(record_dict)
        return jsonify(records_list)
    except Exception as e:
        current_app.logger.error(f"Error fetching {record_type} records: {e}")
        return jsonify({'error': 'Could not fetch records'}), 500

@app.route('/get_customer_chart_data')
@login_required
def get_customer_chart_data():
    """Provides data for the main dashboard chart, structured for the frontend filters."""
    try:
        # REFACTORED: Let the database do the grouping and counting for performance.
        results = db.session.query(
            func.extract('year', CustomerRecord.application_date).label('year'),
            func.extract('month', CustomerRecord.application_date).label('month'),
            CustomerRecord.main_customer_group,
            func.count(CustomerRecord.id).label('count')
        ).filter(CustomerRecord.application_date.isnot(None)).group_by('year', 'month', 'main_customer_group').all()

        chart_data = {}
        unique_customer_groups = set()
        unique_years = set()

        for row in results:
            year = str(row.year)
            month = f"{row.month:02d}"
            group = row.main_customer_group or "ไม่ระบุ"
            count = row.count

            unique_years.add(year)
            unique_customer_groups.add(group)

            chart_data.setdefault(year, {}).setdefault(month, {})
            chart_data[year][month][group] = count

        all_months = [f"{i:02d}" for i in range(1, 13)]

        return jsonify({
            'chart_data': chart_data,
            'unique_customer_groups': sorted(list(unique_customer_groups)),
            'unique_years': sorted(list(unique_years), reverse=True),
            'all_months': all_months
        })

    except Exception as e:
        current_app.logger.error(f"Error generating customer chart data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/get_channel_province_chart_data')
@login_required
def get_channel_province_chart_data():
    """Provides data for the channel/province dashboard chart."""
    try:
        # REFACTORED: Use database grouping for much better performance.
        results = db.session.query(
            func.extract('year', CustomerRecord.application_date).label('year'),
            func.extract('month', CustomerRecord.application_date).label('month'),
            CustomerRecord.province,
            CustomerRecord.application_channel,
            CustomerRecord.main_customer_group,
            func.count(CustomerRecord.id).label('count')
        ).filter(CustomerRecord.application_date.isnot(None)).group_by('year', 'month', 'province', 'application_channel', 'main_customer_group').all()

        chart_data = {}
        unique_years = set()
        unique_channels = set()
        unique_provinces = set()
        unique_groups = set()

        for row in results:
            year = str(row.year)
            month = f"{row.month:02d}"
            province = row.province or "ไม่ระบุ"
            channel = row.application_channel or "ไม่ระบุ"
            group = row.main_customer_group or "ไม่ระบุ"
            count = row.count

            unique_years.add(year)
            unique_provinces.add(province)
            unique_channels.add(channel)
            unique_groups.add(group)

            path = chart_data.setdefault(year, {}).setdefault(month, {}).setdefault(province, {}).setdefault(channel, {})
            path[group] = count

        all_months = [f"{i:02d}" for i in range(1, 13)]

        # NEW: Define a fixed list of all possible channels to ensure they always appear in the filter
        all_possible_channels = [
            "FACEBOOK สตาร์โลน",
            "FACEBOOK กลอรี่แคช",
            "FACEBOOK แคชเครดิต",
            "ไลน์@สตาร์โลน",
            "ไลน์@กลอรี่แคช",
            "ไลน์@แคชเครดิต",
            "โทรเข้ามา สตาร์โลน",
            "โทรเข้ามา กลอรี่แคช",
            "โทรเข้ามา แคชเครดิต",
            "อีเมล"
        ]

        return jsonify({
            'chart_data': chart_data,
            'unique_years': sorted(list(unique_years), reverse=True),
            'all_months': all_months,
            'unique_channels': all_possible_channels,
            'unique_provinces': sorted(list(unique_provinces)),
            'unique_groups': sorted(list(unique_groups))
        })
    except Exception as e:
        current_app.logger.error(f"Error generating channel/province chart data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/cloudinary-signature', methods=['GET'])
@login_required
def get_cloudinary_signature():
    """Generate a signature for direct Cloudinary uploads."""
    try:
        timestamp = int(datetime.now().timestamp())
        transformation = "w_1000,h_1000,c_limit"
        params_to_sign = {'timestamp': timestamp, 'folder': 'customer_app_images', 'transformation': transformation}
        signature = cloudinary.utils.api_sign_request(params_to_sign, os.environ.get('CLOUDINARY_API_SECRET'))
        
        return jsonify({
            'signature': signature, 'timestamp': timestamp,
            'api_key': os.environ.get('CLOUDINARY_API_KEY'),
            'cloud_name': os.environ.get('CLOUDINARY_CLOUD_NAME'),
            'transformation': transformation
        })
    except Exception as e:
        current_app.logger.error(f"Error generating Cloudinary signature: {e}")
        return jsonify({'error': 'Could not generate signature'}), 500

@app.route('/update_customer_status', methods=['POST'])
@login_required
def update_customer_status():
    data = request.get_json()
    record_id = data.get('row_index')
    new_status = data.get('new_status')

    customer = get_customer_by_db_id(record_id)
    if not customer:
        return jsonify({'success': False, 'message': 'ไม่พบข้อมูลลูกค้า'}), 404

    try:
        customer.status = new_status
        if new_status in ['รอตรวจ', 'เลื่อนนัด']:
            customer.inspection_date = datetime.strptime(data.get('inspection_date'), '%Y-%m-%d').date() if data.get('inspection_date') else None
            customer.inspection_time = datetime.strptime(data.get('inspection_time'), '%H:%M').time() if data.get('inspection_time') else None
            customer.inspector = data.get('inspector')
        if new_status in ['ยกเลิก', 'ไม่อนุมัติ']:
            note = data.get('note')
            customer.remarks = (customer.remarks or '') + f"\n[สถานะ: {new_status}] {note}"

        db.session.commit()
        cache.clear()
        return jsonify({'success': True, 'message': 'อัปเดตสถานะสำเร็จ'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating status for {record_id}: {e}")
        return jsonify({'success': False, 'message': f'เกิดข้อผิดพลาด: {e}'}), 500

# =================================================================================
# MAIN EXECUTION
# =================================================================================

if __name__ == '__main__':
    # Use app.run() only for local development.
    # For production, use a proper WSGI server like Gunicorn or uWSGI.
    app.run(debug=True)