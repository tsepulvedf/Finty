"""E2-M7: idioma del usuario, para los correos de subscription-service."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0002_userprofile"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="language",
            field=models.CharField(default="es", max_length=2),
        ),
    ]
