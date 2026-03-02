# api/middleware.py
class RateLimitHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        
        # Add rate limit headers if available
        if hasattr(request, 'successful_throttles'):
            for throttle in request.successful_throttles:
                if hasattr(throttle, 'limit'):
                    limit = int(throttle.limit.split('/')[0])
                    response['X-RateLimit-Limit'] = str(limit)
                    
                    if hasattr(throttle, 'num_requests'):
                        remaining = max(0, limit - throttle.num_requests)
                        response['X-RateLimit-Remaining'] = str(remaining)
        
        return response
