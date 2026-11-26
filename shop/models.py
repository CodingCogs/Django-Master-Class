from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from catalog.models import Book


class Customer(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    city = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    is_vip = models.BooleanField(default=False)
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="orders"
    )
    # No db_index on purpose: adding one is part of the optimization lesson.
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    shipping_city = models.CharField(max_length=100)
    created_at = models.DateTimeField(default=timezone.now)
    shipped_at = models.DateTimeField(null=True, blank=True)

    # The order total is NOT stored. Compute it with
    # Sum(F("items__quantity") * F("items__unit_price")).

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"], name="order_status_idx"),
            ]

    def __str__(self):
        # Touches self.customer -> causes N+1 when listing orders without
        # select_related("customer"). Kept on purpose for the demo.
        return f"Order #{self.pk} by {self.customer}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    book = models.ForeignKey(Book, on_delete=models.PROTECT, related_name="order_items")
    quantity = models.PositiveIntegerField(default=1)
    # Price at purchase time; may differ from the book's current price.
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["order", "book"], name="unique_book_per_order"),
        ]

    def __str__(self):
        # Touches self.book -> N+1 without select_related("book").
        return f"{self.quantity} x {self.book}"


class Review(models.Model):
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="reviews")
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="reviews"
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    title = models.CharField(max_length=200)
    body = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["book", "customer"], name="one_review_per_customer"),
            models.CheckConstraint(
                condition=models.Q(rating__gte=1, rating__lte=5), name="rating_1_to_5"
            ),
        ]

    def __str__(self):
        return f"{self.rating}★ {self.book} by {self.customer}"
