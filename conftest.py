import pytest
from app import app as flask_app, db as sqlalchemy_db, User

@pytest.fixture(scope='module')
def app():
    """
    สร้าง Instance ของ Flask application สำหรับการทดสอบ
    """
    # ตั้งค่าให้แอปอยู่ในโหมดทดสอบ
    flask_app.config.update({
        "TESTING": True,
        # **สำคัญ:** ใช้ฐานข้อมูล SQLite ในหน่วยความจำเพื่อไม่ให้กระทบฐานข้อมูลจริง
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False,  # ปิด CSRF เพื่อให้เทสง่ายขึ้น
        "SECRET_KEY": "my-test-secret-key" # ใช้ test secret key
    })

    # สร้างตารางทั้งหมดในฐานข้อมูลจำลอง (in-memory)
    with flask_app.app_context():
        sqlalchemy_db.create_all()

    yield flask_app

    # Cleanup: ลบตารางทั้งหมดหลังจากการทดสอบในโมดูลเสร็จสิ้น
    with flask_app.app_context():
        sqlalchemy_db.drop_all()

@pytest.fixture()
def client(app):
    """
    สร้าง Test Client สำหรับจำลองการส่ง request ไปยังแอป
    """
    return app.test_client()

@pytest.fixture()
def runner(app):
    """
    สร้าง Test Runner สำหรับคำสั่ง CLI ของแอป (ถ้ามี)
    """
    return app.test_cli_runner()

@pytest.fixture()
def logged_in_client(client, app):
    """
    สร้าง Test Client ที่ล็อกอินแล้วสำหรับทดสอบ endpoint ที่ต้องการ authentication
    """
    # สร้างผู้ใช้ทดสอบในฐานข้อมูลจำลอง
    with app.app_context():
        # ตรวจสอบว่ามีผู้ใช้ 'testuser' อยู่แล้วหรือไม่ เพื่อป้องกัน error
        test_user = User.query.filter_by(user_id='testuser').first()
        if not test_user:
            user = User(user_id='testuser', password='password123')
            sqlalchemy_db.session.add(user)
            sqlalchemy_db.session.commit()

    # ทำการล็อกอิน
    client.post('/login', data=dict(
        username='testuser',
        password='password123'
    ))

    yield client