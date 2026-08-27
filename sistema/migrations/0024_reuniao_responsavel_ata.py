from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reunioes", "0023_rotaparada_empresa_blank"),
    ]

    operations = [
        migrations.AddField(
            model_name="reuniao",
            name="responsavel_ata",
            field=models.CharField(
                blank=True,
                max_length=150,
                verbose_name="Responsavel pela elaboracao e entrega da ata",
            ),
        ),
    ]
