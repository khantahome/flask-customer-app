import pandas as pd
from sqlalchemy import create_engine, text
import numpy as np
# NEW: Import os and dotenv to handle environment variables
import os
from dotenv import load_dotenv
# NEW: Import the Flask app and db object to create tables
from app import app, db

load_dotenv() # โหลดค่าจากไฟล์ .env

# ==============================================================================
# * 1. ตั้งค่าการเชื่อมต่อ DATABASE ของคุณ
# ==============================================================================
# **สำคัญ:** แก้ไขค่าในไฟล์ .env ของคุณ ไม่ใช่ในโค้ดโดยตรง
DB_USER = os.environ.get('DB_USER', 'root')
DB_PASSWORD = os.environ.get('DB_PASSWORD') # <-- * อ่านรหัสผ่านจาก .env
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_NAME = os.environ.get('DB_NAME', 'loan_system')

# เพิ่มการตรวจสอบว่ามีรหัสผ่านหรือไม่
if not DB_PASSWORD:
    raise ValueError("ไม่ได้ตั้งค่า DB_PASSWORD ในไฟล์ .env กรุณาตั้งค่าแล้วลองอีกครั้ง")

db_connection_str = f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}'
db_engine = create_engine(db_connection_str)


# ==============================================================================
# 2. ฟังก์ชันสำหรับทำความสะอาดและแปลงข้อมูล (ไม่ต้องแก้ไขส่วนนี้)
# ==============================================================================
def process_dataframe_and_import(df, table_name, column_map, source_name):
    """ฟังก์ชันสำหรับแปลง DataFrame และนำเข้าข้อมูลไปยังตารางที่ระบุ"""
    try:
        print(f"  - กำลังแปลงข้อมูลจาก '{source_name}' สำหรับตาราง '{table_name}'...")
        # เปลี่ยนชื่อคอลัมน์
        df.rename(columns=column_map, inplace=True)

        # เลือกเฉพาะคอลัมน์ที่มีใน column_map เพื่อป้องกันคอลัมน์เกิน
        # และป้องกัน KeyError ถ้าคอลัมน์ใน map ไม่มีใน df
        valid_columns = [col for col in column_map.values() if col in df.columns]
        df = df[valid_columns]

        if table_name == 'customer_records' and 'customer_id' in df.columns:
            # --- REVISED: Generate PID-xxxx style IDs for missing values ---
            id_counter = 1001
            
            def generate_pid(value):
                # Check if the value is missing (NaN, None, or empty string)
                if pd.isna(value) or str(value).strip() == '':
                    nonlocal id_counter
                    new_id = f"PID-{id_counter}"
                    id_counter += 1
                    return new_id
                # If the value exists, keep it as is.
                return str(value).strip()

            df['customer_id'] = df['customer_id'].apply(generate_pid)

        # แปลงชนิดข้อมูลและจัดการค่าว่าง
        for col in df.columns:
            if 'amount' in col or 'balance' in col or 'limit' in col or 'interest' in col or 'fee' in col:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '', regex=False), errors='coerce').fillna(0)
            if 'date' in col or 'timestamp' in col:
                df[col] = pd.to_datetime(df[col], errors='coerce')
            elif 'time' in col: # NEW: Handle time columns
                df[col] = pd.to_datetime(df[col], errors='coerce', format='%H:%M:%S').dt.time

        df.replace({np.nan: None, 'NaT': None}, inplace=True)

        # Since we are now dropping and creating tables, the TRUNCATE logic is no longer needed.
        # We can directly append to the newly created empty tables.

        df.to_sql(table_name, con=db_engine, if_exists='append', index=False)
        print(f"  ✅ นำเข้าข้อมูลสู่ตาราง '{table_name}' สำเร็จ!")
    except Exception as e:
        print(f"  ❌ เกิดข้อผิดพลาดระหว่างประมวลผล '{source_name}' สำหรับตาราง '{table_name}': {e}")


# ==============================================================================
# * 3. กำหนดค่าสำหรับแต่ละไฟล์ CSV ที่ต้องการนำเข้า
# ==============================================================================

# --- 1. สำหรับ customer_records ---
customer_records_map = {
    'Timestamp': 'timestamp', 'Customer ID': 'customer_id', 'ชื่อ': 'first_name', 'นามสกุล': 'last_name',
    'เลขบัตรประชาชน': 'id_card_number', 'เบอร์มือถือ': 'mobile_phone', 'กลุ่มลูกค้าหลัก': 'main_customer_group',
    'กลุ่มอาชีพย่อย': 'sub_profession_group', 'ระบุอาชีพย่อยอื่นๆ': 'other_sub_profession', 'จดทะเบียน': 'is_registered',
    'ชื่อกิจการ': 'business_name', 'จังหวัดที่อยู่': 'province', 'ที่อยู่จดทะเบียน': 'registered_address',
    'สถานะ': 'status', 'วงเงินที่ต้องการ': 'desired_credit_limit', 'วงเงินที่อนุมัติ': 'approved_credit_limit',
    'เคยขอเข้ามาในเครือหรือยัง': 'applied_before', 'เช็ค': 'check_status', 'ขอเข้ามาทางไหน': 'application_channel',
    'บริษัทที่รับงาน': 'assigned_company', 'หักดอกหัวท้าย': 'upfront_interest_deduction', 'ค่าดำเนินการ': 'processing_fee', 'วันที่ขอเข้ามา': 'application_date',
    'ลิงค์โลเคชั่นบ้าน': 'home_location_link', 'ลิงค์โลเคชั่นที่ทำงาน': 'work_location_link', 'หมายเหตุ': 'remarks',
    'Image URLs': 'image_urls', 'Logged In User': 'logged_in_user', 'วันที่นัดตรวจ': 'inspection_date',
    'เวลานัดตรวจ': 'inspection_time', 'ผู้รับงานตรวจ': 'inspector'
}

