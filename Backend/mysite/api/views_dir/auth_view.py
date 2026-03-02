from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from django.conf import settings
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from ..serializer_dir.users_serializer import CustomTokenObtainPairSerializer

class CookieTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):

        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            refresh_token = response.data.pop('refresh')
            # Set refresh token in HttpOnly cookie
            response.set_cookie(
                key='refresh_token',
                value=refresh_token,
                httponly=True,
                secure=False,  # Set to True in production
                samesite='Lax',
                path='/api/token/refresh/', # Only sent to refresh endpoint
                max_age=7 * 24 * 60 * 60 # 7 days
            )
        return response

class CookieTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get('refresh_token')
        
        if refresh_token:
            if hasattr(request.data, '_mutable'):
                request.data._mutable = True
            request.data['refresh'] = refresh_token

            
        try:
            response = super().post(request, *args, **kwargs)
        except (TokenError, InvalidToken) as e:
            response = Response({"detail": str(e)}, status=status.HTTP_401_UNAUTHORIZED)
            response.delete_cookie('refresh_token', path='/api/token/refresh/')
            return response

        if response.status_code == 200:
            # If refresh token rotation is enabled, the new refresh token will be in response.data
            if 'refresh' in response.data:
                new_refresh_token = response.data.pop('refresh')
                response.set_cookie(
                    key='refresh_token',
                    value=new_refresh_token,
                    httponly=True,
                    secure=False,
                    samesite='Lax',
                    path='/api/token/refresh/',
                    max_age=7 * 24 * 60 * 60
                )
        return response

class LogoutView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        response = Response({"message": "Successfully logged out"}, status=status.HTTP_200_OK)
        
        # Blacklist the token if it exists in cookies
        refresh_token = request.COOKIES.get('refresh_token')
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                pass
        
        response.delete_cookie('refresh_token', path='/api/token/refresh/')
        return response
