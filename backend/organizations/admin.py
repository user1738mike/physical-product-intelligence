from django.contrib import admin

from .models import Membership, Organization


class TenantReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Organization)
class OrganizationAdmin(TenantReadOnlyAdmin):
    list_display = ["name", "slug", "is_active"]


@admin.register(Membership)
class MembershipAdmin(TenantReadOnlyAdmin):
    list_display = ["organization", "user", "role"]
