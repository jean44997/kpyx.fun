import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0006_set_service_pack_prices")]

    operations = [
        migrations.AlterField(
            model_name="servicepack",
            name="price_xof",
            field=models.PositiveIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1)], verbose_name="Prix ponctuel (XOF)"),
        ),
    ]
