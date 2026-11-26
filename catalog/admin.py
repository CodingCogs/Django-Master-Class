# catalog/admin.py
from django.contrib import admin
from .models import Book

@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ["title", "publisher", "price", "stock"]
    list_select_related = ["publisher"]
    search_fields = ["title", "isbn"]
    raw_id_fields = ["publisher", "category", "authors", "tags"]
