import json
from app import User, db, CustomerRecord, generate_password_hash

def test_login_page(client):
    """
    GIVEN: แอปพลิเคชัน Flask ที่ตั้งค่าสำหรับทดสอบ
    WHEN: มีการร้องขอหน้า '/login' (GET)
    THEN: ตรวจสอบว่า response ที่ได้ถูกต้อง
    """
    response = client.get('/login')
    response_text = response.data.decode('utf-8')
    assert response.status_code == 200
    assert "Sign in" in response_text
    assert "ชื่อผู้ใช้" in response_text
    assert "รหัสผ่าน" in response_text

def test_successful_login_and_logout(client, app):
    """
    GIVEN: แอปพลิเคชัน Flask และผู้ใช้ทดสอบในระบบ
    WHEN: ผู้ใช้ล็อกอินด้วยข้อมูลที่ถูกต้อง
    THEN: ตรวจสอบว่าถูก redirect ไปยังหน้า dashboard และสามารถล็อกเอาท์ได้
    """
    # Setup: สร้างผู้ใช้ทดสอบในฐานข้อมูลจำลอง (in-memory)
    with app.app_context():
        hashed_password = generate_password_hash('password123')
        test_user = User(user_id='testuser', password=hashed_password)
        db.session.add(test_user)
        db.session.commit()

    # ทดสอบการล็อกอิน
    response = client.post('/login', data=dict(
        username='testuser',
        password='password123'
    ), follow_redirects=True)

    assert response.status_code == 200
    assert "เข้าสู่ระบบสำเร็จ" in response.data.decode('utf-8')
    assert "หน้าหลัก" in response.data.decode('utf-8') # ตรวจสอบว่าเจอเนื้อหาในหน้า dashboard

    # ทดสอบการล็อกเอาท์
    response = client.get('/logout', follow_redirects=True)
    assert response.status_code == 200
    assert "ออกจากระบบแล้ว" in response.data.decode('utf-8')
    assert b"Sign in" in response.data # ควรจะกลับมาที่หน้า Login

def test_search_customer_data(logged_in_client, app):
    """
    GIVEN a Flask application with several customer records
    WHEN the '/search_customer_data' page is accessed with different keywords
    THEN check that the correct records are displayed
    """
    # 1. Setup: Create test customer records
    with app.app_context():
        customer1 = CustomerRecord(customer_id='PID-SEARCH-1', first_name='สมชาย', last_name='ใจดี', mobile_phone='081-111-1111')
        customer2 = CustomerRecord(customer_id='PID-SEARCH-2', first_name='สมหญิง', last_name='รักสงบ', business_name='ร้านรักสงบ')
        customer3 = CustomerRecord(customer_id='PID-SEARCH-3', first_name='มานี', last_name='มีนา', id_card_number='1234567890123')
        db.session.add_all([customer1, customer2, customer3])
        db.session.commit()

    # 2. Test searching by name (สมหญิง)
    response_name = logged_in_client.get('/search_customer_data?search_keyword=สมหญิง')
    assert response_name.status_code == 200
    response_text_name = response_name.data.decode('utf-8')
    assert 'PID-SEARCH-2' in response_text_name
    assert 'สมหญิง รักสงบ' in response_text_name
    assert 'PID-SEARCH-1' not in response_text_name

    # 3. Test searching by business name (ร้านรักสงบ)
    response_biz = logged_in_client.get('/search_customer_data?search_keyword=ร้านรักสงบ')
    assert response_biz.status_code == 200
    response_text_biz = response_biz.data.decode('utf-8')
    assert 'PID-SEARCH-2' in response_text_biz
    assert 'ร้านรักสงบ' in response_text_biz
    assert 'PID-SEARCH-3' not in response_text_biz

    # 4. Test searching with no results
    response_none = logged_in_client.get('/search_customer_data?search_keyword=ไม่มีอยู่จริง')
    assert response_none.status_code == 200
    response_text_none = response_none.data.decode('utf-8')
    assert 'ไม่พบข้อมูลที่ตรงกับเงื่อนไขการค้นหา' in response_text_none
    assert 'PID-SEARCH-1' not in response_text_none

    # 5. Test accessing the page with no search keyword (should show all)
    response_all = logged_in_client.get('/search_customer_data')
    assert response_all.status_code == 200
    response_text_all = response_all.data.decode('utf-8')
    assert 'แสดงข้อมูลลูกค้าทั้งหมด' in response_text_all
    assert 'PID-SEARCH-1' in response_text_all
    assert 'PID-SEARCH-2' in response_text_all
    assert 'PID-SEARCH-3' in response_text_all

