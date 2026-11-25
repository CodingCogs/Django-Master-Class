"""
Fill the database with realistic, skewed demo data for the ORM chapter.

    uv run python manage.py populate_db            # default size
    uv run python manage.py populate_db --clear    # wipe and refill
    uv run python manage.py populate_db --scale 3  # 3x more rows
    uv run python manage.py populate_db --seed 7   # different (but repeatable) data

The data is deliberately uneven so aggregations are interesting:
a few books sell far more than the rest, about a quarter of customers never order,
some books have no reviews, some are out of stock or inactive.
"""

import random
import time
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from faker import Faker

from catalog.models import Author, Book, Category, Publisher, Tag
from shop.models import Customer, Order, OrderItem, Review

BASE_COUNTS = {
    "publishers": 40,
    "authors": 400,
    "books": 3000,
    "customers": 2000,
    "orders": 8000,
    "reviews": 15000,
}

CATEGORY_TREE = {
    "Fiction": ["Fantasy", "Science Fiction", "Mystery", "Romance", "Thriller", "Historical Fiction"],
    "Non-Fiction": ["Biography", "History", "Self-Help", "Travel", "True Crime"],
    "Science": ["Physics", "Biology", "Astronomy", "Mathematics"],
    "Technology": ["Programming", "Databases", "DevOps", "Artificial Intelligence", "Security"],
    "Business": ["Management", "Finance", "Marketing", "Entrepreneurship"],
    "Kids": ["Picture Books", "Young Adult", "Education"],
}

TAGS = [
    "bestseller", "award-winner", "classic", "new-release", "staff-pick", "hardcover",
    "paperback", "ebook", "illustrated", "series", "debut", "translated", "signed",
    "limited-edition", "beginner", "advanced", "python", "django", "postgres", "docker",
    "short-read", "long-read", "book-club", "gift", "summer-read", "dark", "funny",
    "inspiring", "academic", "reference",
]

ORDER_STATUS_WEIGHTS = {
    Order.Status.DELIVERED: 55,
    Order.Status.SHIPPED: 10,
    Order.Status.PAID: 12,
    Order.Status.PENDING: 13,
    Order.Status.CANCELLED: 10,
}

# Most reviews are positive, like real shops.
RATING_WEIGHTS = {5: 40, 4: 30, 3: 15, 2: 8, 1: 7}

BATCH = 1000


def money(value):
    return Decimal(f"{value:.2f}")


