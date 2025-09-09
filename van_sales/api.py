import frappe
import json
from frappe.auth import LoginManager
from frappe.utils import flt
from frappe.utils.password import get_decrypted_password

@frappe.whitelist(allow_guest=True)
def login_and_get_keys(username: str, password: str):
    try:
        login_manager = LoginManager()
        login_manager.authenticate(username, password)
        login_manager.post_login()

        user = frappe.session.user
        user_doc = frappe.get_doc("User", user)

        # Ensure API keys are generated
        if not user_doc.api_key:
            user_doc.api_key = frappe.generate_hash(length=15)
        # if not user_doc.api_secret:
        user_doc.api_secret = frappe.generate_hash(length=15)
        user_doc.save(ignore_permissions=True)

        key = user_doc.api_key
        secret = get_decrypted_password("User", user, "api_secret")

        frappe.local.login_manager.logout()

        frappe.local.response.update({
            "data": {
                "message": "Login successful",
                "api_key": key,
                "api_secret": secret
            },
            "home_page": "/login",
            "full_name": user_doc.full_name
        })

        return 
    except frappe.AuthenticationError:
        frappe.local.response.http_status_code = 401
        return {"error": "Invalid username or password"}
    
    except Exception as e:
        frappe.local.response.http_status_code = 401
        return {"error": str(e)}


@frappe.whitelist()
def get_customers(limit_start=0, limit_page_length=10, filters=None, fields=None, order_by="creation desc"):
    try:
        # Parse JSON strings (if passed from frontend)
        if isinstance(filters, str):
            filters = json.loads(filters)
        if isinstance(fields, str):
            fields = json.loads(fields)

        # Default fields if none provided
        if not fields:
            fields = ["name", "customer_name", "customer_type", "mobile_no", "email_id"]

        # Get total count with filters
        total_count = frappe.db.count("Customer", filters=filters)

        # Get paginated data
        customers = frappe.get_all(
            "Customer",
            filters=filters,
            fields=fields,
            order_by=order_by,
            limit_start=int(limit_start),
            limit_page_length=int(limit_page_length)
        )

        frappe.local.response.update({
            "data": {
                "total_count": total_count,
                "results": customers
            }
        })

        return

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "get_customers API Error")
        frappe.throw("Something went wrong while fetching customers.")

@frappe.whitelist()
def get_sales_orders_with_children(filters=None,limit_start=0, limit_page_length=10):
    """
    Return Sales Orders with their items and sales_team child tables.
    """
    if isinstance(filters, str):
            filters = json.loads(filters)

    sales_orders = frappe.get_all(
        "Sales Order",
        filters=filters,
        fields=['name'],
        start=limit_start,
        page_length=limit_page_length,
        order_by="transaction_date desc"
    )

    total_count = frappe.db.count("Sales Order", filters=filters)

    results = []
    for so in sales_orders:
        so_doc = frappe.get_doc("Sales Order", so.name)

        # only the following fields will be fetched from so items table
        items = [
            {
                "item_code": row.item_code,
                "item_name": row.item_name,
                "uom": row.uom,
                "qty": row.qty,
                "rate": row.rate,
                "amount": row.amount,
            }
            for row in so_doc.items
        ]

        results.append({
            "name": so_doc.name,
            "customer": so_doc.customer,
            "transaction_date": so_doc.transaction_date,
            "status": so_doc.status,
            "items": items,              # child table
            "sales_team": so_doc.sales_team,     # child table
            "grand_total": so_doc.grand_total
        })

    frappe.local.response.update({
            "data": {
                "total_count": total_count,
                "results": results
            }
        })

    return

@frappe.whitelist()
def get_customer_summary(customer, company=None):
    """
    Returns total_billed, total_paid, total_pending for a customer.
    Uses Sales Invoice aggregated values so Payment Entries are included.
    """
    filters = {"customer": customer, "docstatus": 1}

    totals = frappe.db.get_all(
        "Sales Invoice",
        filters=filters,
        fields=[
            "sum(base_grand_total) as total_billed",
            "sum(outstanding_amount) as total_pending"
        ]
    )[0]

    total_billed = flt(totals.total_billed)
    total_pending = flt(totals.total_pending)
    total_paid = total_billed - total_pending

    return {
        "customer": customer,
        "total_billed": total_billed,
        "total_paid": total_paid,
        "total_pending": total_pending
    }

@frappe.whitelist()
def get_sales_invoices_with_tables(filters=None,limit_start=0, limit_page_length=10):

    if isinstance(filters, str):
            filters = json.loads(filters)

    invoices = frappe.db.get_all(
        "Sales Invoice",
        filters=filters,
        fields=['name'],
        start=limit_start,
        page_length=limit_page_length,
        order_by="posting_date desc"
        )
    
    total_count = frappe.db.count("Sales Invoice", filters=filters)

    results = []
    for si in invoices:
        si_doc = frappe.get_doc("Sales Invoice", si.name)

        # only the following fields will be fetched from si items table
        items = [
            {
                "item_code": row.item_code,
                "item_name": row.item_name,
                "uom": row.uom,
                "qty": row.qty,
                "rate": row.rate,
                "amount": row.amount,
            }
            for row in si_doc.items
        ]

        results.append({
            "name": si_doc.name,
            "customer": si_doc.customer,
            "posting_date": si_doc.posting_date,
            "status": si_doc.status,
            "items": items,              # child table
            "grand_total": si_doc.grand_total
        })

    frappe.local.response.update({
            "data": {
                "total_count": total_count,
                "results": results
            }
        })

    return