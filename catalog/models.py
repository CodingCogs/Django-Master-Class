from django.db import models
from django.utils import timezone


class Category(models.Model):
    """Tree of categories. `parent` is a self-FK, handy for select_related demos."""

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Publisher(models.Model):
    name = models.CharField(max_length=200, unique=True)
    country = models.CharField(max_length=100)
    founded_year = models.PositiveIntegerField()
    website = models.URLField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Author(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    country = models.CharField(max_length=100)
    birth_date = models.DateField(null=True, blank=True)
    # Deliberately large text: good for only()/defer() demos.
    bio = models.TextField(blank=True)

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Book(models.Model):
    title = models.CharField(max_length=255)
    isbn = models.CharField(max_length=13, unique=True)
    publisher = models.ForeignKey(
        Publisher, on_delete=models.PROTECT, related_name="books"
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="books"
    )
    authors = models.ManyToManyField(Author, related_name="books")
    tags = models.ManyToManyField(Tag, related_name="books", blank=True)

    price = models.DecimalField(max_digits=8, decimal_places=2)
    # Cost price: lets you compute margins with F() expressions.
    cost = models.DecimalField(max_digits=8, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    pages = models.PositiveIntegerField()
    published_date = models.DateField()
    is_active = models.BooleanField(default=True)
    # Deliberately large text: good for only()/defer() demos.
    description = models.TextField(blank=True)
    # Incremented with F() to demo race-free updates.
    view_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    # NOTE: no extra indexes on purpose (e.g. published_date, price).
    # Adding them is part of the query-optimization lesson.

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title