# --- 2. สำหรับ approove ---
approvals_map = {
    'สถานะ': 'status', 'Customer ID': 'customer_id', 'ชื่อ-นามสกุล': 'full_name', 'หมายเลขโทรศัพท์': 'phone_number',
    'วันที่อนุมัติ': 'approval_date', 'วงเงินที่อนุมัติ': 'approved_amount', 'บริษัทที่รับงาน': 'assigned_company',
    'ชื่อผู้ลงทะเบียน': 'registrar', 'รูปถ่ายสัญญา': 'contract_image_urls'
}

# --- 3. สำหรับ bad_debt_records ---
bad_debt_map = {
    'Timestamp': 'timestamp', 'CustomerID': 'customer_id', 'CustomerName': 'customer_name', 'Phone': 'phone',
    'ApprovedAmount': 'approved_amount', 'OutstandingBalance': 'outstanding_balance', 'MarkedBy': 'marked_by', 'Notes': 'notes'
}

# --- 4. สำหรับ pull_plug_records ---
pull_plug_map = {
    'Timestamp': 'timestamp', 'CustomerID': 'customer_id', 'CustomerName': 'customer_name', 'Phone': 'phone',
    'PullPlugAmount': 'pull_plug_amount', 'MarkedBy': 'marked_by', 'Notes': 'notes'
}

# --- 5. สำหรับ return_principal_records ---
return_principal_map = {
    'Timestamp': 'timestamp', 'CustomerID': 'customer_id', 'CustomerName': 'customer_name', 'Phone': 'phone',
    'ReturnAmount': 'return_amount', 'MarkedBy': 'marked_by', 'Notes': 'notes'
}

# --- 6. สำหรับ allpidjob ---
all_pid_jobs_map = {
    'Date': 'transaction_date', 'CompanyName': 'company_name', 'CustomerID': 'customer_id', 'Time': 'transaction_time',
    'CustomerName': 'customer_name', 'interest': 'interest', 'Table1_OpeningBalance': 'table1_opening_balance',
    'Table1_NetOpening': 'table1_net_opening', 'Table1_PrincipalReturned': 'table1_principal_returned',
    'Table1_LostAmount': 'table1_lost_amount', 'Table2_OpeningBalance': 'table2_opening_balance',
    'Table2_NetOpening': 'table2_net_opening', 'Table2_PrincipalReturned': 'table2_principal_returned',
    'Table2_LostAmount': 'table2_lost_amount', 'Table3_OpeningBalance': 'table3_opening_balance',
    'Table3_NetOpening': 'table3_net_opening', 'Table3_PrincipalReturned': 'table3_principal_returned',
    'Table3_LostAmount': 'table3_lost_amount', 'บริษัทที่รับงาน': 'main_assigned_company'
}

# --- 7. สำหรับ users ---
users_map = {
    'id': 'id',      # Key คือชื่อคอลัมน์ใน CSV, Value คือชื่อคอลัมน์ในตาราง SQL
    'pass': 'password'
}

def main():
    # --- Step 0: Create tables first ---
    # This function is now defined in the provided `migrate_data.py` but not shown here for brevity.
    # It drops and creates all tables.
    # create_tables() is assumed to be called here.

    # --- Step 1: Import main customer data from data1.csv ---
    customer_csv_path = 'data1.csv'
    print(f"\nกำลังเริ่มการนำเข้าข้อมูลจากไฟล์ CSV หลัก: '{customer_csv_path}'")
    try:
        # Define dtypes to prevent pandas from dropping leading zeros from phone numbers and ID cards
        customer_dtype_spec = {'เบอร์มือถือ': str, 'เลขบัตรประชาชน': str}
        df_customers = pd.read_csv(customer_csv_path, encoding='utf-8-sig', dtype=customer_dtype_spec)
        process_dataframe_and_import(df_customers, 'customer_records', customer_records_map, f"ไฟล์ '{customer_csv_path}'")
    except FileNotFoundError:
        print(f"🚨 ไม่พบไฟล์ '{customer_csv_path}'! กรุณาตรวจสอบว่าไฟล์อยู่ในตำแหน่งที่ถูกต้อง")
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดกับไฟล์ '{customer_csv_path}': {e}")

    # --- Step 2: Import user data from users.csv ---
    users_csv_path = 'users.csv'
    print(f"\nกำลังเริ่มการนำเข้าข้อมูลจากไฟล์ CSV: '{users_csv_path}'")
    try:
        df_users = pd.read_csv(users_csv_path, encoding='utf-8-sig')
        process_dataframe_and_import(df_users, 'users', users_map, f"ไฟล์ '{users_csv_path}'")
    except FileNotFoundError:
        print(f"🚨 ไม่พบไฟล์ '{users_csv_path}'!")
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดกับไฟล์ '{users_csv_path}': {e}")

    print("\n🎉 กระบวนการนำเข้าข้อมูลทั้งหมดเสร็จสิ้น!")

if __name__ == '__main__':
    main()