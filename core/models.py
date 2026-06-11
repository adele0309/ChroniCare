from django.conf import settings
from django.db import models


class SystemConfig(models.Model):
    nom_etablissement = models.CharField(max_length=255)
    logo = models.ImageField(upload_to='logo/', null=True, blank=True)
    email_contact = models.EmailField(default="admin@example.com")
    telephone = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return self.nom_etablissement


class AuditLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
    )
    action = models.CharField(max_length=255)
    description = models.TextField()
    table_concernee = models.CharField(max_length=100)
    date_action = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.action}"


class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True
