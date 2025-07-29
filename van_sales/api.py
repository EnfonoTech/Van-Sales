import frappe
import json
from frappe.auth import LoginManager
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
            fields = ["name", "customer_name", "customer_group", "territory"]

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

        return {
            "total_count": total_count,
            "data": customers
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "get_customers API Error")
        frappe.throw("Something went wrong while fetching customers.")
