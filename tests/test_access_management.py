import unittest
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch

from db.access import (
    load_app_users,
    update_user_access,
    validate_access_change,
)
from ui.access.page import access_change_preview
from ui.access.permissions import permission_matrix
import utils.auth.session as auth_session
from utils.auth.constants import NAV_SECTIONS, ROLE_PERMISSIONS


class AccessManagementTests(unittest.TestCase):
    @patch.object(auth_session.st, "session_state", new_callable=dict)
    def test_existing_supervisor_session_receives_new_logistics_permission(
        self, state
    ):
        state["current_user"] = {
            "username": "lead", "role": "supervisor",
            "can_view_logistics": False,
        }
        state["current_user_role_checked_at"] = 100

        with patch.object(auth_session.time, "monotonic", return_value=101):
            auth_session._refresh_current_user_role()

        self.assertTrue(state["current_user"]["can_view_logistics"])
        self.assertFalse(state["current_user"]["can_manage_logistics"])

    @patch.object(auth_session.st, "session_state", new_callable=dict)
    @patch.object(auth_session, "load_user")
    def test_active_session_refreshes_changed_database_role(
        self, load_user, state
    ):
        state["current_user"] = {"username": "worker", "role": "visitor"}
        state["current_user_role_checked_at"] = 1
        load_user.return_value = {
            "username": "worker", "display_name": "Worker",
            "role": "supervisor",
        }

        with patch.object(auth_session.time, "monotonic", return_value=100):
            auth_session._refresh_current_user_role()

        self.assertEqual(state["current_user"]["role"], "supervisor")
        self.assertTrue(state["current_user"]["can_view_logistics"])

    def test_only_admin_can_open_access_management(self):
        for role, permissions in ROLE_PERMISSIONS.items():
            with self.subTest(role=role):
                self.assertEqual(
                    "can_manage_access" in permissions,
                    role == "admin",
                )

    def test_access_management_has_separate_admin_navigation(self):
        system_items = next(
            items for title, items in NAV_SECTIONS if title == "系统管理"
        )
        self.assertEqual(
            system_items,
            [("access_management", "权限管理", "pages/12_权限管理.py")],
        )

    def test_supervisor_matrix_has_logistics_query_not_management(self):
        matrix = permission_matrix().set_index("角色")
        self.assertEqual(matrix.at["主管", "查看物流查询"], "✓")
        self.assertEqual(matrix.at["主管", "同步ERP、OCR与物流管理"], "")
        self.assertEqual(matrix.at["主管", "管理用户角色"], "")

    def test_access_preview_lists_added_and_removed_permissions(self):
        preview = access_change_preview({
            "user_name": "worker",
            "role": "visitor",
            "is_active": True,
        }, "supervisor", True)

        self.assertTrue(preview["是否变化"])
        self.assertIn("查看物流查询", preview["新增权限"])
        self.assertEqual(preview["移除权限"], "无")

    def test_admin_cannot_disable_or_demote_self(self):
        with self.assertRaisesRegex(ValueError, "不能停用"):
            validate_access_change("admin-user", "admin", False, "admin-user")
        with self.assertRaisesRegex(ValueError, "不能停用"):
            validate_access_change(
                "admin-user", "supervisor", True, "admin-user"
            )

    def test_load_users_selects_no_password_fields(self):
        supabase = Mock()
        execute = (
            supabase.table.return_value.select.return_value
            .order.return_value.execute
        )
        execute.return_value.data = [{
            "name": "Sam", "user_name": "sam", "employee_id": "S1",
            "department": "客服", "role": "supervisor", "is_active": True,
        }]

        users = load_app_users(supabase)

        self.assertEqual(users.iloc[0]["role"], "supervisor")
        selected = supabase.table.return_value.select.call_args.args[0]
        self.assertNotIn("password", selected)

    def test_update_access_uses_audited_database_function(self):
        supabase = Mock()
        execute = supabase.rpc.return_value.execute
        execute.return_value.data = [{
            "user_name": "sam", "role": "supervisor", "is_active": True,
        }]

        result = update_user_access(
            supabase, "sam", "supervisor", True, "admin-user"
        )

        self.assertEqual(result[0]["role"], "supervisor")
        supabase.rpc.assert_called_once_with("update_app_user_access", {
            "p_username": "sam",
            "p_role": "supervisor",
            "p_is_active": True,
            "p_changed_by": "admin-user",
        })

    def test_database_function_rechecks_active_admin_actor(self):
        sql = (
            Path(__file__).resolve().parents[1]
            / "sql" / "access" / "02_role_management.sql"
        ).read_text()
        self.assertIn("actor.role", sql)
        self.assertIn("actor.is_active", sql)
        self.assertIn("Only an active admin can change access", sql)


if __name__ == "__main__":
    unittest.main()
