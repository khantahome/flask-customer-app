import json
from datetime import date, time
import io
from unittest.mock import patch
from app import db, AllPidJob, Approval, User, BadDebtRecord, PullPlugRecord, ReturnPrincipalRecord, ContractDocument, CustomerRecord

def test_get_daily_jobs_api(logged_in_client, app):
    """
    GIVEN a Flask application configured for testing
    WHEN the '/api/daily-jobs' endpoint is requested with valid parameters
    THEN check that the response is valid and contains the correct data
    """
    # Setup: สร้างข้อมูลทดสอบในฐานข้อมูลจำลอง (in-memory)
    with app.app_context():
        # สร้างข้อมูลลูกค้าที่อนุมัติแล้วเพื่อเป็นข้อมูลอ้างอิง
        approval = Approval(customer_id='C-001', full_name='Test Customer')
        db.session.add(approval)

        # สร้างข้อมูล job สำหรับวันที่ที่ต้องการทดสอบ
        job1 = AllPidJob(
            transaction_date=date(2025, 9, 18),
            transaction_time=time(10, 30, 0),
            company_name='STARLOAN',
            customer_id='C-001',
            customer_name='Test Customer',
            table1_opening_balance=5000
        )
        job2 = AllPidJob(
            transaction_date=date(2025, 9, 18),
            transaction_time=time(11, 0, 0),
            company_name='GLORYCASH',
            customer_id='C-002',
            customer_name='Another Customer',
            table2_principal_returned=1000
        )
        # สร้างข้อมูล job สำหรับวันอื่น ซึ่งไม่ควรจะถูกดึงมา
        job3 = AllPidJob(
            transaction_date=date(2025, 9, 19),
            transaction_time=time(9, 0, 0),
            company_name='STARLOAN',
            customer_id='C-003',
            customer_name='Future Customer',
            table1_opening_balance=2000
        )
        db.session.add_all([job1, job2, job3])
        db.session.commit()

    # 1. ทดสอบการดึงข้อมูล job ทั้งหมดสำหรับวันที่ที่ระบุ
    response = logged_in_client.get('/api/daily-jobs?date=2025-09-18')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert len(data) == 2 # ควรจะคืนค่ามา 2 records (job1 และ job2)

    # 2. ทดสอบการกรองข้อมูลตามบริษัท
    response_starloan = logged_in_client.get('/api/daily-jobs?date=2025-09-18&company=STARLOAN')
    assert response_starloan.status_code == 200
    data_starloan = json.loads(response_starloan.data)
    assert len(data_starloan) == 1
    assert data_starloan[0]['CustomerID'] == 'C-001'
    assert data_starloan[0]['Table1_OpeningBalance'] == 5000.0

    # 3. ทดสอบกับวันที่ไม่มีข้อมูล
    response_no_jobs = logged_in_client.get('/api/daily-jobs?date=2025-09-20')
    assert response_no_jobs.status_code == 200
    data_no_jobs = json.loads(response_no_jobs.data)
    assert len(data_no_jobs) == 0

