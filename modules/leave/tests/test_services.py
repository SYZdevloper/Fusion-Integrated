"""Integration tests for leave services and workflow lifecycles."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from fusion_auth.principal import Principal
from modules.leave.models import (
    LeaveApplication,
    LeaveBalance,
)
from modules.leave.services import (
    applications as app_services,
)
from modules.leave.services import (
    approvals as approval_services,
)
from modules.leave.services import (
    balances as balance_services,
)
from modules.leave.services import (
    cancellations as cancellation_services,
)
from modules.leave.services import (
    offline as offline_services,
)
from modules.leave.services import (
    resumptions as resumption_services,
)
from modules.leave.services import (
    substitutes as substitute_services,
)
from modules.leave.services import (
    yearend as yearend_services,
)


def make_principal(user_id=1001, username="testuser", kind="staff", role="staff"):
    return Principal(
        user_id=user_id,
        username=username,
        display_name=f"User {user_id}",
        kind=kind,
        active_role=role,
        roles=(role,),
        permissions=frozenset([
            "leave.request.create",
            "leave.request.view_self",
            "leave.request.delete",
            "leave.request.substitute",
            "leave.request.view",
            "leave.request.approve",
            "leave.balance.update",
            "leave.type.manage",
            "leave.calendar.view",
            "leave.offline.record",
        ]),
        modules=("leave",),
    )


@pytest.mark.django_db
def test_new_cl_without_substitute_workflow_bw_el_01():
    """BW-EL-01: CL applied -> Unit Head approves -> Approved & balance deducted."""
    applicant = make_principal(user_id=101, kind="staff")
    unit_head = make_principal(user_id=201, role="HOD")

    balance_services.ensure_user_balances_initialized(101, 2026, "staff")
    init_bal = LeaveBalance.objects.get(user_id=101, year=2026, leave_type="CL").balance

    # Apply 2 days of CL
    app = app_services.submit_application(
        principal=applicant,
        data={
            "leave_type": "CL",
            "start_date": date(2026, 10, 5),  # Monday
            "end_date": date(2026, 10, 6),    # Tuesday
            "reason": "Family function",
        },
    )
    assert app.status == "AWAITING_UNIT_HEAD"
    assert app.days_count == Decimal("2.0")

    # Unit Head approves
    app_approved = approval_services.review_at_unit_head(
        application_id=app.pk,
        principal=unit_head,
        decision="APPROVED",
        remarks="Approved by HOD",
    )
    assert app_approved.status == "APPROVED"

    # Check balance deducted
    new_bal = LeaveBalance.objects.get(user_id=101, year=2026, leave_type="CL").balance
    assert new_bal == init_bal - Decimal("2.0")


@pytest.mark.django_db
def test_substitute_flow_and_decline_replacement_bw_el_03():
    """BW-EL-03: Substitute declines -> replacement nominated -> replacement accepts -> Unit Head approves."""
    applicant = make_principal(user_id=102, kind="staff")
    sub1 = make_principal(user_id=301, kind="staff")
    sub2 = make_principal(user_id=302, kind="staff")
    unit_head = make_principal(user_id=201, role="HOD")

    balance_services.ensure_user_balances_initialized(102, 2026, "staff")

    app = app_services.submit_application(
        principal=applicant,
        data={
            "leave_type": "CL",
            "start_date": date(2026, 10, 12),
            "end_date": date(2026, 10, 12),
            "reason": "Personal work",
            "substitute_user_id": 301,
        },
    )
    assert app.status == "AWAITING_SUBSTITUTE"

    # Sub 1 declines
    app_declined = substitute_services.respond_substitute(app.pk, sub1, accept=False, remarks="Busy")
    assert app_declined.status == "SUBSTITUTE_DECLINED"

    # Applicant nominates Sub 2
    app_replaced = substitute_services.replace_substitute(app.pk, applicant, new_substitute_id=302)
    assert app_replaced.status == "AWAITING_SUBSTITUTE"
    assert app_replaced.substitute_user_id == 302

    # Sub 2 accepts
    app_accepted = substitute_services.respond_substitute(app.pk, sub2, accept=True, remarks="Will cover")
    assert app_accepted.status == "AWAITING_UNIT_HEAD"

    # Unit Head approves
    final_app = approval_services.review_at_unit_head(app.pk, unit_head, decision="APPROVED")
    assert final_app.status == "APPROVED"


@pytest.mark.django_db
def test_higher_sanction_flow_bw_el_04():
    """BW-EL-04: EL -> Unit Head recommends -> Establishment routes -> Final sanction."""
    applicant = make_principal(user_id=103, kind="staff")
    unit_head = make_principal(user_id=201, role="HOD")
    estt = make_principal(user_id=202, role="dr_establishment")
    director = make_principal(user_id=203, role="Director")

    balance_services.ensure_user_balances_initialized(103, 2026, "staff")

    app = app_services.submit_application(
        principal=applicant,
        data={
            "leave_type": "EL",
            "start_date": date(2026, 10, 5),
            "end_date": date(2026, 10, 9),
            "reason": "Annual leave",
        },
    )
    assert app.status == "AWAITING_UNIT_HEAD"

    # Unit Head recommends (does NOT approve final, EL requires higher sanction)
    app = approval_services.review_at_unit_head(app.pk, unit_head, decision="RECOMMENDED")
    assert app.status == "AWAITING_ESTABLISHMENT"

    # Establishment routes
    app = approval_services.route_at_establishment(app.pk, estt, remarks="Service verified")
    assert app.status == "AWAITING_SANCTION"

    # Director sanctions
    app = approval_services.final_sanction(app.pk, director, decision="APPROVED", remarks="Sanctioned")
    assert app.status == "APPROVED"


@pytest.mark.django_db
def test_cancellation_and_balance_restoration_cw_el_02():
    """CW-EL-02: Approved leave cancellation restores deducted balance."""
    applicant = make_principal(user_id=104, kind="staff")
    unit_head = make_principal(user_id=201, role="HOD")

    balance_services.ensure_user_balances_initialized(104, 2026, "staff")
    init_bal = LeaveBalance.objects.get(user_id=104, year=2026, leave_type="CL").balance

    # Future leave
    future_start = date.today() + timedelta(days=10)
    future_end = future_start + timedelta(days=1)

    app = app_services.submit_application(
        principal=applicant,
        data={"leave_type": "CL", "start_date": future_start, "end_date": future_end, "reason": "Future trip"},
    )
    approval_services.review_at_unit_head(app.pk, unit_head, decision="APPROVED")

    bal_after_approval = LeaveBalance.objects.get(user_id=104, year=2026, leave_type="CL").balance
    assert bal_after_approval < init_bal

    # Request cancellation
    cancellation_services.request_cancellation(app.pk, applicant, reason="Trip cancelled")
    app.refresh_from_db()
    assert app.status == "AWAITING_CANCELLATION"

    # Review cancellation -> approve
    cancellation_services.review_cancellation(app.pk, unit_head, decision="APPROVED")
    app.refresh_from_db()
    assert app.status == "CANCELLED"

    # Balance restored!
    bal_after_cancel = LeaveBalance.objects.get(user_id=104, year=2026, leave_type="CL").balance
    assert bal_after_cancel == init_bal


@pytest.mark.django_db
def test_resumption_review_cw_el_04():
    """CW-EL-04: Early resumption refunds balance difference."""
    applicant = make_principal(user_id=105, kind="staff")
    unit_head = make_principal(user_id=201, role="HOD")
    sanction_auth = make_principal(user_id=203, role="Director")

    balance_services.ensure_user_balances_initialized(105, 2026, "staff")

    app = LeaveApplication.objects.create(
        applicant_user_id=105,
        leave_type="EL",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 10),  # 10 days
        days_count=Decimal("10.0"),
        reason="Medical recuperation",
        status="APPROVED",
    )
    bal = LeaveBalance.objects.get(user_id=105, year=2026, leave_type="EL")
    bal.balance -= Decimal("10.0")
    bal.availed += Decimal("10.0")
    bal.save()

    # Employee resumed early on Oct 8 (availed only 8 days instead of 10)
    resumption_services.submit_resumption(app.pk, applicant, actual_resumption_date=date(2026, 10, 8))
    app.refresh_from_db()
    assert app.resumption_status == "SUBMITTED"

    # Authority reviews resumption
    resumption_services.review_resumption(app.pk, sanction_auth)
    app.refresh_from_db()
    assert app.resumption_status == "REVIEWED"
    assert app.resumption_days_adjusted == Decimal("-2.0")

    # 2 days refunded!
    bal.refresh_from_db()
    assert bal.balance == Decimal("22.0")  # (30 - 10) + 2 = 22


@pytest.mark.django_db
def test_retrospective_offline_leave_el_uc_016():
    """EL-UC-016: Offline leave recorded with sanction reference and balance synchronized."""
    admin = make_principal(user_id=999, role="admin")

    app = offline_services.record_offline_leave(
        admin_principal=admin,
        applicant_user_id=106,
        applicant_kind="staff",
        leave_type="CL",
        start_date=date(2026, 10, 5),
        end_date=date(2026, 10, 5),
        reason="Medical emergency offline approved",
        sanction_ref="ESTT/2026/OFF/001",
        sanction_date=date(2026, 10, 4),
        sanctioned_by="Registrar",
    )
    assert app.status == "APPROVED"
    assert app.is_offline is True
    assert app.offline_sanction_ref == "ESTT/2026/OFF/001"

    bal = LeaveBalance.objects.get(user_id=106, year=2026, leave_type="CL")
    assert bal.availed == Decimal("1.0")
    assert bal.balance == Decimal("7.0")


@pytest.mark.django_db
def test_year_end_processing_el_uc_020():
    """EL-UC-020: Year-end processing lapsing CL/RH and converting Faculty VL 2:1 to EL."""
    # Faculty with 40 unused VL
    LeaveBalance.objects.create(
        user_id=2001,
        year=2026,
        leave_type="VL",
        credited=Decimal("60.0"),
        availed=Decimal("20.0"),
        balance=Decimal("40.0"),
    )
    LeaveBalance.objects.create(
        user_id=2001,
        year=2026,
        leave_type="CL",
        credited=Decimal("8.0"),
        availed=Decimal("3.0"),
        balance=Decimal("5.0"),
    )

    res = yearend_services.execute_year_end_processing(2026)
    assert res["employees_processed"] >= 1

    # In 2027:
    # CL should be re-credited to 8.0, availed 0.0
    cl_2027 = LeaveBalance.objects.get(user_id=2001, year=2027, leave_type="CL")
    assert cl_2027.balance == Decimal("8.0")

    # 40 VL converts to 20 EL in 2027!
    el_2027 = LeaveBalance.objects.get(user_id=2001, year=2027, leave_type="EL")
    assert el_2027.balance == Decimal("20.0")
