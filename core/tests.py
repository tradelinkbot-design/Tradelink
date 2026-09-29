import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.test import RequestFactory, TestCase
from django.views import View

from core.middleware import GlobalRateLimitMiddleware
from core.ratelimit import count_requests, is_rate_limited, is_rate_limited_async, rate_limit

User = get_user_model()


class RateLimitCoreTests(TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.factory = RequestFactory()

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def test_count_requests_and_is_rate_limited(self):
        req = self.factory.get('/some-path/')
        req.user = type('AnonUser', (), {'is_authenticated': False, 'pk': None})()

        # Limit is 3 requests within 60s
        for _ in range(3):
            self.assertFalse(is_rate_limited(req, key='test_limit:{ip}', limit=3, window=60))

        # 4th request exceeds limit
        self.assertTrue(is_rate_limited(req, key='test_limit:{ip}', limit=3, window=60))

    def test_is_rate_limited_fails_open_on_cache_error(self):
        req = self.factory.get('/some-path/')
        req.user = type('AnonUser', (), {'is_authenticated': False, 'pk': None})()

        with patch('core.ratelimit.count_requests', side_effect=RuntimeError('Redis connection lost')):
            self.assertFalse(is_rate_limited(req, key='test_limit:{ip}', limit=3, window=60))

    def test_rate_limit_decorator_injects_headers_on_success(self):
        class SampleView(View):
            @rate_limit(key='sample:{ip}', limit=5, window=60)
            def get(self, request):
                return HttpResponse('OK')

        req = self.factory.get('/sample/')
        req.user = type('AnonUser', (), {'is_authenticated': False, 'pk': None})()

        view = SampleView.as_view()
        response = view(req)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-RateLimit-Limit'], '5')
        self.assertEqual(response['X-RateLimit-Remaining'], '4')
        self.assertIn('X-RateLimit-Reset', response)

    def test_rate_limit_decorator_json_response_on_block(self):
        class ApiView(View):
            @rate_limit(key='api:{ip}', limit=2, window=60, message='Rate limited.', json=True)
            def post(self, request):
                return JsonResponse({'status': 'ok'})

        req = self.factory.post('/api/')
        req.user = type('AnonUser', (), {'is_authenticated': False, 'pk': None})()
        view = ApiView.as_view()

        # Hit 1 & 2
        r1 = view(req)
        self.assertEqual(r1.status_code, 200)
        r2 = view(req)
        self.assertEqual(r2.status_code, 200)

        # Hit 3 (exceeded)
        r3 = view(req)
        self.assertEqual(r3.status_code, 429)
        self.assertEqual(r3['X-RateLimit-Limit'], '2')
        self.assertEqual(r3['X-RateLimit-Remaining'], '0')
        self.assertEqual(r3['Retry-After'], '60')

        data = json.loads(r3.content)
        self.assertEqual(data.get('error'), 'Rate limited.')

    def test_rate_limit_decorator_redirect_on_block(self):
        class FormActionView(View):
            @rate_limit(key='form:{ip}', limit=1, window=60, message='Slow down.', json=False)
            def post(self, request):
                return HttpResponse('Success')

        req = self.factory.post('/form-url/')
        # Set session and messages for redirect behavior
        req.user = type('AnonUser', (), {'is_authenticated': False, 'pk': None})()
        req.session = {}
        # Simulate messages framework
        from django.contrib.messages.storage.fallback import FallbackStorage
        setattr(req, '_messages', FallbackStorage(req))

        view = FormActionView.as_view()

        # Hit 1
        r1 = view(req)
        self.assertEqual(r1.status_code, 200)

        # Hit 2 (blocked)
        r2 = view(req)
        self.assertEqual(r2.status_code, 302)
        self.assertEqual(r2['Location'], '/form-url/')
        self.assertEqual(r2['X-RateLimit-Limit'], '1')
        self.assertEqual(r2['X-RateLimit-Remaining'], '0')
        self.assertEqual(r2['Retry-After'], '60')

    async def test_is_rate_limited_async(self):
        user_pk = 42

        # Allow 2 requests
        is_blocked_1 = await is_rate_limited_async(user_pk, key='async_test:{user}', limit=2, window=60)
        self.assertFalse(is_blocked_1)

        is_blocked_2 = await is_rate_limited_async(user_pk, key='async_test:{user}', limit=2, window=60)
        self.assertFalse(is_blocked_2)

        # 3rd request is blocked
        is_blocked_3 = await is_rate_limited_async(user_pk, key='async_test:{user}', limit=2, window=60)
        self.assertTrue(is_blocked_3)


class GlobalRateLimitMiddlewareTests(TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.factory = RequestFactory()

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def test_middleware_allows_normal_traffic_and_blocks_excess(self):
        def get_response(request):
            return HttpResponse('OK')

        middleware = GlobalRateLimitMiddleware(get_response)
        middleware.limit = 3
        middleware.window = 60

        req = self.factory.get('/some-page/')

        # 3 requests pass
        for _ in range(3):
            resp = middleware(req)
            self.assertEqual(resp.status_code, 200)

        # 4th request gets 429
        resp4 = middleware(req)
        self.assertEqual(resp4.status_code, 429)
        self.assertIn(b'Rate limit exceeded', resp4.content)

    def test_middleware_exempts_admin_static_and_media(self):
        def get_response(request):
            return HttpResponse('OK')

        middleware = GlobalRateLimitMiddleware(get_response)
        middleware.limit = 1
        middleware.window = 60

        admin_req = self.factory.get('/admin/login/')

        # Multiple requests to /admin/ should never be blocked by global middleware
        for _ in range(5):
            resp = middleware(admin_req)
            self.assertEqual(resp.status_code, 200)

    def test_middleware_fails_open_on_cache_error(self):
        def get_response(request):
            return HttpResponse('OK')

        middleware = GlobalRateLimitMiddleware(get_response)
        req = self.factory.get('/test/')

        with patch('core.ratelimit.count_requests', side_effect=Exception('Cache offline')):
            resp = middleware(req)
            self.assertEqual(resp.status_code, 200)
