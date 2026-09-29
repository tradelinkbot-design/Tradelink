from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
import uuid
from phonenumber_field.modelfields import PhoneNumberField
from django.core.exceptions import ValidationError


class UserManager(BaseUserManager):
    """Custom manager for the TradeLink NG User model."""

    def create_user(self, username, email, password, phone_number=None, **kwargs):
        if not username:
            raise ValidationError("Username Field Is Required")
        if not email:
            raise ValidationError("Email Field Is Required")
        if not password:
            raise ValidationError("Password Field Is Required")

        user = self.model(
            username=username,
            email=self.normalize_email(email),
            phone_number=phone_number,   # may be None for social-auth users
            **kwargs
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password, phone_number=None, **kwargs):
        if not username:
            raise ValidationError("Username Field Is Required")
        if not email:
            raise ValidationError("Email Field Is Required")
        if not password:
            raise ValidationError("Password Field Is Required")

        user = self.model(
            username=username,
            email=self.normalize_email(email),
            phone_number=phone_number,
            **kwargs
        )
        user.set_password(password)
        user.is_staff = True
        user.is_superuser = True
        user.save(using=self._db)
        return user


class User(AbstractBaseUser, PermissionsMixin):
    id           = models.UUIDField(unique=True, primary_key=True, editable=False,
                                    db_index=True, default=uuid.uuid4)
    username     = models.CharField(max_length=256, db_index=True, unique=True)
    first_name   = models.CharField(max_length=256, blank=True, null=True)
    last_name    = models.CharField(max_length=256, blank=True, null=True)
    phone_number = PhoneNumberField(unique=True, blank=True, null=True)

    email        = models.EmailField(unique=True, max_length=200)
    image        = models.ImageField(blank=True, upload_to="users_image", null=True)
    is_active    = models.BooleanField(default=True)
    is_staff     = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    created      = models.DateTimeField(auto_now_add=True)
    updated      = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.username

    def get_full_name(self):
        parts = [p for p in (self.first_name, self.last_name) if p]
        return " ".join(parts)

    @property
    def profile_complete(self):
        """True once the user has added their phone number."""
        return bool(self.phone_number)

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['username']   # phone_number removed — now optional

    objects = UserManager()