def test_get_customer_balance_api(logged_in_client, app):
    """
    GIVEN a Flask application configured for testing
    WHEN the '/api/customer-balance/<customer_id>' endpoint is requested
    THEN check that the calculated balance is correct
    """
    # Setup: สร้างข้อมูลทดสอบในฐานข้อมูลจำลอง (in-memory)
    with app.app_context():
        # ไม่จำเป็นต้องสร้าง user ใหม่ เพราะ fixture 'app' มี scope='module'
        # และ user ถูกสร้างไปแล้วในเทสก่อนหน้า

        # Transactions for customer C-101
        job1 = AllPidJob(customer_id='C-101', table1_opening_balance=10000, table2_net_opening=5000) # Given: 15000
        job2 = AllPidJob(customer_id='C-101', table1_principal_returned=2000) # Returned: 2000
        job3 = AllPidJob(customer_id='C-101', table3_opening_balance=3000, table3_principal_returned=500) # Given: 3000, Returned: 500
        
        # Transaction for another customer, should be ignored
        job4 = AllPidJob(customer_id='C-102', table1_opening_balance=9999)

        db.session.add_all([job1, job2, job3, job4])
        db.session.commit()

    # 1. ทดสอบลูกค้า C-101
    # ยอดคงค้างที่คาดหวัง = (10000 + 5000 + 3000) - (2000 + 500) = 18000 - 2500 = 15500
    response_c101 = logged_in_client.get('/api/customer-balance/C-101')
    assert response_c101.status_code == 200
    data_c101 = json.loads(response_c101.data)
    assert data_c101['total_transactions_value'] == 15500.0

    # 2. ทดสอบลูกค้าที่ไม่มีธุรกรรม
    response_no_trans = logged_in_client.get('/api/customer-balance/C-999')
    assert response_no_trans.status_code == 200
    data_no_trans = json.loads(response_no_trans.data)
    assert data_no_trans['total_transactions_value'] == 0

def test_save_approved_data_api(logged_in_client, app):
    """
    GIVEN a Flask application and an approved customer record
    WHEN the '/save-approved-data' endpoint is called with valid transaction data
    THEN check that the approval status is updated and new job records are created correctly
    """
    # 1. Setup: Create initial data in the test database
    with app.app_context():
        # An approval record that is ready to be "closed"
        approval_to_close = Approval(
            customer_id='C-202',
            full_name='สมศรี มีสุข',
            status='รอปิดจ๊อบ', # The initial status
            approved_amount=50000.00,
            assigned_company='STARLOAN'
        )
        db.session.add(approval_to_close)
        db.session.commit()

    # 3. Prepare the payload for the API
    payload = {
        "customer_id": "C-202",
        "fullname": "สมศรี มีสุข",
        "assigned_company": "STARLOAN",
        "interest": "20",
        "transactions": [
            {"company": "STARLOAN", "action_type": "เปิดยอด", "table_select": "โต๊ะ1", "amount": "15000"},
            {"company": "GLORYCASH", "action_type": "เปิดสุทธิ", "table_select": "โต๊ะ2", "amount": "5000"}
        ]
    }

    # 4. Call the API endpoint
    response = logged_in_client.post('/save-approved-data', json=payload)
    
    # 5. Assert the response from the API call
    assert response.status_code == 200
    response_data = json.loads(response.data)
    assert response_data['success'] is True

    # 6. Verify the database state AFTER the API call
    with app.app_context():
        # Check if the approval status was updated
        updated_approval = Approval.query.filter_by(customer_id='C-202').first()
        assert updated_approval is not None
        assert updated_approval.status == 'ปิดจ๊อบแล้ว'

        # Check if the AllPidJob records were created
        new_jobs = AllPidJob.query.filter_by(customer_id='C-202').order_by(AllPidJob.id).all()
        assert len(new_jobs) == 2
        assert new_jobs[0].company_name == 'STARLOAN'
        assert new_jobs[0].table1_opening_balance == 15000.00
        assert new_jobs[1].company_name == 'GLORYCASH'
        assert new_jobs[1].table2_net_opening == 5000.00

