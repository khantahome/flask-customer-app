import pandas as pd
from sqlalchemy import text
import numpy as np
import sys
# NEW: Import os and dotenv to handle environment variables
import os
from dotenv import load_dotenv
# NEW: Import the Flask app and db object to create tables
from app import app, db, CustomerRecord, User, generate_password_hash

load_dotenv() # โหลดค่าจากไฟล์ .env

# NEW: Function to create tables based on models in app.py
# ==============================================================================
# 1. ฟังก์ชันสำหรับสร้างตารางฐานข้อมูล
# ==============================================================================
def create_tables(clean_install=False):
    """
    สร้างตารางฐานข้อมูล
    - ถ้า clean_install=True: จะลบตารางเก่าทั้งหมดทิ้งก่อนแล้วสร้างใหม่ (อันตราย!)
    - ถ้า clean_install=False: จะสร้างเฉพาะตารางที่ยังไม่มีอยู่เท่านั้น (ปลอดภัย)
    """
    print("\nกำลังตรวจสอบและสร้างตารางในฐานข้อมูล...")
    try:
        with app.app_context():
            if clean_install:
                print("  - ได้รับคำสั่ง --clean: กำลังลบตารางเก่าทั้งหมด...")
                db.drop_all()
                print("  - กำลังสร้างตารางใหม่ตามโมเดลล่าสุด...")
                db.create_all()
            else:
                print("  - กำลังสร้างตารางที่ยังไม่มี (หากจำเป็น)...")
                db.create_all() # คำสั่งนี้ปลอดภัย จะไม่ลบตารางที่มีอยู่แล้ว
        print("✅ ตรวจสอบตารางเสร็จสิ้น!")
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดร้ายแรงระหว่างการสร้างตาราง: {e}")
        exit() # Exit if tables can't be created, as migration will fail anyway.

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
            # --- REVISED: Generate numeric IDs for missing values, without "PID-" prefix ---
            with app.app_context():
                # This query finds the highest numeric ID by casting the column to an integer.
                last_id_scalar = db.session.query(db.func.max(db.func.cast(CustomerRecord.customer_id, db.Integer))).scalar()
                
                id_counter = (last_id_scalar or 1000) + 1

                def generate_id(value):
                    nonlocal id_counter
                    # Check if the value is missing (NaN, None, or empty string)
                    if pd.isna(value) or str(value).strip() == '':
                        new_id = f"{id_counter}"
                        id_counter += 1
                        return new_id
                    # If the value exists, keep it as is.
                    return str(value).strip()

            df['customer_id'] = df['customer_id'].apply(generate_id)

        # แปลงชนิดข้อมูลและจัดการค่าว่าง
        for col in df.columns:
            if 'amount' in col or 'balance' in col or 'limit' in col or 'interest' in col or 'fee' in col:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '', regex=False), errors='coerce').fillna(0)
            if 'date' in col or 'timestamp' in col:
                df[col] = pd.to_datetime(df[col], errors='coerce')
            elif 'time' in col: # NEW: Handle time columns
                df[col] = pd.to_datetime(df[col], errors='coerce', format='%H:%M:%S').dt.time

        # NEW: Hash passwords before inserting into the database
        if table_name == 'users' and 'password' in df.columns:
            print("  - กำลังแฮชรหัสผ่าน...")
            df['password'] = df['password'].apply(lambda pwd: generate_password_hash(str(pwd)) if pd.notna(pwd) else None)

            # --- NEW LOGIC TO PREVENT DUPLICATE USERS ---
            with app.app_context():
                # Get a list of all existing user IDs from the database
                print("  - กำลังตรวจสอบผู้ใช้ที่ซ้ำกันในฐานข้อมูล...")
                existing_user_ids = [user.user_id for user in db.session.query(User.user_id).all()]
                
                # Filter the DataFrame to only include users that are NOT already in the database
                original_count = len(df)
                df_new_users = df[~df['id'].isin(existing_user_ids)]
                new_count = len(df_new_users)

                if new_count == 0:
                    print("  - ไม่พบผู้ใช้ใหม่ในไฟล์ CSV ที่จะต้องเพิ่มเข้าสู่ระบบ")
                    return # Exit the function early if no new users
                
                print(f"  - พบผู้ใช้ทั้งหมด {original_count} คนในไฟล์, จะทำการเพิ่มผู้ใช้ใหม่ {new_count} คน")
                df = df_new_users # Replace the original df with the filtered one
            # --- END NEW LOGIC ---

        df.replace({np.nan: None, 'NaT': None}, inplace=True)

        # REVISED: ใช้ engine จาก app context เพื่อหลีกเลี่ยงการสร้าง connection ซ้ำซ้อน
        with app.app_context():
            df.to_sql(table_name, con=db.engine, if_exists='append', index=False)
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
    # --- ตรวจสอบว่าผู้ใช้ต้องการล้างข้อมูลหรือไม่ ---
    clean_install = '--clean' in sys.argv

    if clean_install:
        print("\n🔥🔥🔥 คำเตือน: คุณกำลังจะลบข้อมูลทั้งหมดในฐานข้อมูลและสร้างใหม่! 🔥🔥🔥")
        # เพิ่มการยืนยันเพื่อความปลอดภัย
        confirm = input("ข้อมูลทั้งหมดจะหายไป! พิมพ์ 'yes' เพื่อยืนยันการลบข้อมูล: ")
        if confirm.lower().strip() != 'yes':
            print("ยกเลิกการทำงาน")
            exit()

    # --- Step 0: Create tables first ---
    # ส่งค่า clean_install ไปยังฟังก์ชัน
    create_tables(clean_install=clean_install)

    # --- REFACTORED: Define all migration tasks in a structured list ---
    migration_tasks = [
        {
            'csv_path': 'users.csv',
            'table_name': 'users',
            'column_map': users_map,
            'dtype_spec': None
        }
    ]

    # --- REFACTORED: Loop through tasks and execute ---
    for task in migration_tasks:
        csv_path = task['csv_path']
        print(f"\nกำลังเริ่มการนำเข้าข้อมูลจากไฟล์ CSV: '{csv_path}'")
        try:
            # REVISED: Handle different delimiters for different CSV files.
            # data1.csv and users.csv use commas, while the others use semicolons.
            delimiter = ';' if task['table_name'] not in ['customer_records', 'users'] else ','
            df = pd.read_csv(
                csv_path, 
                encoding='utf-8-sig', 
                dtype=task.get('dtype_spec'), 
                delimiter=delimiter
            )
            process_dataframe_and_import(df, task['table_name'], task['column_map'], f"ไฟล์ '{csv_path}'")
        except FileNotFoundError:
            print(f"🚨 ไม่พบไฟล์ '{csv_path}'! ข้ามการนำเข้าไฟล์นี้")
        except Exception as e:
            print(f"❌ เกิดข้อผิดพลาดกับไฟล์ '{csv_path}': {e}")

    print("\n🎉 กระบวนการนำเข้าข้อมูลทั้งหมดเสร็จสิ้น!")

if __name__ == '__main__':
    main()