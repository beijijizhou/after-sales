import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DIAGNOSTIC_DIR = PROJECT_ROOT / "output" / "automation" / "haloo"
DIAGNOSTIC_PATH = DIAGNOSTIC_DIR / "controls.json"
DIAGNOSTIC_SCREENSHOT = DIAGNOSTIC_DIR / "controls.png"


def save_control_diagnostics(page):
    DIAGNOSTIC_DIR.mkdir(parents=True, exist_ok=True)
    controls = []
    for frame in page.frames:
        frame_controls = frame.locator(
            "button, input, [role='combobox'], .ant-select-selector"
        ).evaluate_all(
            """elements => elements.map(element => ({
                tag: element.tagName,
                text: (element.innerText || '').trim(),
                placeholder: element.getAttribute('placeholder') || '',
                type: element.getAttribute('type') || '',
                value: element.value || '',
                class_name: element.className || '',
                parent_text: (element.parentElement?.innerText || '').trim(),
                visible: Boolean(element.offsetWidth || element.offsetHeight)
            }))"""
        )
        controls.append({
            "frame_name": frame.name,
            "frame_url": frame.url,
            "controls": frame_controls,
        })
    DIAGNOSTIC_PATH.write_text(
        json.dumps(controls, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    page.screenshot(path=DIAGNOSTIC_SCREENSHOT, full_page=True)
