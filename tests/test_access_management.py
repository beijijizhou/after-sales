import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch

import pandas as pd

from db.access import (
    create_employee,
    load_app_users,
    load_employee_profile_audit,
    load_employee_status_audit,
    load_employees,
    normalize_employee_departments,
    save_role_definition,
    update_employee_profile,
    update_user_access,
    update_employee_status,
    validate_access_change,
    validate_employee_status_change,
    validate_role_definition,
)
from ui.access.page import access_change_preview, filter_access_users
from ui.people.models import (
    ALL_DEPARTMENTS,
    ALL_JOB_TITLES,
    employee_creation_error_message,
    employee_table,
    filter_employees_by_organization,
    filter_employees,
    manageable_employees,
    reset_stale_employee_selection,
)
from ui.people.profile import employee_profile_preview
from ui.people.status import (
    DEPARTURE_REASONS,
    REACTIVATION_REASONS,
    resolve_employment_reason,
)
from ui.access.permissions import (
    permission_group_matrix,
    permission_matrix,
    role_permission_detail,
    role_permission_summary,
)
from ui.access.role_editor import role_permission_preview
import utils.auth.session as auth_session
from utils.auth.constants import NAV_SECTIONS, ROLE_PERMISSIONS, ROLE_SUPERVISOR
from utils.auth.ui import visible_navigation_sections


