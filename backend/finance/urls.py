from django.urls import path

from . import api_views

urlpatterns = [
    path('auth/me', api_views.auth_me, name='auth_me'),
    path('auth/google/login', api_views.google_login, name='google_login'),
    path('auth/google/callback', api_views.google_callback, name='google_callback'),
    path('auth/logout', api_views.logout, name='logout'),
    path('dashboard', api_views.dashboard, name='dashboard'),
    path('transactions', api_views.transactions, name='transactions'),
    path('metadata', api_views.metadata, name='metadata'),
    path('transfers', api_views.create_transfer, name='create_transfer'),
    path('receipts', api_views.create_receipt, name='create_receipt'),
    path('receipts/ocr', api_views.receipt_ocr, name='receipt_ocr'),
    path('receipts/<str:receipt_id>', api_views.get_receipt, name='get_receipt'),
    path('giftcards', api_views.giftcards, name='giftcards'),
    path('giftcards/buy', api_views.buy_giftcard, name='buy_giftcard'),
    path('giftcards/<str:giftcard_id>/use', api_views.use_giftcard, name='use_giftcard'),
    path('assistant/parse', api_views.assistant_parse, name='assistant_parse'),
    path('health', api_views.health, name='health'),
    path('management/status', api_views.management_status, name='management_status'),
    path('management/sync', api_views.management_sync, name='management_sync'),
    path('management/export', api_views.management_export, name='management_export'),
]
