import json
from app import db, Approval, BadDebtRecord, PullPlugRecord, ReturnPrincipalRecord

def test_mark_as_bad_debt_api(logged_in_client, app):
    """
    GIVEN a Flask application and an approved customer record
    WHEN the '/mark_as_bad_debt' endpoint is called with valid data
    THEN check that the approval status is updated and a bad debt record is created
    """
    # 1. Setup: Create initial data
    with app.app_context():
        # An approval record to be marked as bad debt
        approval_to_fail = Approval(
            customer_id='C-303',
            full_name='นายสมควร เจ๊ง',
            status='ปิดจ๊อบแล้ว', # A customer who has taken a loan
            approved_amount=25000.00,
            phone_number='0899998888'
        )
        db.session.add(approval_to_fail)
        db.session.commit()

    # 3. Prepare payload
    payload = {
        "customer_id": "C-303",
        "phone": "0899998888",
        "outstanding_balance": "15000",
        "notes": "ขาดการติดต่อเกิน 30 วัน"
    }

    # 4. Call API
    response = logged_in_client.post('/mark_as_bad_debt', json=payload)

    # 5. Assert response
    assert response.status_code == 200
    response_data = json.loads(response.data)
    assert response_data['success'] is True
    assert response_data['message'] == 'บันทึกหนี้เสียเรียบร้อยแล้ว'

    # 6. Verify database state
    with app.app_context():
        # Check Approval status update
        updated_approval = Approval.query.filter_by(customer_id='C-303').first()
        assert updated_approval is not None
        assert updated_approval.status == 'หนี้เสีย'

        # Check BadDebtRecord creation
        bad_debt_record = BadDebtRecord.query.filter_by(customer_id='C-303').first()
        assert bad_debt_record is not None
        assert bad_debt_record.customer_name == 'นายสมควร เจ๊ง'
        assert bad_debt_record.outstanding_balance == 15000.00
        assert bad_debt_record.notes == "ขาดการติดต่อเกิน 30 วัน"
        assert bad_debt_record.marked_by == 'testuser'

def test_mark_as_pull_plug_api(logged_in_client, app):
    """
    GIVEN a Flask application and an approved customer record
    WHEN the '/mark_as_pull_plug' endpoint is called with valid data
    THEN check that the approval status is updated and a pull plug record is created
    """
    # 1. Setup: Create initial data
    with app.app_context():
        # An approval record to be marked as pull plug
        approval_to_pull = Approval(
            customer_id='C-404',
            full_name='นายสมหวัง ยังไหว',
            status='ปิดจ๊อบแล้ว',
            phone_number='0811112222'
        )
        db.session.add(approval_to_pull)
        db.session.commit()

    # 3. Prepare payload
    payload = {
        "customer_id": "C-404",
        "phone": "0811112222",
        "pull_plug_amount": "5000",
        "notes": "เจรจาสำเร็จ"
    }

    # 4. Call API
    response = logged_in_client.post('/mark_as_pull_plug', json=payload)

    # 5. Assert response
    assert response.status_code == 200
    response_data = json.loads(response.data)
    assert response_data['success'] is True
    assert response_data['message'] == 'บันทึกการชั๊กปลั๊กเรียบร้อยแล้ว'

    # 6. Verify database state
    with app.app_context():
        updated_approval = Approval.query.filter_by(customer_id='C-404').first()
        assert updated_approval.status == 'ชั๊กปลั๊ก'

        pull_plug_record = PullPlugRecord.query.filter_by(customer_id='C-404').first()
        assert pull_plug_record is not None
        assert pull_plug_record.customer_name == 'นายสมหวัง ยังไหว'
        assert pull_plug_record.pull_plug_amount == 5000.00
        assert pull_plug_record.notes == "เจรจาสำเร็จ"
        assert pull_plug_record.marked_by == 'testuser'

def test_mark_as_return_principal_api(logged_in_client, app):
    """
    GIVEN a Flask application and an approved customer record
    WHEN the '/mark_as_return_principal' endpoint is called with valid data
    THEN check that the approval status is updated and a return principal record is created
    """
    # 1. Setup: Create initial data
    with app.app_context():
        # An approval record to be marked as return principal
        approval_to_return = Approval(
            customer_id='C-505',
            full_name='นางสาวสมใจ ได้คืน',
            status='ปิดจ๊อบแล้ว',
            phone_number='0822223333'
        )
        db.session.add(approval_to_return)
        db.session.commit()

    # 3. Prepare payload
    payload = {
        "customer_id": "C-505",
        "phone": "0822223333",
        "return_amount": "10000",
        "notes": "ลูกค้าขอคืนต้นบางส่วน"
    }

    # 4. Call API
    response = logged_in_client.post('/mark_as_return_principal', json=payload)

    # 5. Assert response
    assert response.status_code == 200
    response_data = json.loads(response.data)
    assert response_data['success'] is True
    assert response_data['message'] == 'บันทึกการคืนต้นเรียบร้อยแล้ว'

    # 6. Verify database state
    with app.app_context():
        updated_approval = Approval.query.filter_by(customer_id='C-505').first()
        assert updated_approval.status == 'คืนต้น'

        return_record = ReturnPrincipalRecord.query.filter_by(customer_id='C-505').first()
        assert return_record is not None
        assert return_record.customer_name == 'นางสาวสมใจ ได้คืน'
        assert return_record.return_amount == 10000.00
        assert return_record.notes == "ลูกค้าขอคืนต้นบางส่วน"
        assert return_record.marked_by == 'testuser'