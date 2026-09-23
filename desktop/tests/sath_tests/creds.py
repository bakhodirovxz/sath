"""Test serveri admin paroli — koddan emas, muhitdan (audit: testlarda qat'iy kodlangan parol yo'q).

GES_TEST_PASSWORD (yoki GES_ADMIN_PASSWORD) — desktop/tests/start_dev_server.ps1 uni o'zi o'rnatadi."""

import os


def admin_password() -> str:
    pw = os.environ.get("GES_TEST_PASSWORD") or os.environ.get("GES_ADMIN_PASSWORD")
    if not pw:
        raise RuntimeError(
            "GES_TEST_PASSWORD o'rnatilmagan: test serveri admin paroli kerak "
            "(desktop/tests/start_dev_server.ps1 uni yaratadi va shu PowerShell sessiyasiga yozadi)"
        )
    return pw