class Command(BaseCommand):
    help = "Populate the database with demo data for the advanced ORM chapter."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Delete existing demo data first.")
        parser.add_argument("--scale", type=float, default=1.0, help="Multiply all row counts (default 1.0).")
        parser.add_argument("--seed", type=int, default=42, help="Random seed for repeatable data.")

    def handle(self, *args, clear, scale, seed, **options):
        self.rng = random.Random(seed)
        Faker.seed(seed)
        self.fake = Faker()
        self.now = timezone.now()
        counts = {k: max(1, int(v * scale)) for k, v in BASE_COUNTS.items()}

        if Book.objects.exists() and not clear:
            self.stdout.write(self.style.WARNING("Data already exists. Use --clear to wipe and refill."))
            return

        started = time.perf_counter()
        with transaction.atomic():
            if clear:
                self._clear()
            categories = self._categories()
            publishers = self._publishers(counts["publishers"])
            authors = self._authors(counts["authors"])
            tags = self._tags()
            books = self._books(counts["books"], categories, publishers, authors, tags)
            customers = self._customers(counts["customers"])
            self._orders(counts["orders"], customers, books)
            self._reviews(counts["reviews"], customers, books)

        self.stdout.write(self.style.SUCCESS(f"Done in {time.perf_counter() - started:.1f}s"))
        for model in (Category, Publisher, Author, Tag, Book, Customer, Order, OrderItem, Review):
            self.stdout.write(f"  {model.__name__:<10} {model.objects.count():>7}")

    # ------------------------------------------------------------------ helpers

    def _log(self, msg):
        self.stdout.write(f"- {msg}")

    def _past(self, max_days, min_days=0):
        return self.now - timedelta(
            days=self.rng.randint(min_days, max_days), seconds=self.rng.randint(0, 86_399)
        )

    def _clear(self):
        self._log("clearing old data")
        for model in (Review, OrderItem, Order, Customer, Book, Author, Tag, Publisher):
            model.objects.all().delete()
        Category.objects.all().delete()

    # ------------------------------------------------------------------ catalog

    def _categories(self):
        self._log("categories")
        roots = Category.objects.bulk_create(
            Category(name=name, slug=slugify(name)) for name in CATEGORY_TREE
        )
        children = Category.objects.bulk_create(
            Category(name=child, slug=slugify(child), parent=root)
            for root in roots
            for child in CATEGORY_TREE[root.name]
        )
        return children  # books live in leaf categories

    def _publishers(self, n):
        self._log(f"{n} publishers")
        names = set()
        while len(names) < n:
            names.add(f"{self.fake.last_name()} {self.rng.choice(['Press', 'Books', 'Publishing', 'House', 'Media'])}")
        return Publisher.objects.bulk_create(
            Publisher(
                name=name,
                country=self.fake.country(),
                founded_year=self.rng.randint(1850, 2020),
                website=f"https://{slugify(name)}.example.com",
            )
            for name in names
        )

    def _authors(self, n):
        self._log(f"{n} authors")
        objs = []
        for i in range(n):
            first, last = self.fake.first_name(), self.fake.last_name()
            objs.append(
                Author(
                    first_name=first,
                    last_name=last,
                    email=f"{first.lower()}.{last.lower()}.{i}@authors.example.com",
                    country=self.fake.country(),
                    birth_date=self.fake.date_of_birth(minimum_age=25, maximum_age=90)
                    if self.rng.random() > 0.1
                    else None,
                    bio="\n\n".join(self.fake.paragraphs(nb=4)),
                )
            )
        return Author.objects.bulk_create(objs, batch_size=BATCH)

    def _tags(self):
        self._log(f"{len(TAGS)} tags")
        return Tag.objects.bulk_create(Tag(name=name) for name in TAGS)

    def _books(self, n, categories, publishers, authors, tags):
        self._log(f"{n} books")
        # Some publishers and authors are far more prolific than others.
        pub_weights = [self.rng.paretovariate(1.5) for _ in publishers]
        author_weights = [self.rng.paretovariate(1.3) for _ in authors]

        isbns = self.rng.sample(range(10**9, 10**10), n)
        objs = []
        for i in range(n):
            price = self.rng.uniform(4.99, 89.99)
            stock_roll = self.rng.random()
            objs.append(
                Book(
                    title=self.fake.sentence(nb_words=self.rng.randint(2, 6)).rstrip("."),
                    isbn=f"978{isbns[i]}",
                    publisher=self.rng.choices(publishers, weights=pub_weights)[0],
                    category=self.rng.choice(categories),
                    price=money(price),
                    cost=money(price * self.rng.uniform(0.35, 0.75)),
                    stock=0 if stock_roll < 0.08 else self.rng.randint(1, 500),
                    pages=self.rng.randint(80, 1200),
                    published_date=self.fake.date_between(start_date="-30y", end_date="today"),
                    is_active=self.rng.random() > 0.07,
                    description="\n\n".join(self.fake.paragraphs(nb=5)),
                    view_count=int(self.rng.paretovariate(1.2) * 50),
                    created_at=self._past(5 * 365),
                )
            )
        books = Book.objects.bulk_create(objs, batch_size=BATCH)

        BookAuthor = Book.authors.through
        BookTag = Book.tags.through
        book_authors, book_tags = [], []
        for book in books:
            k = self.rng.choices([1, 2, 3, 4], weights=[70, 20, 7, 3])[0]
            chosen = set(self.rng.choices(authors, weights=author_weights, k=k))
            book_authors += [BookAuthor(book_id=book.pk, author_id=a.pk) for a in chosen]
            for tag in self.rng.sample(tags, self.rng.randint(0, 5)):
                book_tags.append(BookTag(book_id=book.pk, tag_id=tag.pk))
        BookAuthor.objects.bulk_create(book_authors, batch_size=BATCH)
        BookTag.objects.bulk_create(book_tags, batch_size=BATCH)
        return books

    # ------------------------------------------------------------------ shop

    def _customers(self, n):
        self._log(f"{n} customers")
        cities = [(self.fake.city(), self.fake.country()) for _ in range(60)]
        objs = []
        for i in range(n):
            first, last = self.fake.first_name(), self.fake.last_name()
            city, country = self.rng.choice(cities)
            objs.append(
                Customer(
                    first_name=first,
                    last_name=last,
                    email=f"{first.lower()}.{last.lower()}.{i}@customers.example.com",
                    city=city,
                    country=country,
                    is_vip=self.rng.random() < 0.05,
                    joined_at=self._past(3 * 365, min_days=30),
                )
            )
        return Customer.objects.bulk_create(objs, batch_size=BATCH)

    def _orders(self, n, customers, books):
        # 15% of customers are never picked; with the long tail, about 24% end up with no orders.
        buyers = self.rng.sample(customers, int(len(customers) * 0.85))
        buyer_weights = [self.rng.paretovariate(1.5) for _ in buyers]
        sellable = [b for b in books if b.is_active]
        book_weights = [self.rng.paretovariate(1.1) for _ in sellable]
        statuses, status_weights = zip(*ORDER_STATUS_WEIGHTS.items())

        self._log(f"{n} orders")
        orders = []
        for _ in range(n):
            customer = self.rng.choices(buyers, weights=buyer_weights)[0]
            status = self.rng.choices(statuses, weights=status_weights)[0]
            created = max(self._past(2 * 365), customer.joined_at)
            shipped = None
            if status in (Order.Status.SHIPPED, Order.Status.DELIVERED):
                shipped = created + timedelta(days=self.rng.randint(1, 7))
            orders.append(
                Order(
                    customer=customer,
                    status=status,
                    # Usually ships to the customer's city, sometimes elsewhere.
                    shipping_city=customer.city if self.rng.random() < 0.9 else self.fake.city(),
                    created_at=created,
                    shipped_at=shipped,
                )
            )
        orders = Order.objects.bulk_create(orders, batch_size=BATCH)

        items = []
        for order in orders:
            k = self.rng.choices([1, 2, 3, 4, 5, 6], weights=[35, 30, 15, 10, 6, 4])[0]
            for book in set(self.rng.choices(sellable, weights=book_weights, k=k)):
                # Sometimes sold at a discount compared to the list price.
                discount = Decimal("1") if self.rng.random() < 0.75 else Decimal(str(self.rng.choice([0.9, 0.8, 0.7])))
                items.append(
                    OrderItem(
                        order=order,
                        book=book,
                        quantity=self.rng.choices([1, 2, 3, 5], weights=[75, 15, 7, 3])[0],
                        unit_price=(book.price * discount).quantize(Decimal("0.01")),
                    )
                )
        self._log(f"{len(items)} order items")
        OrderItem.objects.bulk_create(items, batch_size=BATCH)

    def _reviews(self, n, customers, books):
        # Popular books get many reviews; ~20% of books get none.
        reviewable = self.rng.sample(books, int(len(books) * 0.8))
        weights = [self.rng.paretovariate(1.1) for _ in reviewable]
        ratings, rating_weights = zip(*RATING_WEIGHTS.items())

        pairs = set()
        max_pairs = len(reviewable) * len(customers)
        while len(pairs) < min(n, max_pairs):
            book = self.rng.choices(reviewable, weights=weights)[0]
            pairs.add((book.pk, self.rng.choice(customers).pk))

        self._log(f"{len(pairs)} reviews")
        objs = [
            Review(
                book_id=book_id,
                customer_id=customer_id,
                rating=self.rng.choices(ratings, weights=rating_weights)[0],
                title=self.fake.sentence(nb_words=self.rng.randint(3, 8)).rstrip("."),
                body=self.fake.paragraph(nb_sentences=self.rng.randint(2, 8)),
                created_at=self._past(2 * 365),
            )
            for book_id, customer_id in pairs
        ]
        Review.objects.bulk_create(objs, batch_size=BATCH)
