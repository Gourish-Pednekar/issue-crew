"""Create eval tasks 02 and 03, register them, and verify their baselines fail."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sandbox import run_pytest  # noqa: E402

TASKS_DIR = ROOT / "eval" / "tasks"
TASKS_JSON = ROOT / "eval" / "tasks.json"

COMMON = {
    "pytest.ini": "[pytest]\npythonpath = .\n",
    "app/__init__.py": "",
}

TASKS = {
    "02-slugify": {
        "prompt": (
            "Implement slugify(text) in app/text_utils.py so that all tests in "
            "tests/test_text_utils.py pass. Do not modify the tests."
        ),
        "files": {
            "app/text_utils.py": '''def slugify(text):
    raise NotImplementedError
''',
            "tests/test_text_utils.py": '''from app.text_utils import slugify


def test_lowercases():
    assert slugify("Hello") == "hello"


def test_spaces_become_hyphens():
    assert slugify("hello world") == "hello-world"


def test_punctuation_removed():
    assert slugify("Hello, World!") == "hello-world"


def test_collapses_repeated_separators():
    assert slugify("a   b---c") == "a-b-c"


def test_strips_leading_and_trailing():
    assert slugify("  --Hello--  ") == "hello"


def test_empty_returns_empty():
    assert slugify("") == ""


def test_digits_kept():
    assert slugify("Python 3.11 rocks") == "python-311-rocks"
''',
        },
    },
    "03-cart-bugs": {
        "prompt": (
            "The shopping cart in app/cart.py has bugs. Fix them so all tests in "
            "tests/test_cart.py pass, including rejecting discount percentages above "
            "100 with a ValueError. Do not modify the tests."
        ),
        "files": {
            "app/cart.py": '''class Cart:
    def __init__(self):
        self.items = []

    def add(self, name, unit_price, quantity=1):
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        self.items.append((name, unit_price, quantity))

    def subtotal(self):
        return sum(price for _, price, _ in self.items)

    def total(self, discount_percent=0):
        sub = self.subtotal()
        return round(sub - sub * discount_percent, 2)
''',
            "tests/test_cart.py": '''import pytest

from app.cart import Cart


def test_subtotal_counts_quantity():
    c = Cart()
    c.add("pen", 2.50, 4)
    assert c.subtotal() == 10.0


def test_subtotal_multiple_items():
    c = Cart()
    c.add("pen", 2.50, 2)
    c.add("book", 10.0)
    assert c.subtotal() == 15.0


def test_total_without_discount():
    c = Cart()
    c.add("book", 10.0, 3)
    assert c.total() == 30.0


def test_total_with_ten_percent_discount():
    c = Cart()
    c.add("book", 10.0, 3)
    assert c.total(discount_percent=10) == 27.0


def test_discount_above_100_rejected():
    c = Cart()
    c.add("pen", 1.0)
    with pytest.raises(ValueError):
        c.total(discount_percent=101)


def test_zero_quantity_rejected():
    c = Cart()
    with pytest.raises(ValueError):
        c.add("pen", 1.0, 0)
''',
        },
    },
}


def main():
    registry = json.loads(TASKS_JSON.read_text(encoding="utf-8"))
    known = {t["id"] for t in registry}

    for task_id, spec in TASKS.items():
        task_dir = TASKS_DIR / task_id
        if task_dir.exists():
            print(f"{task_id}: folder already exists, leaving it alone")
        else:
            for rel, content in {**COMMON, **spec["files"]}.items():
                path = task_dir / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8", newline="\n")
            print(f"{task_id}: created")

        if task_id not in known:
            registry.append({"id": task_id, "prompt": spec["prompt"]})

        passed, out = run_pytest(task_dir)
        last = out.strip().splitlines()[-1] if out.strip() else "(no output)"
        if passed:
            print(f"  WARNING: baseline already passes! {last}")
        else:
            print(f"  baseline fails as expected: {last}")

    TASKS_JSON.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    print(f"\ntasks.json now has {len(registry)} tasks")


if __name__ == "__main__":
    main()