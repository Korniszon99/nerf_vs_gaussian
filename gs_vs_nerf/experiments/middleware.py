"""Staff-only research workstation when production settings are enabled."""
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required

class StaffAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.REQUIRE_STAFF_AUTH and not request.path.startswith(("/admin/", settings.STATIC_URL)):
            return staff_member_required(self.get_response)(request)
        return self.get_response(request)
