import sys
import os

print("--- Python Environment Information ---")
print(f"Python Executable: {sys.executable}")
print("\n--- sys.path (Python กำลังมองหา library จากที่นี่) ---")
for path in sys.path:
    print(path)

print("\n--- กำลังตรวจสอบว่า 'python-dotenv' อยู่ในเส้นทางหรือไม่ ---")
found = False
for path in sys.path:
    # Check for the package directory
    dotenv_path = os.path.join(path, 'dotenv')
    if os.path.exists(dotenv_path) and os.path.isdir(dotenv_path):
        print(f"✅ พบโฟลเดอร์ 'dotenv' ที่: {dotenv_path}")
        found = True
        break

if not found:
    print("\n❌ ไม่พบ package 'dotenv' ในเส้นทางของ sys.path")
    print("นี่คือสาเหตุของปัญหา ImportError ครับ")
else:
    print("\n✅ พบ package 'dotenv' ในเส้นทางแล้ว")

print("\n--- กำลังลอง import โดยตรง ---")
try:
    from dotenv import load_dotenv
    print("✅ Import 'load_dotenv' สำเร็จ!")
except ImportError as e:
    print(f"❌ Import ล้มเหลว: {e}")
except Exception as e:
    print(f"❌ เกิดข้อผิดพลาดที่ไม่คาดคิดระหว่าง import: {e}")