class AccessManagementTests(unittest.TestCase):
    def test_employment_reason_dropdown_has_defaults_and_custom_fallback(self):
        self.assertEqual(DEPARTURE_REASONS[0], "员工主动离职")
        self.assertEqual(REACTIVATION_REASONS[0], "重新入职")
        self.assertEqual(
            resolve_employment_reason("员工主动离职"), "员工主动离职"
        )
        self.assertEqual(
            resolve_employment_reason("其他原因", " 搬离本地 "), "搬离本地"
        )
        self.assertEqual(resolve_employment_reason("其他原因", "  "), "")

    def test_empty_employee_audits_keep_employee_id_column(self):
        supabase = Mock()
        supabase.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value.data = []

        status = load_employee_status_audit(supabase)
        profile = load_employee_profile_audit(supabase)

        self.assertTrue(status.empty)
        self.assertTrue(profile.empty)
        self.assertIn("employee_id", status.columns)
        self.assertIn("employee_id", profile.columns)

    def test_supervisor_only_sees_same_department_subordinates(self):
        employees = pd.DataFrame([
            {"name": "本人", "user_name": "linda", "employee_id": "L1",
             "job_title": "质检", "role": "supervisor",
             "departments": ["DTF"]},
            {"name": "质检员工", "user_name": "qa", "employee_id": "E1",
             "job_title": "质检", "role": "visitor",
             "departments": ["DTF"]},
            {"name": "UV员工", "user_name": "uv", "employee_id": "E2",
             "job_title": "烫印", "role": "visitor",
             "departments": ["UV"]},
            {"name": "Damo", "user_name": "damo", "employee_id": "P1",
             "job_title": "主管", "role": "producer",
             "departments": ["DTF"]},
            {"name": "售后", "user_name": "after", "employee_id": "A1",
             "job_title": "售后", "role": "after_sales",
             "departments": ["DTF"]},
            {"name": "Admin", "user_name": "admin", "employee_id": "X1",
             "job_title": "管理员", "role": "admin",
             "departments": ["DTF"]},
            {"name": "普通访客", "user_name": "guest", "employee_id": "G1",
             "job_title": "员工", "role": "visitor",
             "departments": ["DTF"]},
        ])

        visible = manageable_employees(employees, {
            "username": "linda", "role": "supervisor",
            "departments": ["DTF"],
        })

        self.assertEqual(visible["employee_id"].tolist(), ["E1"])

    def test_admin_can_see_all_employee_levels(self):
        employees = pd.DataFrame([
            {"employee_id": "E1", "role": "visitor"},
            {"employee_id": "A1", "role": "after_sales"},
            {"employee_id": "X1", "role": "admin"},
        ])
        visible = manageable_employees(employees, {"role": "admin"})
        self.assertEqual(visible["employee_id"].tolist(), ["E1", "A1", "X1"])

    def test_employee_picker_filters_department_before_job_title(self):
        employees = pd.DataFrame([
            {"employee_id": "E1", "job_title": "质检", "departments": ["DTF"]},
            {"employee_id": "E2", "job_title": "烫印", "departments": ["DTF"]},
            {"employee_id": "E3", "job_title": "烫印", "departments": ["UV"]},
        ])

        filtered = filter_employees_by_organization(employees, "DTF", "烫印")

        self.assertEqual(filtered["employee_id"].tolist(), ["E2"])
        self.assertEqual(
            filter_employees_by_organization(
                employees, ALL_DEPARTMENTS, ALL_JOB_TITLES
            )["employee_id"].tolist(),
            ["E1", "E2", "E3"],
        )

    def test_visitor_navigation_removes_empty_groups_and_flattens_single_child(self):
        allowed = {"app", "qa"}
        sections = visible_navigation_sections(
            [
                ("售后查询", [
                    ("app", "订单与条码查询", "search.py"),
                    ("analysis", "人工登记分析", "analysis.py"),
                ]),
                ("库存", [("inventory", "库存", "inventory.py")]),
                (None, [("qa", "质检", "qa.py")]),
            ],
            {"app": "view", "analysis": "manage", "inventory": "stock", "qa": "qa"},
            allowed.__contains__,
        )

        self.assertEqual(sections, [
            ("售后查询", [("app", "订单与条码查询", "search.py")]),
            (None, [("qa", "质检", "qa.py")]),
        ])
        self.assertEqual(len(sections[0][1]), 1)

    def test_employee_filter_clears_only_stale_selected_employee(self):
        state = {"employee": "E1"}
        reset_stale_employee_selection(state, "employee", ["E2"])
        self.assertNotIn("employee", state)

        state = {"employee": "E2"}
        reset_stale_employee_selection(state, "employee", ["E2"])
        self.assertEqual(state["employee"], "E2")

    def test_duplicate_employee_name_directs_user_to_existing_roster(self):
        message = employee_creation_error_message(
            'duplicate key value violates unique constraint "users_name_key"; '
            'Key (name)=(吴雪珍) already exists'
        )

        self.assertIn("员工姓名已存在", message)
        self.assertIn("员工名单", message)
        self.assertNotIn("duplicate key", message)

    def test_supervisor_role_can_manage_employee_lifecycle(self):
        self.assertIn(
            "can_manage_people", ROLE_PERMISSIONS[ROLE_SUPERVISOR]
        )

    def test_role_and_status_filters_group_users_in_selected_role_order(self):
        users = pd.DataFrame([
            {
                "name": "售后二", "user_name": "after-2",
                "role": "after_sales", "is_active": True,
            },
            {
                "name": "主管一", "user_name": "lead-1",
                "role": "supervisor", "is_active": True,
            },
            {
                "name": "售后一", "user_name": "after-1",
                "role": "after_sales", "is_active": False,
            },
            {
                "name": "生产一", "user_name": "producer-1",
                "role": "producer", "is_active": True,
            },
        ])

        filtered = filter_access_users(
            users, ["supervisor", "after_sales"], "启用"
        )

        self.assertEqual(
            filtered["user_name"].tolist(), ["lead-1", "after-2"]
        )

    def test_empty_role_filter_clears_user_selection_source(self):
        users = pd.DataFrame([{
            "name": "主管一", "user_name": "lead-1",
            "role": "supervisor", "is_active": True,
        }])

        self.assertTrue(filter_access_users(users, [], "全部").empty)

    @patch.object(auth_session.st, "session_state", new_callable=dict)
    def test_existing_after_sales_session_receives_usps_permission(
        self, state
    ):
        state["current_user"] = {
            "username": "lead", "role": "after_sales",
            "can_view_logistics": False,
        }
        state["current_user_role_checked_at"] = 100

        with patch.object(auth_session.time, "monotonic", return_value=101):
            auth_session._refresh_current_user_role()

        self.assertTrue(state["current_user"]["can_view_logistics"])
        self.assertTrue(state["current_user"]["can_manage_logistics"])
        self.assertTrue(state["current_user"]["can_edit_inventory"])
        self.assertFalse(state["current_user"]["can_view_cost"])

    @patch.object(auth_session.st, "session_state", new_callable=dict)
    @patch.object(auth_session, "load_user")
    def test_active_session_refreshes_changed_database_role(
        self, load_user, state
    ):
        state["current_user"] = {"username": "worker", "role": "visitor"}
        state["current_user_role_checked_at"] = 1
        load_user.return_value = {
            "username": "worker", "display_name": "Worker",
            "role": "after_sales",
        }

        with patch.object(auth_session.time, "monotonic", return_value=100):
            auth_session._refresh_current_user_role()

        self.assertEqual(state["current_user"]["role"], "after_sales")
        self.assertTrue(state["current_user"]["can_view_logistics"])

    @patch.object(auth_session.st, "session_state", new_callable=dict)
    def test_database_permissions_override_hardcoded_role_defaults(self, state):
        auth_session.set_current_user({
            "username": "custom-manager",
            "display_name": "Custom Manager",
            "role": "custom_manager",
            "role_label": "自定义管理员",
            "permissions": ["can_manage_access", "can_view_logistics"],
        })

        self.assertTrue(state["current_user"]["can_manage_access"])
        self.assertTrue(state["current_user"]["can_view_logistics"])
        self.assertFalse(state["current_user"]["can_edit_inventory"])

    def test_access_management_has_separate_admin_navigation(self):
        system_items = next(
            items for title, items in NAV_SECTIONS if title == "系统管理"
        )
        self.assertEqual(
            system_items,
            [("access_management", "权限管理", "pages/12_权限管理.py")],
        )
        self.assertIn(
            ("register", "人员管理", "pages/0_注册.py"),
            next(items for title, items in NAV_SECTIONS if title is None),
        )

    def test_supervisor_matrix_has_logistics_query_not_management(self):
        roles, catalog, assigned = _dynamic_role_frames()
        matrix = permission_matrix(roles, catalog, assigned).set_index("角色")
        self.assertEqual(matrix.at["主管", "USPS官方API查询"], "✓")
        self.assertEqual(matrix.at["主管", "生产物流：ERP同步、OCR与管理"], "")
        self.assertEqual(matrix.at["主管", "管理用户与角色权限"], "")

    def test_role_permission_summary_is_compact_and_counted(self):
        roles, catalog, assigned = _dynamic_role_frames()

        summary = role_permission_summary(
            roles, catalog, assigned
        ).set_index("角色")

        self.assertEqual(summary.at["主管", "已启用权限"], 2)
        self.assertEqual(summary.at["主管", "全部权限"], 4)
        self.assertEqual(summary.at["主管", "覆盖率"], 50)

    def test_role_detail_can_filter_one_permission_group(self):
        roles, catalog, assigned = _dynamic_role_frames()

        detail = role_permission_detail(
            "supervisor", catalog, assigned, "物流"
        ).set_index("权限")

        self.assertEqual(len(detail), 2)
        self.assertEqual(detail.at["USPS官方API查询", "状态"], "✓ 已启用")
        self.assertEqual(
            detail.at["生产物流：ERP同步、OCR与管理", "状态"], "— 未启用"
        )

    def test_group_matrix_only_contains_selected_group(self):
        roles, catalog, assigned = _dynamic_role_frames()

        matrix = permission_group_matrix(
            "物流", roles, catalog, assigned
        )

        self.assertEqual(
            matrix.columns.tolist(),
            ["角色", "USPS官方API查询", "生产物流：ERP同步、OCR与管理"],
        )

    def test_access_preview_lists_added_and_removed_permissions(self):
        roles, catalog, assigned = _dynamic_role_frames()
        preview = access_change_preview({
            "user_name": "worker",
            "role": "visitor",
            "is_active": True,
        }, "supervisor", True, {
            "visitor": "游客", "supervisor": "主管",
        }, {
            "visitor": {"can_view_app"},
            "supervisor": {"can_view_app", "can_view_logistics"},
        }, catalog)

        self.assertTrue(preview["是否变化"])
        self.assertIn("USPS官方API查询", preview["新增权限"])
        self.assertEqual(preview["移除权限"], "无")

    def test_admin_cannot_disable_or_demote_self(self):
        with self.assertRaisesRegex(ValueError, "不能修改自己的角色"):
            validate_access_change("admin-user", "admin", False, "admin-user")
        with self.assertRaisesRegex(ValueError, "不能修改自己的角色"):
            validate_access_change(
                "admin-user", "supervisor", True, "admin-user"
            )

    def test_role_permission_preview_is_reviewable_row_by_row(self):
        _, catalog, _ = _dynamic_role_frames()

        preview = role_permission_preview(
            catalog,
            ["can_view_app", "can_manage_logistics"],
            ["can_view_app", "can_view_logistics"],
        ).set_index("权限标识")

        self.assertEqual(preview.at["can_view_app", "变化"], "保留")
        self.assertEqual(preview.at["can_view_logistics", "变化"], "新增")
        self.assertEqual(preview.at["can_manage_logistics", "变化"], "移除")

    def test_custom_role_validation_and_audited_save(self):
        validate_role_definition(
            "logistics_viewer", "物流查看员", ["can_view_logistics"]
        )
        supabase = Mock()
        supabase.rpc.return_value.execute.return_value.data = [{
            "role_key": "logistics_viewer",
            "role_name": "物流查看员",
        }]

        save_role_definition(
            supabase, "logistics_viewer", "物流查看员", "仅查询物流",
            ["can_view_logistics"], "admin-user",
        )

        supabase.rpc.assert_called_once_with("upsert_app_role", {
            "p_role_key": "logistics_viewer",
            "p_role_name": "物流查看员",
            "p_description": "仅查询物流",
            "p_permissions": ["can_view_logistics"],
            "p_changed_by": "admin-user",
        })

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

    def test_load_users_excludes_rows_without_login_account(self):
        supabase = Mock()
        execute = (
            supabase.table.return_value.select.return_value
            .order.return_value.execute
        )
        execute.return_value.data = [
            {
                "name": "Production Staff", "user_name": None,
                "employee_id": "P1", "department": "生产",
                "role": None, "is_active": True,
            },
            {
                "name": "Lead", "user_name": "lead",
                "employee_id": "S1", "department": "客服",
                "role": "supervisor", "is_active": True,
            },
        ]

        users = load_app_users(supabase)

        self.assertEqual(users["user_name"].tolist(), ["lead"])
        self.assertIsInstance(users.iloc[0]["user_name"], str)

    def test_people_roster_includes_employees_without_login_account(self):
        supabase = Mock()
        execute = (
            supabase.table.return_value.select.return_value
            .order.return_value.execute
        )
        execute.return_value.data = [
            {
                "name": "烫印员工", "user_name": None,
                "employee_id": "P1", "department": "烫印",
                "job_title": "烫印", "role": None, "is_active": True,
            },
            {
                "name": "离职质检", "user_name": "old-qa",
                "employee_id": "Q1", "department": "质检",
                "job_title": "质检", "role": "visitor", "is_active": False,
            },
        ]

        employees = load_employees(supabase)

        self.assertEqual(employees["employee_id"].tolist(), ["P1", "Q1"])
        self.assertEqual(
            filter_employees(employees, "已离职")["name"].tolist(),
            ["离职质检"],
        )
        table = employee_table(employees)
        self.assertEqual(table.iloc[0]["登录账号"], "—")
        self.assertEqual(table.iloc[1]["状态"], "已离职")

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

    def test_update_access_saves_multiple_production_departments(self):
        supabase = Mock()
        supabase.rpc.return_value.execute.return_value.data = [{
            "user_name": "qa", "role": "visitor",
            "is_active": True, "departments": ["DTF", "UV"],
        }]

        update_user_access(
            supabase, "qa", "visitor", True, "admin-user",
            departments=["dtf", "UV", "DTF"],
        )

        supabase.rpc.assert_called_once_with(
            "update_app_user_profile_access",
            {
                "p_username": "qa",
                "p_role": "visitor",
                "p_is_active": True,
                "p_departments": ["DTF", "UV"],
                "p_changed_by": "admin-user",
            },
        )

    def test_employee_departments_are_normalized_before_database_validation(self):
        self.assertEqual(
            normalize_employee_departments(["dtf", "UV", "DTF"]),
            ["DTF", "UV"],
        )
        with self.assertRaisesRegex(ValueError, "至少需要选择"):
            normalize_employee_departments([])
        self.assertEqual(normalize_employee_departments(["laser"]), ["LASER"])

    def test_employee_profile_preview_shows_job_and_department_move(self):
        preview = employee_profile_preview({
            "name": "员工一", "employee_id": "E1", "user_name": "worker",
            "job_title": "质检", "departments": ["DTF"],
        }, "烫印", ["UV"])

        self.assertEqual(preview["原岗位"], "质检")
        self.assertEqual(preview["新岗位"], "烫印")
        self.assertEqual(preview["原生产部门"], "DTF")
        self.assertEqual(preview["新生产部门"], "UV")
        self.assertTrue(preview["是否变化"])

    def test_people_change_controls_are_reactive_outside_streamlit_forms(self):
        people_ui = Path(__file__).resolve().parents[1] / "ui" / "people"
        profile_source = (people_ui / "profile.py").read_text()
        status_source = (people_ui / "status.py").read_text()

        self.assertNotIn("with st.form", profile_source)
        self.assertNotIn("with st.form", status_source)
        self.assertIn("st.button", profile_source)
        self.assertIn("st.button", status_source)

    def test_people_page_uses_status_and_action_as_parallel_main_tabs(self):
        page_source = (
            Path(__file__).resolve().parents[1] / "ui" / "people" / "page.py"
        ).read_text()

        self.assertIn(
            '"人员状态", "人员办理", "新增员工", "变更记录"',
            page_source,
        )
        self.assertIn('"办理事项", ["离职/复职", "人员调岗"]', page_source)
        self.assertNotIn('st.tabs(["离职/复职", "人员调岗"]', page_source)

    def test_employee_profile_update_uses_audited_rpc(self):
        supabase = Mock()
        supabase.rpc.return_value.execute.return_value.data = [{
            "employee_id": "E1", "job_title": "烫印",
            "departments": ["UV"],
        }]

        update_employee_profile(
            supabase, "E1", "烫印", ["uv"], "linda"
        )

        supabase.rpc.assert_called_once_with("update_employee_profile", {
            "p_employee_id": "E1", "p_job_title": "烫印",
            "p_departments": ["UV"], "p_changed_by": "linda",
        })

    def test_employee_registration_uses_atomic_database_rpc(self):
        supabase = Mock()
        supabase.rpc.return_value.execute.return_value.data = [{
            "employee_id": "qa-new_id", "departments": ["DTF", "UV"],
        }]

        result = create_employee(
            supabase, "新质检", "质检", ["DTF", "UV"],
            username="qa-new", password="secret",
        )

        supabase.rpc.assert_called_once_with(
            "register_employee_account",
            {
                "p_name": "新质检", "p_job_title": "质检",
                "p_departments": ["DTF", "UV"],
                "p_username": "qa-new", "p_password": "secret",
                "p_role": "visitor",
            },
        )
        self.assertEqual(result["employee_id"], "qa-new_id")

    def test_departure_requires_reason_and_uses_audited_rpc(self):
        with self.assertRaisesRegex(ValueError, "必须填写原因"):
            validate_employee_status_change(
                "E1", False, date(2026, 8, 19), "", "admin-user"
            )

        supabase = Mock()
        supabase.rpc.return_value.execute.return_value.data = [{
            "employee_id": "E1", "is_active": False,
        }]
        update_employee_status(
            supabase, "E1", False, date(2026, 8, 19),
            "员工主动离职", "admin-user",
        )

        supabase.rpc.assert_called_once_with(
            "update_employee_employment_status",
            {
                "p_employee_id": "E1", "p_is_active": False,
                "p_effective_date": "2026-08-19",
                "p_reason": "员工主动离职",
                "p_changed_by": "admin-user",
            },
        )

    def test_database_function_rechecks_active_admin_actor(self):
        sql_directory = (
            Path(__file__).resolve().parents[1]
            / "sql" / "access" / "role_management"
        )
        scripts = sorted(sql_directory.glob("[0-9][0-9]_*.sql"))
        self.assertEqual(len(scripts), 14)
        self.assertTrue(all(
            len(script.read_text().splitlines()) < 200 for script in scripts
        ))
        sql = "\n".join(script.read_text() for script in scripts)
        self.assertIn("actor.role", sql)
        self.assertIn("actor.is_active", sql)
        self.assertIn("app_actor_can_manage_access", sql)
        self.assertIn("app_role_change_audit", sql)
        self.assertIn("upsert_app_role", sql)
        self.assertIn("can_manage_people", sql)
        self.assertIn("update_employee_employment_status", sql)
        self.assertIn("cannot change own employment status", sql)
        self.assertIn("values ('supervisor', 'can_manage_people')", sql)
        supervisor_migration = (
            sql_directory / "13_supervisor_people_management.sql"
        ).read_text()
        self.assertIn("previous_role", supervisor_migration)
        self.assertNotIn("current_role text", supervisor_migration)
        self.assertIn("update_employee_profile", sql)
        self.assertIn("app_employee_profile_audit", sql)

    def test_role_schema_archives_legacy_wide_permission_table(self):
        schema = (
            Path(__file__).resolve().parents[1]
            / "sql" / "access" / "role_management" / "01_schema.sql"
        ).read_text()

        self.assertIn("information_schema.columns", schema)
        self.assertIn("column_name = 'role_key'", schema)
        self.assertIn("rename to app_role_permissions_legacy_wide", schema)
        self.assertNotIn("drop table", schema.lower())


def _dynamic_role_frames():
    roles = pd.DataFrame([
        {"role_key": "visitor", "role_name": "游客"},
        {"role_key": "supervisor", "role_name": "主管"},
    ])
    catalog = pd.DataFrame([
        {
            "permission_key": "can_view_app", "permission_name": "查看售后查询",
            "permission_group": "基础页面", "sort_order": 10,
        },
        {
            "permission_key": "can_view_logistics",
            "permission_name": "USPS官方API查询",
            "permission_group": "物流", "sort_order": 20,
        },
        {
            "permission_key": "can_manage_logistics",
            "permission_name": "生产物流：ERP同步、OCR与管理",
            "permission_group": "物流", "sort_order": 30,
        },
        {
            "permission_key": "can_manage_access",
            "permission_name": "管理用户与角色权限",
            "permission_group": "系统管理", "sort_order": 40,
        },
    ])
    assigned = pd.DataFrame([
        {"role_key": "visitor", "permission_key": "can_view_app"},
        {"role_key": "supervisor", "permission_key": "can_view_app"},
        {"role_key": "supervisor", "permission_key": "can_view_logistics"},
    ])
    return roles, catalog, assigned


if __name__ == "__main__":
    unittest.main()
