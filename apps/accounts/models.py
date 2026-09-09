from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """平台用户: 学员 / 观察员 / 管理员."""

    class Role(models.TextChoices):
        ADMIN = "admin", "管理员"
        OBSERVER = "observer", "观察员"
        TRAINEE = "trainee", "学员"

    role = models.CharField("角色", max_length=16, choices=Role.choices, default=Role.TRAINEE)

    @property
    def is_observer(self):
        return self.role == self.Role.OBSERVER

    @property
    def is_trainee(self):
        return self.role == self.Role.TRAINEE

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    def can_observe(self):
        return self.is_observer or self.is_admin_role
