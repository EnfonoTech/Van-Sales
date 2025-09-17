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
        if not user_doc.api_secret:
            user_doc.api_secret = frappe.generate_hash(length=15)
            user_doc.save(ignore_permissions=True)

        key = user_doc.api_key
        secret = get_decrypted_password("User", user, "api_secret")

        # frappe.local.login_manager.logout()

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

        for customer_dict in customers:
            summary = get_customer_summary(customer_dict.get('name'))
            customer_dict['total_billed'] = summary.get('total_billed')
            customer_dict['total_paid'] = summary.get('total_paid')
            customer_dict['total_pending'] = summary.get('total_pending')

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


@frappe.whitelist()
def create_sales_invoice_with_salesperson(invoice_data: dict):
    """
    Create Sales Invoice and auto-assign salesperson based on current user
    """

    if isinstance(invoice_data, str):
        invoice_data = frappe.parse_json(invoice_data)

    current_user = frappe.session.user

    employee = frappe.db.get_value("Employee", {"user_id": current_user}, "name")
    if not employee:
        frappe.throw(f"No Employee linked to User {current_user}")

    sales_person = frappe.db.get_value("Sales Person", {"employee": employee}, "name")
    if not sales_person:
        frappe.throw(f"No Sales Person linked to Employee {employee}")

    si = frappe.get_doc({
        "doctype": "Sales Invoice",
        **invoice_data
    })

    si.append("sales_team", {
        "sales_person": sales_person,
        "allocated_percentage": 100
    })

    si.insert(ignore_permissions=True)
    frappe.db.commit()

    return si

@frappe.whitelist()
def create_sales_order_with_salesperson(order_data: dict):
    """
    Create Sales Order and auto-assign salesperson based on current user
    """

    if isinstance(order_data, str):
        order_data = frappe.parse_json(order_data)

    current_user = frappe.session.user

    employee = frappe.db.get_value("Employee", {"user_id": current_user}, "name")
    if not employee:
        frappe.throw(f"No Employee linked to User {current_user}")

    sales_person = frappe.db.get_value("Sales Person", {"employee": employee}, "name")
    if not sales_person:
        frappe.throw(f"No Sales Person linked to Employee {employee}")

    default_company = frappe.db.get_single_value("Global Defaults", "default_company")
    if not default_company:
        frappe.throw("No default company found in Global Defaults")

    order_data.setdefault("company", default_company)

    so = frappe.get_doc({
        "doctype": "Sales Order",
        **order_data
    })

    so.append("sales_team", {
        "sales_person": sales_person,
        "allocated_percentage": 100
    })

    so.set_missing_values()

    so.insert(ignore_permissions=True)
    frappe.db.commit()

    return so

@frappe.whitelist()
def get_assigned_customers(limit_start=0, limit_page_length=10, filters=None, fields=None, order_by="creation desc"):
    try:
        # Parse JSON strings (if passed from frontend)
        if isinstance(filters, str):
            filters = json.loads(filters)
        if not filters:
            filters = {}
        if isinstance(fields, str):
            fields = json.loads(fields)

        # Default fields if none provided
        if not fields:
            fields = ["name", "customer_name", "customer_type", "mobile_no", "email_id"]

        current_user = frappe.session.user

        meta = frappe.get_meta("Employee")
        if meta.has_field("custom_customer_group"):
            employee_name, custom_customer_group = frappe.db.get_value(
            "Employee",
            {"user_id": current_user},
            ["name", "custom_customer_group"]
        ) or (None, None)
        if not employee_name:
            frappe.throw(f"No Employee linked to User {current_user}")
        if custom_customer_group:
            filters["customer_group"] = custom_customer_group
        else:
            frappe.throw("Employee Doctype does not have Assigned Customer Group field")

            
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

        for customer_dict in customers:
            summary = get_customer_summary(customer_dict.get('name'))
            customer_dict['total_billed'] = summary.get('total_billed')
            customer_dict['total_paid'] = summary.get('total_paid')
            customer_dict['total_pending'] = summary.get('total_pending')
        
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
