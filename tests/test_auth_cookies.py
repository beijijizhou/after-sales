import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from utils.auth import cookies


class AuthCookieTests(unittest.TestCase):
    def test_initial_empty_component_result_is_not_cached(self):
        first = Mock()
        first.get.return_value = None
        first.get_all.return_value = {}
        second = Mock()
        second.get.return_value = "signed-token"
        fake_streamlit = SimpleNamespace(
            session_state={},
            context=SimpleNamespace(cookies={}),
        )

        with (
            patch.object(cookies, "st", fake_streamlit),
            patch.object(
                cookies.stx,
                "CookieManager",
                side_effect=[first, second],
            ),
        ):
            self.assertIsNone(cookies.read_auth_cookie())
            self.assertNotIn(
                cookies.AUTH_COOKIE_CACHE,
                fake_streamlit.session_state,
            )
            self.assertEqual(cookies.read_auth_cookie(), "signed-token")

        self.assertEqual(
            fake_streamlit.session_state[cookies.AUTH_COOKIE_CACHE],
            "signed-token",
        )

    def test_real_cookie_value_is_reused_from_session_cache(self):
        fake_streamlit = SimpleNamespace(
            session_state={cookies.AUTH_COOKIE_CACHE: "signed-token"},
            context=SimpleNamespace(cookies={}),
        )
        with (
            patch.object(cookies, "st", fake_streamlit),
            patch.object(cookies.stx, "CookieManager") as manager,
        ):
            self.assertEqual(cookies.read_auth_cookie(), "signed-token")
            manager.assert_not_called()


if __name__ == "__main__":
    unittest.main()
