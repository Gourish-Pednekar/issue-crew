class Cart:
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