def test_enter_customer_data(logged_in_client, app):
    """
    GIVEN a logged-in user
    WHEN the '/enter_customer_data' form is submitted with valid data
    THEN check that a new CustomerRecord is created in the database
    """
    # 1. Prepare form data for the new customer
    new_customer_data = {
        'customer_name': 'ทดสอบ',
        'last_name': 'การสร้าง',
        'mobile_phone_number': '099-888-7777',
        'id_card_number': '9876543210987',
        'main_customer_group': 'ค้าขาย',
        'business_name': 'ร้านค้าทดสอบ',
        'province': 'กรุงเทพมหานคร',
        'status': 'รอติดต่อ',
        'how_applied': 'FACEBOOK สตาร์โลน',
        'desired_credit_limit': '100000'
    }

    # 2. Send a POST request to the endpoint
    response = logged_in_client.post('/enter_customer_data', data=new_customer_data)

    # 3. Assert the API response
    assert response.status_code == 200
    response_data = json.loads(response.data)
    assert response_data['success'] is True
    assert 'บันทึกข้อมูลลูกค้า' in response_data['message']
    new_customer_id = response_data['customer_id']

    # 4. Verify the database state
    with app.app_context():
        created_customer = CustomerRecord.query.filter_by(customer_id=new_customer_id).first()
        assert created_customer is not None
        assert created_customer.first_name == 'ทดสอบ'
        assert created_customer.mobile_phone == '099-888-7777'
        assert created_customer.status == 'รอติดต่อ'
        assert created_customer.desired_credit_limit == 100000.00

def test_edit_customer_data(logged_in_client, app):
    """
    GIVEN a logged-in user and an existing customer record
    WHEN the '/edit_customer_data' form is submitted with updated data
    THEN check that the CustomerRecord is updated in the database
    """
    # 1. Setup: Create an initial customer record
    with app.app_context():
        initial_customer = CustomerRecord(
            customer_id='PID-EDIT-1',
            first_name='เดิม',
            last_name='นามสกุลเดิม',
            status='รอติดต่อ',
            province='กรุงเทพมหานคร'
        )
        db.session.add(initial_customer)
        db.session.commit()
        # We need the database ID to build the URL
        customer_db_id = initial_customer.id

    # 2. Prepare the updated data
    updated_data = {
        'customer_name': 'ใหม่',
        'last_name': 'นามสกุลใหม่',
        'status': 'รอตรวจ',
        'province': 'เชียงใหม่',
    }

    # 3. Send a POST request to the edit endpoint and follow the redirect
    response = logged_in_client.post(f'/edit_customer_data/{customer_db_id}', data=updated_data, follow_redirects=True)

    # 4. Assert the response after redirect
    assert response.status_code == 200
    assert 'อัปเดตข้อมูลลูกค้าสำเร็จ' in response.data.decode('utf-8')

    # 5. Verify the database state
    with app.app_context():
        updated_customer = db.session.get(CustomerRecord, customer_db_id)
        assert updated_customer is not None
        assert updated_customer.first_name == 'ใหม่'
        assert updated_customer.status == 'รอตรวจ'
        assert updated_customer.province == 'เชียงใหม่'

def test_delete_customer(logged_in_client, app):
    """
    GIVEN a logged-in user and an existing customer record
    WHEN a POST request is sent to '/delete_customer/<id>'
    THEN check that the customer is deleted from the database
    """
    # 1. Setup: Create a customer to be deleted
    with app.app_context():
        customer_to_delete = CustomerRecord(
            customer_id='PID-DELETE-1',
            first_name='จะถูกลบ',
            last_name='แน่นอน'
        )
        db.session.add(customer_to_delete)
        db.session.commit()
        customer_db_id = customer_to_delete.id

    # 2. Send a POST request to the delete endpoint and follow the redirect
    response = logged_in_client.post(f'/delete_customer/{customer_db_id}', follow_redirects=True)

    # 3. Assert the response after redirect
    assert response.status_code == 200
    assert 'ลบข้อมูลลูกค้า PID-DELETE-1 สำเร็จ' in response.data.decode('utf-8')

    # 4. Verify the database state
    with app.app_context():
        deleted_customer = db.session.get(CustomerRecord, customer_db_id)
        assert deleted_customer is None