def test_update_customer_status_api(logged_in_client, app):
    """
    GIVEN a logged-in user and an existing customer record
    WHEN the '/update_customer_status' endpoint is called with various payloads
    THEN check that the customer status and related fields are updated correctly
    """
    # 1. Setup: Create a customer record
    with app.app_context():
        customer = CustomerRecord(
            customer_id='PID-STATUS-1',
            first_name='สถานะ',
            last_name='ทดสอบ',
            status='รอติดต่อ',
            remarks='Initial remark.'
        )
        db.session.add(customer)
        db.session.commit()
        customer_db_id = customer.id

    # 2. Test simple status update
    payload_simple = {'row_index': customer_db_id, 'new_status': 'รออนุมัติ'}
    response_simple = logged_in_client.post('/update_customer_status', json=payload_simple)
    assert response_simple.status_code == 200
    assert json.loads(response_simple.data)['success'] is True

    with app.app_context():
        updated_customer_1 = db.session.get(CustomerRecord, customer_db_id)
        assert updated_customer_1.status == 'รออนุมัติ'

    # 3. Test update with inspection data
    payload_inspect = {
        'row_index': customer_db_id,
        'new_status': 'รอตรวจ',
        'inspection_date': '2025-10-20',
        'inspection_time': '14:30',
        'inspector': 'สมศักดิ์'
    }
    response_inspect = logged_in_client.post('/update_customer_status', json=payload_inspect)
    assert response_inspect.status_code == 200

    with app.app_context():
        updated_customer_2 = db.session.get(CustomerRecord, customer_db_id)
        assert updated_customer_2.status == 'รอตรวจ'
        assert updated_customer_2.inspection_date == date(2025, 10, 20)
        assert updated_customer_2.inspection_time == time(14, 30)
        assert updated_customer_2.inspector == 'สมศักดิ์'

    # 4. Test update with note (e.g., cancellation)
    payload_cancel = {
        'row_index': customer_db_id,
        'new_status': 'ยกเลิก',
        'note': 'ลูกค้าไม่รับสาย'
    }
    response_cancel = logged_in_client.post('/update_customer_status', json=payload_cancel)
    assert response_cancel.status_code == 200

    with app.app_context():
        updated_customer_3 = db.session.get(CustomerRecord, customer_db_id)
        assert updated_customer_3.status == 'ยกเลิก'
        assert 'Initial remark.' in updated_customer_3.remarks
        assert '[สถานะ: ยกเลิก] ลูกค้าไม่รับสาย' in updated_customer_3.remarks

def test_dashboard_chart_apis(logged_in_client, app):
    """
    GIVEN a logged-in user and customer records with various dates and groups
    WHEN the dashboard chart data APIs are called
    THEN check that the aggregated data is correct
    """
    # 1. Setup: Create data for charts
    with app.app_context():
        db.session.add_all([
            CustomerRecord(customer_id='PID-CHART-1', application_date=date(2024, 1, 10), main_customer_group='ค้าขาย', province='กรุงเทพมหานคร', application_channel='FACEBOOK สตาร์โลน'),
            CustomerRecord(customer_id='PID-CHART-2', application_date=date(2024, 1, 15), main_customer_group='พนักงาน', province='กรุงเทพมหานคร', application_channel='ไลน์@สตาร์โลน'),
            CustomerRecord(customer_id='PID-CHART-3', application_date=date(2024, 2, 5), main_customer_group='ค้าขาย', province='เชียงใหม่', application_channel='FACEBOOK สตาร์โลน'),
        ])
        db.session.commit()

    # 2. Test /get_customer_chart_data
    response_cust_chart = logged_in_client.get('/get_customer_chart_data')
    assert response_cust_chart.status_code == 200
    data_cust_chart = json.loads(response_cust_chart.data)
    assert data_cust_chart['chart_data']['2024']['01']['ค้าขาย'] == 1
    assert data_cust_chart['chart_data']['2024']['01']['พนักงาน'] == 1
    assert data_cust_chart['chart_data']['2024']['02']['ค้าขาย'] == 1

    # 3. Test /get_channel_province_chart_data
    response_chan_chart = logged_in_client.get('/get_channel_province_chart_data')
    assert response_chan_chart.status_code == 200
    data_chan_chart = json.loads(response_chan_chart.data)
    assert data_chan_chart['chart_data']['2024']['01']['กรุงเทพมหานคร']['FACEBOOK สตาร์โลน']['ค้าขาย'] == 1
    assert data_chan_chart['chart_data']['2024']['02']['เชียงใหม่']['FACEBOOK สตาร์โลน']['ค้าขาย'] == 1