import os

os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:///./test_monitor.db'
os.environ['JWT_SECRET'] = 'test-secret-that-is-definitely-longer-than-32-characters'
os.environ['ADMIN_EMAIL'] = 'admin@example.com'
os.environ['ADMIN_PASSWORD'] = 'admin-password-for-tests'
os.environ['REALTIME_ENABLED'] = 'false'
