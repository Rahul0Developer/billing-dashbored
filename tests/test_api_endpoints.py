"""
End-to-End API Integration Tests for Supermarket POS Engine
Validates FastAPI endpoints for POS billing, returns, order voiding, register shifts,
inventory adjustments, customer analytics, and multi-period financial reporting.
"""

import unittest
from fastapi.testclient import TestClient
from backend.app import app


class TestRetailStoreAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_check(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ONLINE")
        self.assertIn("supermarket", data)

    def test_catalog_and_search(self):
        # Search for product
        res = self.client.get("/api/products/search?q=Atta")
        self.assertEqual(res.status_code, 200)
        matches = res.json()
        self.assertGreater(len(matches), 0)
        self.assertIn("Atta", matches[0]["name"])

    def test_pos_calculate_cart(self):
        # Scanned barcode for Aashirvaad Atta
        payload = {
            "items": [{"barcode": "8901030889211", "quantity": 2}],
            "customer_phone": "9876543210"
        }
        res = self.client.post("/api/pos/calculate", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["items_count"], 2)
        self.assertGreater(data["grand_total"], 0.0)
        self.assertIn("total_savings", data)
        self.assertIn("total_tax", data)

    def test_insufficient_stock_error_handling(self):
        # Request unrealistic quantity of 99999 units
        payload = {
            "items": [{"barcode": "8901030889211", "quantity": 99999}],
            "payment_method": "CASH",
            "tendered_amount": 50000000.0,
            "cashier_id": "CASHIER-01"
        }
        res = self.client.post("/api/pos/checkout", json=payload)
        self.assertEqual(res.status_code, 409)
        err = res.json()
        self.assertEqual(err["code"], "INSUFFICIENT_STOCK")
        self.assertIn("Insufficient stock", err["error"])

    def test_pos_checkout_return_and_dashboard_flow(self):
        # 1. Successful Checkout
        checkout_payload = {
            "items": [{"barcode": "8901030889211", "quantity": 2}],
            "payment_method": "CASH",
            "tendered_amount": 1000.0,
            "cashier_id": "CASHIER-01",
            "cashier_name": "Rajesh Sharma",
            "customer_phone": "9811122233",
            "customer_name": "Karan Malhotra"
        }
        checkout_res = self.client.post("/api/pos/checkout", json=checkout_payload)
        self.assertEqual(checkout_res.status_code, 200)
        c_data = checkout_res.json()
        self.assertTrue(c_data["success"])
        bill_num = c_data["bill_number"]
        self.assertGreater(c_data["grand_total"], 0.0)
        self.assertGreater(c_data["change_amount"], 0.0)
        self.assertIn("thermal_receipt_text", c_data)

        # 2. Verify Dashboard Reflects Sale
        dash_res = self.client.get("/api/dashboard?period=today")
        self.assertEqual(dash_res.status_code, 200)
        dash_data = dash_res.json()
        self.assertIn("today", dash_data)
        self.assertIn("weekly", dash_data)
        self.assertIn("monthly", dash_data)
        self.assertIn("yearly", dash_data)
        self.assertGreater(dash_data["today"]["revenue"], 0.0)

        # 3. Process Return with Valid Manager PIN
        return_payload = {
            "bill_number": bill_num,
            "items": [{"barcode": "8901030889211", "quantity": 1}],
            "manager_pin": "2222",
            "cashier_id": "CASHIER-01",
            "reason": "Customer changed mind"
        }
        ret_res = self.client.post("/api/returns/process", json=return_payload)
        self.assertEqual(ret_res.status_code, 200)
        ret_data = ret_res.json()
        self.assertTrue(ret_data["success"])
        self.assertGreater(ret_data["refund_amount"], 0.0)

        # 4. Attempt Return with Invalid PIN
        bad_pin_payload = {
            "bill_number": bill_num,
            "items": [{"barcode": "8901030889211", "quantity": 1}],
            "manager_pin": "0000",
            "cashier_id": "CASHIER-01"
        }
        bad_ret = self.client.post("/api/returns/process", json=bad_pin_payload)
        self.assertEqual(bad_ret.status_code, 403)
        self.assertEqual(bad_ret.json()["code"], "UNAUTHORIZED_MANAGER")

    def test_expenses_summary_endpoint(self):
        res = self.client.get("/api/expenses/summary")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("totals", data)
        self.assertIn("category_breakdown", data)
        self.assertIn("weekly_total", data)
        self.assertIn("monthly_total", data)
        self.assertIn("yearly_total", data)

    def test_customer_analytics_endpoint(self):
        res = self.client.get("/api/customers/top")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("top_customers", data)
        self.assertIsInstance(data["top_customers"], list)

    def test_branches_and_inter_branch_transfer_endpoints(self):
        # 1. List branches
        res = self.client.get("/api/branches")
        self.assertEqual(res.status_code, 200)
        branches = res.json()
        self.assertIsInstance(branches, list)
        self.assertGreater(len(branches), 0)
        self.assertIn("code", branches[0])
        self.assertIn("total_sales", branches[0])

        # 2. Register a new branch
        import random
        rnd = random.randint(100, 999)
        new_branch_payload = {
            "code": f"HYD-{rnd}",
            "name": "Hyderabad Hitec City Flagship",
            "address": "Cyber Towers, Hitec City",
            "city": "Hyderabad",
            "state": "Telangana",
            "pincode": "500081",
            "phone": "+91-40-67891234",
            "manager_name": "Suresh Reddy",
            "is_headquarters": False
        }
        create_res = self.client.post("/api/branches", json=new_branch_payload)
        self.assertEqual(create_res.status_code, 200)
        create_data = create_res.json()
        self.assertTrue(create_data["success"])
        branch_id = create_data["branch_id"]

        # 3. Check new branch inventory
        inv_res = self.client.get(f"/api/branches/{branch_id}/inventory")
        self.assertEqual(inv_res.status_code, 200)
        branch_inv = inv_res.json()
        self.assertIsInstance(branch_inv, list)
        self.assertGreater(len(branch_inv), 0)

        # 4. Inter-branch stock transfer via API
        # Transfer 3 units of Atta from BR-DEL-01 to Hyderabad branch
        transfer_payload = {
            "from_branch_id": "BR-DEL-01",
            "to_branch_id": branch_id,
            "barcode": "8901030889211",
            "quantity": 3,
            "reason": "Replenish new Hyderabad branch"
        }
        trans_res = self.client.post("/api/inventory/transfer", json=transfer_payload)
        self.assertEqual(trans_res.status_code, 200)
        trans_data = trans_res.json()
        self.assertTrue(trans_data["success"])
        self.assertEqual(trans_data["transferred_quantity"], 3)

    def test_customer_smart_recognition_and_insights_endpoints(self):
        # 0. Query customers or ensure one is registered
        cust_res = self.client.get("/api/customers")
        self.assertEqual(cust_res.status_code, 200)
        cust_list = cust_res.json()
        if len(cust_list) > 0:
            target_phone = cust_list[0]["phone"]
        else:
            self.client.post("/api/pos/checkout", json={
                "items": [{"barcode": "8901030889211", "quantity": 1}],
                "payment_method": "CASH",
                "tendered_amount": 500.0,
                "customer_phone": "9810188442",
                "customer_name": "Rahul Sharma"
            })
            target_phone = "9810188442"

        # 1. Lookup existing customer by phone
        res_phone = self.client.get(f"/api/customers/recognize?identifier={target_phone}")
        self.assertEqual(res_phone.status_code, 200)
        data_phone = res_phone.json()
        self.assertTrue(data_phone["found"])
        self.assertEqual(data_phone["phone"], target_phone)
        self.assertIn("membership_code", data_phone)
        self.assertIn("digital_card", data_phone)
        self.assertIn("loyalty_points", data_phone)

        # 2. Lookup by Membership Code
        mem_code = data_phone["membership_code"]
        res_code = self.client.get(f"/api/customers/recognize?identifier={mem_code}")
        self.assertEqual(res_code.status_code, 200)
        self.assertTrue(res_code.json()["found"])

        # 3. Lookup by 2D QR Code Payload
        qr_payload = f"RETAIL:MEM:{mem_code}:{target_phone}"
        res_qr = self.client.get(f"/api/customers/recognize?identifier={qr_payload}")
        self.assertEqual(res_qr.status_code, 200)
        self.assertTrue(res_qr.json()["found"])

        # 4. Customer Shopping Insights
        res_insights = self.client.get(f"/api/customers/{target_phone}/insights")
        self.assertEqual(res_insights.status_code, 200)
        ins_data = res_insights.json()
        self.assertEqual(ins_data["phone"], target_phone)
        self.assertIn("category_preferences", ins_data)
        self.assertIn("top_purchased_products", ins_data)
        self.assertIn("recent_orders", ins_data)

    def test_business_intelligence_endpoint(self):
        # Fetch comprehensive BI analytics
        res = self.client.get("/api/analytics/business-intelligence")
        self.assertEqual(res.status_code, 200)
        bi = res.json()

        self.assertIn("best_selling_products", bi)
        self.assertIn("slow_moving_stock", bi)
        self.assertIn("customer_retention", bi)
        self.assertIn("seasonal_demand", bi)
        self.assertIn("restock_priority", bi)

        # Verify key metrics exist
        self.assertIn("total_locked_capital", bi["slow_moving_stock"])
        self.assertIn("repeat_customer_rate_percent", bi["customer_retention"])
        self.assertIn("busiest_day", bi["seasonal_demand"])
        self.assertIn("estimated_total_restock_cost", bi["restock_priority"])


if __name__ == "__main__":
    unittest.main()
