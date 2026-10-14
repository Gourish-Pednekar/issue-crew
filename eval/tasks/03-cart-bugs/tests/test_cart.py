import pytest

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
