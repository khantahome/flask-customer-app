# -*- coding: utf-8 -*-
from werkzeug.security import generate_password_hash
import getpass # ใช้สำหรับซ่อนการพิมพ์รหัสผ่าน
import sys

# Ensure UTF-8 encoding for output, especially on Windows
sys.stdout.reconfigure(encoding='utf-8')

print("--- Password Hashing Utility ---")
print("สคริปต์นี้จะสร้าง Hashed Password สำหรับนำไปใช้ในฐานข้อมูลโดยตรง")

# ใช้ getpass เพื่อซ่อนรหัสผ่านขณะพิมพ์เพื่อความปลอดภัย
password_to_hash = getpass.getpass("กรุณาป้อนรหัสผ่านที่ต้องการเข้ารหัส (password will be hidden): ")

if not password_to_hash:
    print("\n❌ ไม่ได้ป้อนรหัสผ่าน โปรดยกเลิกและลองอีกครั้ง")
else:
    # สร้าง hash โดยใช้วิธีเดียวกับในแอปพลิเคชัน
    hashed_password = generate_password_hash(password_to_hash)
    
    print("\n✅ สร้างรหัสผ่านที่เข้ารหัส (Hashed Password) สำเร็จแล้ว!")
    print("----------------------------------------------------")
    print("คัดลอกข้อความทั้งหมดข้างล่างนี้ไปใช้ใน Workbench:")
    print(hashed_password)
    print("----------------------------------------------------")