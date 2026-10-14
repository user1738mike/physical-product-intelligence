from django.contrib import admin

from .models import (
    AttributeClaim,
    ClaimSelection,
    ClaimVerification,
    ConfigurationRevision,
    Evidence,
    Measurement,
    PackagingConfiguration,
    PackagingProfile,
    Product,
    ProductRevision,
    RevisionEvidence,
)


class ProductHistoryAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for model in (Product, ProductRevision, Evidence, RevisionEvidence, PackagingProfile, Measurement):
    admin.site.register(model, ProductHistoryAdmin)

for model in (
    PackagingConfiguration,
    ConfigurationRevision,
    AttributeClaim,
    ClaimVerification,
    ClaimSelection,
):
    admin.site.register(model, ProductHistoryAdmin)
