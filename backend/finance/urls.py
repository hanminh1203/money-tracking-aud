from django.urls import path

from . import api_views

urlpatterns = [
    path('auth/me', api_views.auth_me, name='auth_me'),
    path('auth/google/login', api_views.google_login, name='google_login'),
    path('auth/google/callback', api_views.google_callback, name='google_callback'),
    path('auth/logout', api_views.logout, name='logout'),
    path('transactions', api_views.transactions, name='transactions'),
    path('metadata', api_views.metadata, name='metadata'),
    path('income-expense', api_views.income_expense, name='income_expense'),
    path('spending-by-category', api_views.spending_by_category, name='spending_by_category'),
    path('transfers', api_views.create_transfer, name='create_transfer'),
    path('receipts', api_views.create_receipt, name='create_receipt'),
    path('receipts/ocr', api_views.receipt_ocr, name='receipt_ocr'),
    path('receipts/<str:receipt_id>', api_views.get_receipt, name='get_receipt'),
    path('assistant/parse', api_views.assistant_parse, name='assistant_parse'),
    path('health', api_views.health, name='health'),
    path('management/status', api_views.management_status, name='management_status'),
    path('management/sync', api_views.management_sync, name='management_sync'),
]
